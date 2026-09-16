//! Cross-origin resource sharing (specification section 8).

use crate::headers::Headers;

/// Headers a browser must be allowed to send to negotiate Links Notation.
pub const DEFAULT_ALLOWED_HEADERS: [&str; 5] = [
    "Content-Type",
    "Accept",
    "Authorization",
    "If-Match",
    "If-None-Match",
];

/// Headers a browser must be allowed to read to follow the protocol.
pub const DEFAULT_EXPOSED_HEADERS: [&str; 4] = ["ETag", "Link", "Location", "Allow"];

/// Methods a browser may use unless the policy narrows them.
pub const DEFAULT_METHODS: [&str; 7] = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"];

/// A cross-origin policy.
///
/// [`CorsPolicy::permissive`] is the `cors: true` of the JavaScript and Python
/// packages: every origin, every default method and header.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CorsPolicy {
    /// Allowed origins; a single `*` allows every origin.
    pub origins: Vec<String>,
    /// Allowed methods.
    pub methods: Vec<String>,
    /// Headers a request may carry.
    pub allowed_headers: Vec<String>,
    /// Headers a browser may read from the response.
    pub exposed_headers: Vec<String>,
    /// Whether credentials may be sent.
    pub credentials: bool,
    /// How long a preflight result may be cached, in seconds.
    pub max_age: u32,
}

impl Default for CorsPolicy {
    fn default() -> Self {
        Self::permissive()
    }
}

impl CorsPolicy {
    /// The permissive default policy.
    pub fn permissive() -> Self {
        Self {
            origins: vec!["*".to_string()],
            methods: DEFAULT_METHODS.iter().map(|m| m.to_string()).collect(),
            allowed_headers: DEFAULT_ALLOWED_HEADERS
                .iter()
                .map(|h| h.to_string())
                .collect(),
            exposed_headers: DEFAULT_EXPOSED_HEADERS
                .iter()
                .map(|h| h.to_string())
                .collect(),
            credentials: false,
            max_age: 600,
        }
    }

    /// The same policy restricted to the given origins.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::cors::{cors_headers, CorsPolicy};
    ///
    /// let policy = CorsPolicy::permissive().with_origins(["https://app.example"]);
    /// assert!(cors_headers(&policy, Some("https://other.example")).is_empty());
    /// ```
    pub fn with_origins<I, S>(mut self, origins: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        self.origins = origins.into_iter().map(Into::into).collect();
        self
    }

    /// The same policy with credentials allowed.
    pub fn with_credentials(mut self, credentials: bool) -> Self {
        self.credentials = credentials;
        self
    }

    /// The same policy with another preflight cache lifetime.
    pub fn with_max_age(mut self, max_age: u32) -> Self {
        self.max_age = max_age;
        self
    }
}

/// Build the CORS response headers for a request.
///
/// The map is empty when the origin is not allowed, which leaves the response
/// without any cross-origin permission — exactly what a browser needs to refuse
/// it.
pub fn cors_headers(policy: &CorsPolicy, request_origin: Option<&str>) -> Headers {
    let wildcard = policy.origins.iter().any(|origin| origin == "*");
    let allow_origin = if wildcard {
        match (policy.credentials, request_origin) {
            (true, Some(origin)) => Some(origin.to_string()),
            _ => Some("*".to_string()),
        }
    } else {
        request_origin
            .filter(|origin| policy.origins.iter().any(|allowed| allowed == origin))
            .map(str::to_string)
    };

    let Some(allow_origin) = allow_origin else {
        return Headers::new();
    };

    let mut headers = Headers::from_pairs([
        ("Access-Control-Allow-Origin", allow_origin),
        ("Access-Control-Allow-Methods", policy.methods.join(", ")),
        (
            "Access-Control-Allow-Headers",
            policy.allowed_headers.join(", "),
        ),
        (
            "Access-Control-Expose-Headers",
            policy.exposed_headers.join(", "),
        ),
        ("Access-Control-Max-Age", policy.max_age.to_string()),
    ]);
    if policy.credentials {
        headers.insert("Access-Control-Allow-Credentials", "true");
    }
    headers
}
