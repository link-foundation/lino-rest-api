//! Media types and content negotiation (specification section 2).
//!
//! Negotiation follows RFC 9110 section 12.5.1: the `Accept` header is parsed
//! into ranges with quality values, the ranges are ordered by quality and then
//! by specificity, and the first range that matches a representation the server
//! can produce wins.

/// Readable, indented Links Notation. The default representation.
pub const LINO_CONTENT_TYPE: &str = "text/lino";

/// Readable Links Notation restricted to one line per value.
pub const LINO_LINE_CONTENT_TYPE: &str = "text/lino-line";

/// Type-tagged, base64 Links Notation that preserves object identity.
pub const LINO_COMPACT_CONTENT_TYPE: &str = "text/lino-compact";

/// JSON fallback for clients that cannot speak Links Notation.
pub const JSON_CONTENT_TYPE: &str = "application/json";

/// Problem details served as Links Notation.
pub const LINO_PROBLEM_CONTENT_TYPE: &str = "application/problem+lino";

/// Media type of RFC 9457 problem details expressed as JSON.
pub const JSON_PROBLEM_CONTENT_TYPE: &str = "application/problem+json";

/// Every representation a server produces, most preferred first.
pub const SUPPORTED_MEDIA_TYPES: [&str; 4] = [
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
];

/// One range of an `Accept` header.
#[derive(Debug, Clone, PartialEq)]
pub struct AcceptRange {
    /// The media range itself, lower-cased.
    pub media_type: String,
    /// Quality value, 1.0 when absent.
    pub quality: f64,
    /// 0 for `*/*`, 1 for `type/*`, 2 for a concrete type.
    pub specificity: u8,
}

/// Add `charset=utf-8` to a media type so that bytes are unambiguous.
pub fn with_charset(media_type: &str) -> String {
    format!("{media_type}; charset=utf-8")
}

/// Strip parameters and normalise case, turning a header value into a media type.
///
/// Returns an empty string when the header is absent.
pub fn parse_content_type(header_value: Option<&str>) -> String {
    match header_value {
        None => String::new(),
        Some(value) => value
            .split(';')
            .next()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase(),
    }
}

/// Parse an `Accept` header into ranges ordered by preference.
pub fn parse_accept(header_value: Option<&str>) -> Vec<AcceptRange> {
    let header = header_value.unwrap_or("").trim();
    if header.is_empty() {
        return vec![AcceptRange {
            media_type: "*/*".to_string(),
            quality: 1.0,
            specificity: 0,
        }];
    }

    let mut ranges: Vec<(usize, AcceptRange)> = Vec::new();
    for (index, part) in header.split(',').enumerate() {
        let mut pieces = part.split(';');
        let media_type = pieces.next().unwrap_or("").trim().to_ascii_lowercase();
        if media_type.is_empty() {
            continue;
        }

        let mut quality = 1.0;
        for parameter in pieces {
            let (name, value) = match parameter.split_once('=') {
                Some((name, value)) => (name, value),
                None => (parameter, ""),
            };
            if name.trim().eq_ignore_ascii_case("q") {
                quality = value.trim().parse::<f64>().unwrap_or(0.0);
            }
        }

        let specificity = if media_type == "*/*" {
            0
        } else if media_type.ends_with("/*") {
            1
        } else {
            2
        };

        ranges.push((
            index,
            AcceptRange {
                media_type,
                quality,
                specificity,
            },
        ));
    }

    ranges.sort_by(|left, right| {
        right
            .1
            .quality
            .partial_cmp(&left.1.quality)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(right.1.specificity.cmp(&left.1.specificity))
            .then(left.0.cmp(&right.0))
    });
    ranges.into_iter().map(|entry| entry.1).collect()
}

/// Test whether an `Accept` range matches a concrete media type.
fn range_matches(range_type: &str, media_type: &str) -> bool {
    if range_type == "*/*" || range_type == media_type {
        return true;
    }
    match range_type.strip_suffix('*') {
        Some(prefix) => media_type.starts_with(prefix),
        None => false,
    }
}

/// Select the representation to produce for a request.
///
/// Returns `None` when nothing the server can produce is acceptable, which the
/// caller answers with `406 Not Acceptable`.
pub fn negotiate_media_type(accept_header: Option<&str>, supported: &[String]) -> Option<String> {
    for accepted in parse_accept(accept_header) {
        if accepted.quality <= 0.0 {
            continue;
        }
        for media_type in supported {
            if range_matches(&accepted.media_type, media_type) {
                return Some(media_type.clone());
            }
        }
    }
    None
}

/// Every representation a server produces, as owned strings.
pub fn supported_media_types() -> Vec<String> {
    SUPPORTED_MEDIA_TYPES
        .iter()
        .map(|entry| entry.to_string())
        .collect()
}

/// Resolve a media type to the representation it is encoded as.
///
/// Problem-details types carry the same syntax as their base representation, so
/// they decode with the same codec.
pub fn normalize_media_type(media_type: &str) -> &str {
    match media_type {
        LINO_PROBLEM_CONTENT_TYPE => LINO_CONTENT_TYPE,
        JSON_PROBLEM_CONTENT_TYPE => JSON_CONTENT_TYPE,
        other => other,
    }
}

/// Test whether a request body media type can be decoded.
pub fn is_decodable_media_type(media_type: &str) -> bool {
    SUPPORTED_MEDIA_TYPES.contains(&normalize_media_type(media_type))
}

/// Problem-details media type matching a representation.
pub fn problem_media_type(media_type: &str) -> &str {
    match media_type {
        LINO_CONTENT_TYPE => LINO_PROBLEM_CONTENT_TYPE,
        JSON_CONTENT_TYPE => JSON_PROBLEM_CONTENT_TYPE,
        other => other,
    }
}
