//! Links Notation REST client (specification section 10).
//!
//! Built on `reqwest`, so it talks to any service that speaks the wire protocol,
//! whichever language implements it.

use lino_objects_codec::LinoValue;

use crate::codec::{decode_from, encode_for};
use crate::headers::Headers;
use crate::media_type::{
    LINO_CONTENT_TYPE, is_decodable_media_type, parse_content_type, with_charset,
};
use crate::query::QueryParams;
use crate::value::{get, to_query_text};

/// Default `Accept` sent by the client: Links Notation first, JSON as a fallback.
///
/// Spelled out rather than built from [`crate::media_type::LINO_CONTENT_TYPE`],
/// because a constant cannot be formatted at compile time; the assertion in
/// `tests/client.rs` keeps the two in step.
pub const DEFAULT_ACCEPT: &str = "text/lino, application/json;q=0.5";

/// Path of the native service description (specification section 9).
pub const DESCRIPTION_PATH: &str = "/.well-known/lino-api";

/// Anything that can go wrong while talking to a service.
#[derive(Debug)]
pub enum LinoClientError {
    /// The request never produced a response.
    Transport(reqwest::Error),
    /// The service answered with a `4xx` or a `5xx`.
    Status {
        /// HTTP status code.
        status: u16,
        /// Decoded problem details, when the body could be decoded.
        problem: Option<LinoValue>,
        /// Human readable message, taken from the problem when there is one.
        message: String,
    },
    /// A value could not be encoded as the configured request representation.
    Encoding(String),
}

impl LinoClientError {
    /// The status code of a `4xx` or `5xx` answer.
    pub fn status(&self) -> Option<u16> {
        match self {
            Self::Status { status, .. } => Some(*status),
            _ => None,
        }
    }

    /// The problem details carried by a `4xx` or `5xx` answer.
    pub fn problem(&self) -> Option<&LinoValue> {
        match self {
            Self::Status { problem, .. } => problem.as_ref(),
            _ => None,
        }
    }

    /// Build the error of a failed response.
    fn of_status(status: u16, problem: Option<LinoValue>) -> Self {
        let message = problem
            .as_ref()
            .and_then(|problem| {
                get(problem, "detail")
                    .or_else(|| get(problem, "title"))
                    .map(to_query_text)
            })
            .filter(|message| !message.is_empty())
            .unwrap_or_else(|| format!("Request failed with status {status}"));
        Self::Status {
            status,
            problem,
            message,
        }
    }
}

impl std::fmt::Display for LinoClientError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Transport(error) => write!(formatter, "{error}"),
            Self::Status { message, .. } => write!(formatter, "{message}"),
            Self::Encoding(message) => write!(formatter, "{message}"),
        }
    }
}

impl std::error::Error for LinoClientError {}

impl From<reqwest::Error> for LinoClientError {
    fn from(error: reqwest::Error) -> Self {
        Self::Transport(error)
    }
}

/// A decoded response.
#[derive(Debug, Clone, PartialEq)]
pub struct LinoResponse {
    /// HTTP status code.
    pub status: u16,
    /// Response headers.
    pub headers: Headers,
    /// Decoded body, or [`None`] when the response carried none.
    pub data: Option<LinoValue>,
    /// The body as it arrived, for representations this client cannot decode.
    pub text: String,
    /// The `ETag` of the representation, when it carries one.
    pub etag: Option<String>,
    /// The `Location` of a created resource, when the response carries one.
    pub location: Option<String>,
}

impl LinoResponse {
    /// The decoded body, or a null value when there is none.
    pub fn value(&self) -> LinoValue {
        self.data.clone().unwrap_or(LinoValue::Null)
    }

    /// The methods advertised in an `Allow` header.
    pub fn allowed_methods(&self) -> Vec<String> {
        self.headers
            .get("allow")
            .unwrap_or("")
            .split(',')
            .map(str::trim)
            .filter(|method| !method.is_empty())
            .map(str::to_string)
            .collect()
    }
}

/// Everything a single call may add to a request.
#[derive(Debug, Clone, Default)]
pub struct RequestOptions {
    /// Query parameters, repeated parameters kept in order.
    pub query: QueryParams,
    /// Extra request headers.
    pub headers: Headers,
    /// Override the `Accept` header of the client.
    pub accept: Option<String>,
    /// `If-Match` precondition.
    pub if_match: Option<String>,
    /// `If-None-Match` precondition.
    pub if_none_match: Option<String>,
}

impl RequestOptions {
    /// Options that add nothing to a request.
    pub fn new() -> Self {
        Self::default()
    }

    /// The same options with one more query parameter.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::client::RequestOptions;
    /// use lino_rest_api::value::boolean;
    ///
    /// let options = RequestOptions::new().with_query("done", &boolean(false));
    /// assert_eq!(options.query.to_query_string(), "done=false");
    /// ```
    pub fn with_query<N: Into<String>>(mut self, name: N, value: &LinoValue) -> Self {
        self.query.append(name, to_query_text(value));
        self
    }

    /// The same options with one more textual query parameter.
    pub fn with_query_text<N: Into<String>, V: Into<String>>(mut self, name: N, value: V) -> Self {
        self.query.append(name, value);
        self
    }

    /// The same options with one more request header.
    pub fn with_header<N: Into<String>, V: Into<String>>(mut self, name: N, value: V) -> Self {
        self.headers.insert(name, value);
        self
    }

    /// The same options asking for another representation.
    pub fn with_accept<S: Into<String>>(mut self, accept: S) -> Self {
        self.accept = Some(accept.into());
        self
    }

    /// The same options carrying an `If-Match` precondition.
    pub fn if_match<S: Into<String>>(mut self, etag: S) -> Self {
        self.if_match = Some(etag.into());
        self
    }

    /// The same options carrying an `If-None-Match` precondition.
    pub fn if_none_match<S: Into<String>>(mut self, etag: S) -> Self {
        self.if_none_match = Some(etag.into());
        self
    }
}

/// A client for a service that speaks Links Notation.
#[derive(Debug, Clone)]
pub struct LinoClient {
    base_url: String,
    accept: String,
    content_type: String,
    headers: Headers,
    http: reqwest::Client,
}

impl LinoClient {
    /// A client for a service at a base URL.
    pub fn new<S: Into<String>>(base_url: S) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            accept: DEFAULT_ACCEPT.to_string(),
            content_type: LINO_CONTENT_TYPE.to_string(),
            headers: Headers::new(),
            http: reqwest::Client::new(),
        }
    }

    /// The same client asking for another representation.
    pub fn with_accept<S: Into<String>>(mut self, accept: S) -> Self {
        self.accept = accept.into();
        self
    }

    /// The same client sending request bodies as another representation.
    pub fn with_content_type<S: Into<String>>(mut self, content_type: S) -> Self {
        self.content_type = content_type.into();
        self
    }

    /// The same client sending one more header with every request.
    pub fn with_header<N: Into<String>, V: Into<String>>(mut self, name: N, value: V) -> Self {
        self.headers.insert(name, value);
        self
    }

    /// The same client built on a configured `reqwest` client.
    pub fn with_http_client(mut self, http: reqwest::Client) -> Self {
        self.http = http;
        self
    }

    /// The base URL every path is appended to.
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// Perform a request and decode the response.
    ///
    /// # Errors
    ///
    /// A [`LinoClientError::Status`] for any `4xx` or `5xx`, carrying the
    /// decoded problem details, and a [`LinoClientError::Transport`] when the
    /// request never reached the service.
    pub async fn request(
        &self,
        method: &str,
        path: &str,
        body: Option<&LinoValue>,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        let query = options.query.to_query_string();
        let url = if query.is_empty() {
            format!("{}{path}", self.base_url)
        } else {
            format!("{}{path}?{query}", self.base_url)
        };

        let mut request_headers = Headers::new();
        request_headers.insert(
            "Accept",
            options
                .accept
                .clone()
                .unwrap_or_else(|| self.accept.clone()),
        );
        request_headers.extend_missing(&self.headers);
        for (name, value) in options.headers.iter() {
            request_headers.insert(name.to_string(), value.to_string());
        }
        if let Some(etag) = &options.if_match {
            request_headers.insert("If-Match", etag.clone());
        }
        if let Some(etag) = &options.if_none_match {
            request_headers.insert("If-None-Match", etag.clone());
        }

        let method_name = method.to_uppercase();
        let http_method = reqwest::Method::from_bytes(method_name.as_bytes())
            .map_err(|error| LinoClientError::Encoding(error.to_string()))?;
        let mut builder = self.http.request(http_method, url);
        if let Some(value) = body {
            let encoded = encode_for(value, &self.content_type)
                .map_err(|error| LinoClientError::Encoding(error.to_string()))?;
            request_headers.insert("Content-Type", with_charset(&self.content_type));
            builder = builder.body(encoded);
        }
        for (name, value) in request_headers.iter() {
            builder = builder.header(name, value);
        }

        let response = builder.send().await?;
        let status = response.status().as_u16();
        let mut headers = Headers::new();
        for (name, value) in response.headers() {
            headers.insert(name.as_str(), value.to_str().unwrap_or_default());
        }
        let text = response.text().await?;
        let data = decode_response(status, &method_name, &headers, &text);

        if status >= 400 {
            return Err(LinoClientError::of_status(status, data));
        }
        Ok(LinoResponse {
            status,
            etag: headers.get("etag").map(str::to_string),
            location: headers.get("location").map(str::to_string),
            headers,
            data,
            text,
        })
    }

    /// `GET` a resource.
    pub async fn get(
        &self,
        path: &str,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        self.request("GET", path, None, options).await
    }

    /// `POST` to a collection.
    pub async fn post(
        &self,
        path: &str,
        body: &LinoValue,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        self.request("POST", path, Some(body), options).await
    }

    /// `PUT` a representation.
    pub async fn put(
        &self,
        path: &str,
        body: &LinoValue,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        self.request("PUT", path, Some(body), options).await
    }

    /// `PATCH` a representation.
    pub async fn patch(
        &self,
        path: &str,
        body: &LinoValue,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        self.request("PATCH", path, Some(body), options).await
    }

    /// `DELETE` a resource.
    pub async fn delete(
        &self,
        path: &str,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        self.request("DELETE", path, None, options).await
    }

    /// `HEAD` a resource.
    pub async fn head(
        &self,
        path: &str,
        options: &RequestOptions,
    ) -> Result<LinoResponse, LinoClientError> {
        self.request("HEAD", path, None, options).await
    }

    /// `OPTIONS` a path, returning the advertised methods.
    pub async fn options(
        &self,
        path: &str,
        options: &RequestOptions,
    ) -> Result<Vec<String>, LinoClientError> {
        Ok(self
            .request("OPTIONS", path, None, options)
            .await?
            .allowed_methods())
    }

    /// List a collection, returning the decoded envelope.
    pub async fn list(
        &self,
        path: &str,
        options: &RequestOptions,
    ) -> Result<LinoValue, LinoClientError> {
        Ok(self.get(path, options).await?.value())
    }

    /// Fetch the service description of specification section 9.
    pub async fn describe(&self) -> Result<LinoValue, LinoClientError> {
        Ok(self
            .get(DESCRIPTION_PATH, &RequestOptions::new())
            .await?
            .value())
    }
}

/// Decode a response body according to its own `Content-Type` (section 10).
///
/// A body this client cannot decode is left to the caller as text rather than
/// reported as an error, because a service may legitimately answer with a
/// representation the client never asked for.
pub fn decode_response(
    status: u16,
    method: &str,
    headers: &Headers,
    text: &str,
) -> Option<LinoValue> {
    if status == 204 || status == 304 || method == "HEAD" || text.is_empty() {
        return None;
    }
    let media_type = parse_content_type(headers.get("content-type"));
    if !is_decodable_media_type(&media_type) {
        return None;
    }
    decode_from(text, &media_type).ok()
}

/// Create a client, for symmetry with the other packages.
pub fn create_lino_client<S: Into<String>>(base_url: S) -> LinoClient {
    LinoClient::new(base_url)
}
