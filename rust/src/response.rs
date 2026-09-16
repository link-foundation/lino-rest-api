//! Explicit response values.
//!
//! A handler may return a plain value, which is sent as `200`, or one of these
//! results when it needs to control the status code or the headers.

use lino_objects_codec::LinoValue;

use crate::headers::Headers;

/// The body of a response: a value to encode, or nothing at all.
///
/// The distinction matters because `None` is a value Links Notation can encode,
/// while a `204` carries no body whatsoever.
#[derive(Debug, Clone, PartialEq)]
pub enum Body {
    /// No body, as `204` and `304` require.
    Empty,
    /// A value, encoded as the negotiated representation.
    Value(LinoValue),
    /// An already-encoded body, sent as it is.
    Raw(String),
}

impl From<LinoValue> for Body {
    fn from(value: LinoValue) -> Self {
        Body::Value(value)
    }
}

/// A handler result carrying a status code and headers alongside the value.
#[derive(Debug, Clone, PartialEq)]
pub struct LinoResult {
    /// The body.
    pub body: Body,
    /// HTTP status code.
    pub status: u16,
    /// Response headers.
    pub headers: Headers,
    /// Whether to compute an entity tag for the representation.
    pub etag: bool,
    /// Whether to evaluate conditional request headers; [`None`] follows `etag`.
    pub preconditions: Option<bool>,
    /// Whether an `If-Match` is required on unsafe methods.
    pub require_precondition: bool,
    /// Media type to send, overriding the negotiated one.
    pub media_type: Option<String>,
}

impl LinoResult {
    /// A result with a status and a body, and nothing else set.
    pub fn new(status: u16, body: Body) -> Self {
        Self {
            body,
            status,
            headers: Headers::new(),
            etag: true,
            preconditions: None,
            require_precondition: false,
            media_type: None,
        }
    }

    /// The same result with one more header.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::response::ok;
    /// use lino_rest_api::value::int;
    ///
    /// let result = ok(int(1)).with_header("X-Trace", "abc");
    /// assert_eq!(result.headers.get("x-trace"), Some("abc"));
    /// ```
    pub fn with_header<N: Into<String>, V: Into<String>>(mut self, name: N, value: V) -> Self {
        self.headers.insert(name, value);
        self
    }

    /// The same result with several more headers.
    pub fn with_headers(mut self, headers: Headers) -> Self {
        for (name, value) in headers.iter() {
            self.headers.insert(name.to_string(), value.to_string());
        }
        self
    }

    /// The same result without an entity tag, for bodies that are not worth
    /// caching or that change on every read.
    pub fn without_etag(mut self) -> Self {
        self.etag = false;
        self
    }

    /// The same result with conditional request evaluation turned on or off.
    pub fn with_preconditions(mut self, preconditions: bool) -> Self {
        self.preconditions = Some(preconditions);
        self
    }

    /// The same result demanding an `If-Match` on unsafe methods.
    pub fn requiring_precondition(mut self, require: bool) -> Self {
        self.require_precondition = require;
        self
    }

    /// The same result sent as a concrete media type.
    pub fn with_media_type<S: Into<String>>(mut self, media_type: S) -> Self {
        self.media_type = Some(media_type.into());
        self
    }
}

/// A `200 OK` carrying a value.
pub fn ok(value: LinoValue) -> LinoResult {
    LinoResult::new(200, Body::Value(value))
}

/// A `201 Created` carrying a value and a `Location`.
pub fn created(value: LinoValue, location: &str) -> LinoResult {
    LinoResult::new(201, Body::Value(value)).with_header("Location", location)
}

/// A `202 Accepted` carrying a value.
pub fn accepted(value: LinoValue) -> LinoResult {
    LinoResult::new(202, Body::Value(value))
}

/// A `204 No Content`.
pub fn no_content() -> LinoResult {
    LinoResult::new(204, Body::Empty)
}

/// A response with an explicit status code and a value.
pub fn status(status_code: u16, value: LinoValue) -> LinoResult {
    LinoResult::new(status_code, Body::Value(value))
}

/// A response with an explicit status code and no body.
pub fn status_empty(status_code: u16) -> LinoResult {
    LinoResult::new(status_code, Body::Empty)
}

/// A response whose body is already encoded, bypassing negotiation.
///
/// Used for representations that are defined by their own media type, such as
/// the OpenAPI document of specification section 9.
pub fn raw_response(body: &str, media_type: &str, status_code: u16) -> LinoResult {
    LinoResult::new(status_code, Body::Raw(body.to_string())).with_media_type(media_type)
}

impl From<LinoValue> for LinoResult {
    /// A plain value is a `200 OK` carrying it.
    fn from(value: LinoValue) -> Self {
        ok(value)
    }
}

impl From<()> for LinoResult {
    /// A handler that returns nothing sends a `204 No Content`.
    fn from(_: ()) -> Self {
        no_content()
    }
}
