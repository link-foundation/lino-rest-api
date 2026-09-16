//! Entity tags and conditional requests (specification section 7).

use sha2::{Digest, Sha256};

use crate::headers::Headers;
use crate::problem::LinoHttpError;

/// Compute the strong entity tag of an encoded representation.
///
/// # Examples
///
/// ```
/// use lino_rest_api::etag::compute_etag;
///
/// assert!(compute_etag("(a 1)").starts_with('"'));
/// ```
pub fn compute_etag(body: &str) -> String {
    let digest = Sha256::digest(body.as_bytes());
    let mut hex = String::with_capacity(64);
    for byte in digest {
        hex.push_str(&format!("{byte:02x}"));
    }
    format!("\"{hex}\"")
}

/// Split an `If-Match` or `If-None-Match` header into entity tags.
///
/// Any weak prefix is removed, because this API only issues strong tags.
pub fn parse_etag_list(header_value: Option<&str>) -> Vec<String> {
    let Some(header_value) = header_value else {
        return Vec::new();
    };
    header_value
        .split(',')
        .map(|tag| {
            tag.trim()
                .strip_prefix("W/")
                .unwrap_or(tag.trim())
                .to_string()
        })
        .filter(|tag| !tag.is_empty())
        .collect()
}

/// Test whether an entity tag list matches the current tag.
pub fn etag_matches(header_value: Option<&str>, current_etag: &str) -> bool {
    parse_etag_list(header_value)
        .iter()
        .any(|tag| tag == "*" || tag == current_etag)
}

/// Outcome of evaluating the conditional headers of a request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PreconditionResult {
    /// Whether the response should be `304 Not Modified`.
    pub not_modified: bool,
}

/// Evaluate the conditional request headers of a request.
///
/// # Errors
///
/// A `412` on a failed `If-Match`, and a `428` when one is required and absent.
pub fn evaluate_preconditions(
    headers: &Headers,
    method: &str,
    current_etag: &str,
    require_precondition: bool,
) -> Result<PreconditionResult, LinoHttpError> {
    let safe = method == "GET" || method == "HEAD";
    let if_match = headers.get("if-match");
    let if_none_match = headers.get("if-none-match");

    if !safe {
        if let Some(if_match) = if_match {
            if !etag_matches(Some(if_match), current_etag) {
                return Err(LinoHttpError::new(
                    412,
                    Some("The entity tag in If-Match does not match the current representation"),
                ));
            }
        } else if require_precondition {
            return Err(LinoHttpError::new(
                428,
                Some("This request requires an If-Match precondition"),
            ));
        }
    }

    if let Some(if_none_match) = if_none_match {
        if etag_matches(Some(if_none_match), current_etag) {
            if safe {
                return Ok(PreconditionResult { not_modified: true });
            }
            return Err(LinoHttpError::new(
                412,
                Some("The entity tag in If-None-Match matches the current representation"),
            ));
        }
    }

    Ok(PreconditionResult {
        not_modified: false,
    })
}
