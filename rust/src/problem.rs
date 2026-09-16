//! RFC 9457 problem details, expressed in Links Notation (specification section 5).

use std::collections::BTreeMap;
use std::fmt;

use lino_objects_codec::LinoValue;

use crate::value::{int, object, string};

/// Base URI every registered problem type is resolved against.
pub const PROBLEM_TYPE_BASE: &str = "https://link-foundation.github.io/lino-rest-api/errors/";

/// Reason phrase of a status code, falling back to a generic class phrase.
pub fn reason_phrase(status: u16) -> &'static str {
    match status {
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        406 => "Not Acceptable",
        409 => "Conflict",
        410 => "Gone",
        412 => "Precondition Failed",
        413 => "Content Too Large",
        415 => "Unsupported Media Type",
        422 => "Unprocessable Content",
        428 => "Precondition Required",
        429 => "Too Many Requests",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        502 => "Bad Gateway",
        503 => "Service Unavailable",
        504 => "Gateway Timeout",
        status if status >= 500 => "Server Error",
        _ => "Request Error",
    }
}

/// Kebab-case slug used as the last segment of a problem type URI.
///
/// # Examples
///
/// ```
/// use lino_rest_api::problem::problem_slug;
///
/// assert_eq!(problem_slug("Precondition Required"), "precondition-required");
/// ```
pub fn problem_slug(title: &str) -> String {
    let mut slug = String::new();
    let mut pending_dash = false;
    for character in title.to_lowercase().chars() {
        if character.is_ascii_alphanumeric() {
            if pending_dash && !slug.is_empty() {
                slug.push('-');
            }
            pending_dash = false;
            slug.push(character);
        } else {
            pending_dash = true;
        }
    }
    slug
}

/// An HTTP error that carries problem details.
///
/// Returning one of these from a handler produces a conforming error response;
/// the client returns the same shape when a server answers with 4xx or 5xx.
#[derive(Debug, Clone, PartialEq)]
pub struct LinoHttpError {
    /// HTTP status code.
    pub status: u16,
    /// Short, type-wide summary.
    pub title: String,
    /// Human readable explanation of this occurrence.
    pub detail: Option<String>,
    /// Problem type URI.
    pub type_uri: String,
    /// URI of this occurrence.
    pub instance: Option<String>,
    /// Response headers to send with the error.
    pub headers: BTreeMap<String, String>,
    /// Extra problem members.
    pub extensions: Vec<(String, LinoValue)>,
}

impl LinoHttpError {
    /// An error with a status and an optional detail, titled after the status.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::problem::LinoHttpError;
    ///
    /// let error = LinoHttpError::new(404, Some("No task 7"));
    /// assert_eq!(error.title, "Not Found");
    /// assert!(error.type_uri.ends_with("not-found"));
    /// ```
    pub fn new(status: u16, detail: Option<&str>) -> Self {
        let title = reason_phrase(status).to_string();
        Self {
            status,
            type_uri: format!("{PROBLEM_TYPE_BASE}{}", problem_slug(&title)),
            title,
            detail: detail.map(str::to_string),
            instance: None,
            headers: BTreeMap::new(),
            extensions: Vec::new(),
        }
    }

    /// The same error with another title, which also retitles the type URI.
    pub fn with_title<S: Into<String>>(mut self, title: S) -> Self {
        self.title = title.into();
        self.type_uri = format!("{PROBLEM_TYPE_BASE}{}", problem_slug(&self.title));
        self
    }

    /// The same error with an explicit problem type URI.
    pub fn with_type<S: Into<String>>(mut self, type_uri: S) -> Self {
        self.type_uri = type_uri.into();
        self
    }

    /// The same error with the URI of this occurrence.
    pub fn with_instance<S: Into<String>>(mut self, instance: S) -> Self {
        self.instance = Some(instance.into());
        self
    }

    /// The same error with one more response header.
    pub fn with_header<N: Into<String>, V: Into<String>>(mut self, name: N, value: V) -> Self {
        self.headers.insert(name.into(), value.into());
        self
    }

    /// The same error with one more problem member.
    pub fn with_extension<S: Into<String>>(mut self, key: S, value: LinoValue) -> Self {
        self.extensions.push((key.into(), value));
        self
    }

    /// Human readable message: the detail when present, the title otherwise.
    pub fn message(&self) -> &str {
        self.detail.as_deref().unwrap_or(&self.title)
    }

    /// Render the error as the problem details object of the specification.
    pub fn to_problem(&self, instance: Option<&str>) -> LinoValue {
        let mut problem = object([
            ("type", string(self.type_uri.clone())),
            ("title", string(self.title.clone())),
            ("status", int(i64::from(self.status))),
        ]);
        if let LinoValue::Object(members) = &mut problem {
            if let Some(detail) = &self.detail {
                members.push(("detail".to_string(), string(detail.clone())));
            }
            let resolved = self
                .instance
                .as_deref()
                .filter(|text| !text.is_empty())
                .or(instance)
                .filter(|text| !text.is_empty());
            if let Some(resolved) = resolved {
                members.push(("instance".to_string(), string(resolved)));
            }
            for (key, value) in &self.extensions {
                members.push((key.clone(), value.clone()));
            }
        }
        problem
    }
}

impl fmt::Display for LinoHttpError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.message())
    }
}

impl std::error::Error for LinoHttpError {}

/// Build problem details for a status code without constructing an error first.
pub fn problem_details(status: u16, detail: Option<&str>, instance: Option<&str>) -> LinoValue {
    LinoHttpError::new(status, detail).to_problem(instance)
}

/// A 422 carrying field-level validation failures.
///
/// Each failure is an object with a `field` and a `message`, exactly as the
/// JavaScript and Python packages send it.
pub fn validation_error(errors: Vec<(String, String)>, detail: &str) -> LinoHttpError {
    let items = errors
        .into_iter()
        .map(|(field, message)| object([("field", string(field)), ("message", string(message))]))
        .collect::<Vec<_>>();
    LinoHttpError::new(422, Some(detail))
        .with_title("Unprocessable Content")
        .with_type(format!("{PROBLEM_TYPE_BASE}validation-failed"))
        .with_extension("errors", LinoValue::Array(items))
}
