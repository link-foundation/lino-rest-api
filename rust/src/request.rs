//! The request object handlers receive.
//!
//! It is intentionally small: the method, the path, the decoded body, the
//! negotiated representation and the parsed query.

use lino_objects_codec::LinoValue;

use crate::headers::Headers;
use crate::problem::LinoHttpError;
use crate::query::{CollectionQuery, QueryParams, form_decode, parse_collection_query};
use crate::router::PathParams;

/// Page-size defaults a request inherits from its application.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QueryDefaults {
    /// Page size used when a request does not ask for one.
    pub default_limit: usize,
    /// Largest page the server will serve.
    pub max_limit: usize,
}

impl Default for QueryDefaults {
    fn default() -> Self {
        Self {
            default_limit: crate::query::DEFAULT_LIMIT,
            max_limit: crate::query::MAX_LIMIT,
        }
    }
}

/// One HTTP request, decoded according to the specification.
#[derive(Debug, Clone)]
pub struct LinoRequest {
    /// HTTP method, upper-cased.
    pub method: String,
    /// Request path, without the query string.
    pub path: String,
    /// Request headers, looked up without regard to case.
    pub headers: Headers,
    /// Path parameters captured by the matched route.
    pub params: PathParams,
    /// Raw query string, without its leading `?`.
    pub query_string: String,
    /// Decoded request body, or [`None`] when the request carried none.
    pub body: Option<LinoValue>,
    /// The representation the response will be encoded as.
    pub media_type: String,
    /// The media type the request body arrived in.
    pub request_media_type: Option<String>,
    /// Page-size defaults inherited from the application.
    pub query_defaults: QueryDefaults,
}

impl LinoRequest {
    /// A request with a method and a path, and nothing else set.
    pub fn new<M: Into<String>, P: Into<String>>(method: M, path: P) -> Self {
        Self {
            method: method.into().to_uppercase(),
            path: path.into(),
            headers: Headers::new(),
            params: PathParams::new(),
            query_string: String::new(),
            body: None,
            media_type: crate::media_type::LINO_CONTENT_TYPE.to_string(),
            request_media_type: None,
            query_defaults: QueryDefaults::default(),
        }
    }

    /// Read a request header, case insensitively.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.get(name)
    }

    /// Read a path parameter, percent-decoded.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::request::LinoRequest;
    ///
    /// let mut request = LinoRequest::new("GET", "/tasks/a%20b");
    /// request.params.insert("id".to_string(), "a%20b".to_string());
    /// assert_eq!(request.param("id").as_deref(), Some("a b"));
    /// ```
    pub fn param(&self, name: &str) -> Option<String> {
        self.params.get(name).map(|value| percent_decode(value))
    }

    /// Query parameters, with repeated parameters kept in order.
    pub fn query(&self) -> QueryParams {
        QueryParams::parse(&self.query_string)
    }

    /// Parse the query string as a collection query (specification section 6).
    ///
    /// # Errors
    ///
    /// A `400` when `limit` or `offset` is not a non-negative integer.
    pub fn collection_query(&self) -> Result<CollectionQuery, LinoHttpError> {
        parse_collection_query(
            &self.query(),
            self.query_defaults.default_limit,
            self.query_defaults.max_limit,
        )
    }

    /// The request body, or a `400` when the request carried none.
    ///
    /// # Errors
    ///
    /// A `400` when the body is absent, which is what a `POST` without one is.
    pub fn require_body(&self) -> Result<&LinoValue, LinoHttpError> {
        self.body
            .as_ref()
            .ok_or_else(|| LinoHttpError::new(400, Some("A request body is required")))
    }

    /// The path together with its query string, as the `instance` of a problem.
    pub fn instance(&self) -> String {
        if self.query_string.is_empty() {
            self.path.clone()
        } else {
            format!("{}?{}", self.path, self.query_string)
        }
    }
}

/// Percent-decode a path segment, leaving `+` alone.
///
/// A path is not a form, so `+` there is a plus sign, not a space.
pub fn percent_decode(text: &str) -> String {
    form_decode(&text.replace('+', "%2B"))
}

/// Percent-encode a path, leaving the segment separator alone.
///
/// This is what Python's `urllib.parse.quote` does with its default `safe="/"`,
/// so an identifier appears in a `Location` header the same way in every
/// implementation.
///
/// # Examples
///
/// ```
/// use lino_rest_api::request::percent_encode;
///
/// assert_eq!(percent_encode("a b/c"), "a%20b/c");
/// ```
pub fn percent_encode(text: &str) -> String {
    let mut encoded = String::with_capacity(text.len());
    for byte in text.as_bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                encoded.push(*byte as char)
            }
            other => encoded.push_str(&format!("%{other:02X}")),
        }
    }
    encoded
}
