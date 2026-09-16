//! The request and response halves of the specification, expressed as plain
//! functions: body decoding and content negotiation (section 2.1), entity tags
//! (section 7) and problem details (section 5).
//!
//! [`crate::app::LinoApp`] is built from these helpers, and any other HTTP stack
//! can be wired to the same behaviour by calling them directly.

use lino_objects_codec::LinoValue;

use crate::codec::{decode_from, encode_for};
use crate::etag::{compute_etag, evaluate_preconditions};
use crate::headers::{Headers, append_list_value};
use crate::media_type::{
    LINO_CONTENT_TYPE, is_decodable_media_type, negotiate_media_type, parse_content_type,
    problem_media_type, supported_media_types, with_charset,
};
use crate::problem::LinoHttpError;
use crate::response::Body;
use crate::value::{array, string};

/// Largest request body accepted by default, in bytes.
pub const DEFAULT_MAX_BODY_BYTES: usize = 1024 * 1024;

/// A response ready to be written to the wire.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResponseParts {
    /// HTTP status code.
    pub status: u16,
    /// Response headers.
    pub headers: Headers,
    /// Encoded body; empty for `204` and `304`.
    pub body: String,
}

impl ResponseParts {
    /// A response with a status, headers and a body.
    pub fn new(status: u16, headers: Headers, body: impl Into<String>) -> Self {
        Self {
            status,
            headers,
            body: body.into(),
        }
    }
}

/// Add a field name to `Vary` without repeating it.
///
/// Both content negotiation and CORS extend `Vary`; a plain assignment from
/// either of them would silently drop the other one's contribution.
pub fn append_vary(headers: &mut Headers, field_name: &str) {
    append_list_value(headers, "Vary", field_name);
}

/// Select the representation to produce for a request.
///
/// # Errors
///
/// A `406` when no supported representation is acceptable, carrying the list of
/// the ones that are.
pub fn negotiate_request(
    headers: &Headers,
    supported: Option<&[String]>,
) -> Result<String, LinoHttpError> {
    let candidates = supported
        .map(<[String]>::to_vec)
        .unwrap_or_else(supported_media_types);
    let accept = headers.get("accept");
    negotiate_media_type(accept, &candidates).ok_or_else(|| {
        LinoHttpError::new(
            406,
            Some(&format!(
                "No acceptable representation for Accept: {}",
                accept.unwrap_or("")
            )),
        )
        .with_extension("supported", array(candidates.iter().cloned().map(string)))
    })
}

/// A decoded request body, together with the media type it arrived in.
#[derive(Debug, Clone, PartialEq)]
pub struct DecodedBody {
    /// The value, or [`None`] when the request carried no body.
    pub value: Option<LinoValue>,
    /// The media type the body arrived in, when it carried one.
    pub media_type: Option<String>,
}

/// Decode a request body according to its `Content-Type`.
///
/// # Errors
///
/// A `413` when the body is too large, a `415` when its media type is not one
/// this API reads, and a `400` when it is malformed.
pub fn decode_request_body(
    raw: &[u8],
    content_type: Option<&str>,
    max_bytes: usize,
) -> Result<DecodedBody, LinoHttpError> {
    if raw.len() > max_bytes {
        return Err(LinoHttpError::new(
            413,
            Some(&format!("Request body exceeds {max_bytes} bytes")),
        )
        .with_header("Connection", "close"));
    }

    let media_type = parse_content_type(content_type);
    if media_type.is_empty() {
        return Ok(DecodedBody {
            value: None,
            media_type: None,
        });
    }

    if !is_decodable_media_type(&media_type) {
        return Err(LinoHttpError::new(
            415,
            Some(&format!("Unsupported request media type: {media_type}")),
        )
        .with_extension(
            "supported",
            array(supported_media_types().into_iter().map(string)),
        ));
    }

    let text = String::from_utf8_lossy(raw);
    if text.trim().is_empty() {
        return Ok(DecodedBody {
            value: None,
            media_type: Some(media_type),
        });
    }

    match decode_from(&text, &media_type) {
        Ok(value) => Ok(DecodedBody {
            value: Some(value),
            media_type: Some(media_type),
        }),
        Err(error) => Err(LinoHttpError::new(
            400,
            Some(&format!("Malformed {media_type} request body: {error}")),
        )),
    }
}

/// How a response should treat entity tags and conditional requests.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EtagPolicy {
    /// Whether to emit an `ETag`.
    pub etag: bool,
    /// Whether to evaluate conditional headers; [`None`] means safe methods only.
    pub preconditions: Option<bool>,
    /// Whether an `If-Match` is required on unsafe methods.
    pub require_precondition: bool,
}

impl Default for EtagPolicy {
    fn default() -> Self {
        Self {
            etag: true,
            preconditions: None,
            require_precondition: false,
        }
    }
}

/// Encode a value as the negotiated representation.
///
/// # Errors
///
/// A `412` or a `428` when a precondition fails, and a `500` when the value
/// cannot be encoded as the negotiated representation.
pub fn build_response(
    body: &Body,
    status: u16,
    media_type: &str,
    headers: &Headers,
    request_headers: &Headers,
    method: &str,
    policy: EtagPolicy,
) -> Result<ResponseParts, LinoHttpError> {
    let mut response_headers = headers.clone();
    append_vary(&mut response_headers, "Accept");

    if status == 204 || matches!(body, Body::Empty) {
        let status = if status == 200 { 204 } else { status };
        return Ok(ResponseParts::new(status, response_headers, ""));
    }

    let encoded = match body {
        Body::Raw(text) => text.clone(),
        Body::Value(value) => encode_for(value, media_type)
            .map_err(|error| LinoHttpError::new(500, Some(&error.to_string())))?,
        Body::Empty => unreachable!("handled above"),
    };

    if policy.etag {
        let tag = compute_etag(&encoded);
        response_headers.insert("ETag", tag.clone());

        // Preconditions on unsafe methods have to be evaluated against the
        // *current* representation before the change is applied, which only the
        // route handler can do; here the body is already the new representation.
        let safe = method == "GET" || method == "HEAD";
        let evaluate = policy.preconditions.unwrap_or(safe);
        if evaluate
            && evaluate_preconditions(request_headers, method, &tag, policy.require_precondition)?
                .not_modified
        {
            return Ok(ResponseParts::new(304, response_headers, ""));
        }
    }

    response_headers.insert("Content-Type", with_charset(media_type));
    Ok(ResponseParts::new(status, response_headers, encoded))
}

/// Render an error as problem details (specification section 5).
///
/// # Examples
///
/// ```
/// use lino_rest_api::middleware::build_problem_response;
/// use lino_rest_api::problem::LinoHttpError;
///
/// let parts = build_problem_response(
///     &LinoHttpError::new(404, Some("No task 7")),
///     "text/lino",
///     Some("/tasks/7"),
/// );
/// assert_eq!(parts.status, 404);
/// assert_eq!(
///     parts.headers.get("content-type"),
///     Some("application/problem+lino; charset=utf-8"),
/// );
/// ```
pub fn build_problem_response(
    error: &LinoHttpError,
    media_type: &str,
    instance: Option<&str>,
) -> ResponseParts {
    let problem = error.to_problem(instance);
    let mut headers = Headers::new();
    for (name, value) in &error.headers {
        headers.insert(name.clone(), value.clone());
    }
    append_vary(&mut headers, "Accept");
    headers.insert("Content-Type", with_charset(problem_media_type(media_type)));

    // The problem itself must reach the client even when the negotiated
    // representation is the one that failed, so encoding falls back to LINO.
    let body = encode_for(&problem, media_type)
        .or_else(|_| encode_for(&problem, LINO_CONTENT_TYPE))
        .unwrap_or_else(|_| String::new());

    ResponseParts::new(error.status, headers, body)
}
