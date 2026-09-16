//! Helpers shared by the integration suites.
//!
//! The JavaScript suite starts a server on an ephemeral port and the Python one
//! drives the application in process; here both paths are available, so that the
//! same checks can be run against [`LinoApp::respond`] directly and against the
//! axum shell over a real socket.

// Each integration test is its own crate, so a helper only some of them use
// would otherwise be reported as dead code.
#![allow(dead_code)]

use std::sync::Arc;

use lino_objects_codec::LinoValue;
use lino_rest_api::app::{LinoApp, RawRequest};
use lino_rest_api::client::LinoClient;
use lino_rest_api::codec::decode_from;
use lino_rest_api::headers::Headers;
use lino_rest_api::media_type::{JSON_CONTENT_TYPE, LINO_CONTENT_TYPE};
use lino_rest_api::middleware::ResponseParts;
use lino_rest_api::serve::BoundServer;
use lino_rest_api::value::{as_array, get, to_query_text};

/// One response, however it was obtained.
#[derive(Debug, Clone)]
pub struct RawResponse {
    /// HTTP status code.
    pub status: u16,
    /// Response headers.
    pub headers: Headers,
    /// Response body, as text.
    pub text: String,
}

impl RawResponse {
    /// Read a response header, case insensitively.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.get(name)
    }

    /// Read a response header, failing the test when it is absent.
    pub fn require(&self, name: &str) -> &str {
        self.header(name)
            .unwrap_or_else(|| panic!("response carries no {name} header"))
    }

    /// The bare media type of the response, without its parameters.
    pub fn content_type(&self) -> String {
        self.header("content-type")
            .unwrap_or("")
            .split(';')
            .next()
            .unwrap_or("")
            .trim()
            .to_string()
    }

    /// The field names listed in `Vary`, lower-cased.
    pub fn vary_fields(&self) -> Vec<String> {
        self.header("vary")
            .unwrap_or("")
            .split(',')
            .map(|field| field.trim().to_lowercase())
            .filter(|field| !field.is_empty())
            .collect()
    }

    /// Decode the body as the media type the response declares.
    pub fn value(&self) -> LinoValue {
        let media_type = self.content_type();
        let media_type = if media_type.is_empty() {
            LINO_CONTENT_TYPE.to_string()
        } else {
            media_type
        };
        decode_from(&self.text, &media_type)
            .unwrap_or_else(|error| panic!("body is not a well-formed {media_type}: {error}"))
    }

    /// Decode the body as Links Notation, whatever the response declares.
    ///
    /// Problem details arrive as `application/problem+lino`, which carries the
    /// same syntax as `text/lino`.
    pub fn lino(&self) -> LinoValue {
        decode_from(&self.text, LINO_CONTENT_TYPE)
            .unwrap_or_else(|error| panic!("body is not well-formed Links Notation: {error}"))
    }

    /// Decode the body as JSON.
    pub fn json(&self) -> LinoValue {
        decode_from(&self.text, JSON_CONTENT_TYPE)
            .unwrap_or_else(|error| panic!("body is not well-formed JSON: {error}"))
    }
}

impl From<ResponseParts> for RawResponse {
    fn from(parts: ResponseParts) -> Self {
        Self {
            status: parts.status,
            headers: parts.headers,
            text: parts.body,
        }
    }
}

/// Drive an application in process, without a socket.
pub struct InProcess {
    /// The application under test.
    pub app: LinoApp,
}

impl InProcess {
    /// Wrap an application.
    pub fn new(app: LinoApp) -> Self {
        Self { app }
    }

    /// Send a request built by the caller.
    pub async fn send(&self, request: RawRequest) -> RawResponse {
        self.app.respond(request).await.into()
    }

    /// Send a request with a method, a path, headers and an optional body.
    pub async fn raw(
        &self,
        method: &str,
        path: &str,
        headers: &[(&str, &str)],
        body: Option<&str>,
    ) -> RawResponse {
        let mut request = RawRequest::new(method, path);
        if let Some((path, query)) = path.split_once('?') {
            request.path = path.to_string();
            request.query_string = query.to_string();
        }
        for (name, value) in headers {
            request.headers.insert(*name, *value);
        }
        if let Some(body) = body {
            request.body = body.as_bytes().to_vec();
        }
        self.send(request).await
    }
}

/// A live application together with a raw and a Links Notation client.
pub struct Served {
    /// Base URL of the running server.
    pub base: String,
    /// A client that does no Links Notation handling at all.
    pub http: reqwest::Client,
    /// The client of specification section 10.
    pub client: LinoClient,
}

impl Served {
    /// Start an application on an ephemeral port and hand out clients for it.
    ///
    /// The server is spawned on the current runtime, which the test harness
    /// shuts down when the test ends, so nothing has to be stopped by hand.
    pub async fn start(app: LinoApp) -> Self {
        let server = BoundServer::bind(app, "127.0.0.1:0")
            .await
            .expect("an ephemeral port is available");
        let base = server.base_url();
        tokio::spawn(async move {
            let _ = server.serve().await;
        });
        Self {
            client: LinoClient::new(base.clone()),
            base,
            http: reqwest::Client::new(),
        }
    }

    /// Send a request without any Links Notation handling.
    pub async fn raw(
        &self,
        method: &str,
        path: &str,
        headers: &[(&str, &str)],
        body: Option<&str>,
    ) -> RawResponse {
        let method = reqwest::Method::from_bytes(method.as_bytes()).expect("a known method");
        let mut builder = self.http.request(method, format!("{}{path}", self.base));
        for (name, value) in headers {
            builder = builder.header(*name, *value);
        }
        if let Some(body) = body {
            builder = builder.body(body.to_string());
        }
        let response = builder.send().await.expect("the server answers");
        let status = response.status().as_u16();
        let mut collected = Headers::new();
        for (name, value) in response.headers() {
            collected.insert(name.as_str(), value.to_str().unwrap_or_default());
        }
        RawResponse {
            status,
            headers: collected,
            text: response.text().await.expect("a readable body"),
        }
    }
}

/// Wrap a store for [`LinoApp::resource`].
pub fn shared<S>(store: S) -> Arc<S> {
    Arc::new(store)
}

/// Read a member, failing the test when it is absent.
pub fn member<'a>(value: &'a LinoValue, key: &str) -> &'a LinoValue {
    get(value, key).unwrap_or_else(|| panic!("value carries no {key} member: {value:?}"))
}

/// Read a nested member by path, failing the test when a step is absent.
pub fn at<'a>(value: &'a LinoValue, path: &[&str]) -> &'a LinoValue {
    path.iter().fold(value, |current, key| member(current, key))
}

/// Read a member as text.
pub fn text(value: &LinoValue, key: &str) -> String {
    to_query_text(member(value, key))
}

/// Read the `items` member of a collection envelope.
pub fn items(envelope: &LinoValue) -> &Vec<LinoValue> {
    as_array(member(envelope, "items")).expect("items is a list")
}
