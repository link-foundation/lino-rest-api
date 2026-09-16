//! The Links Notation REST API application.
//!
//! The application is a framework-independent request handler: it takes a
//! [`RawRequest`] — a method, a path, a query string, headers and body bytes —
//! and answers with [`ResponseParts`]. Everything the specification requires
//! happens in between: content negotiation, Links Notation bodies, problem
//! details, automatic `HEAD`, automatic `OPTIONS`, `405 Method Not Allowed` with
//! `Allow`, CORS and a machine-readable service description.
//!
//! [`crate::serve`] runs it over HTTP; anything else that can build a
//! [`RawRequest`] can run it too.

use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use lino_objects_codec::LinoValue;

use crate::codec::to_json_pretty;
use crate::cors::{CorsPolicy, cors_headers};
use crate::description::{ServiceInfo, openapi_document, service_description};
use crate::headers::Headers;
use crate::media_type::{JSON_CONTENT_TYPE, LINO_CONTENT_TYPE};
use crate::middleware::{
    DEFAULT_MAX_BODY_BYTES, EtagPolicy, ResponseParts, append_vary, build_problem_response,
    build_response, decode_request_body, negotiate_request,
};
use crate::problem::LinoHttpError;
use crate::request::{LinoRequest, QueryDefaults};
use crate::resource::{ResourceOptions, register_resource};
use crate::response::{Body, LinoResult, raw_response};
use crate::router::{RouteMeta, RouteTable};
use crate::store::Store;

/// Methods a handler can be registered for.
pub const HTTP_METHODS: [&str; 7] = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"];

/// Where the native service description lives (specification section 9).
pub const DESCRIPTION_PATH: &str = "/.well-known/lino-api";

/// Where the generated OpenAPI 3.1 document lives (specification section 9).
pub const OPENAPI_PATH: &str = "/.well-known/openapi.json";

/// What a handler returns: a future resolving to a result or a problem.
pub type HandlerFuture = Pin<Box<dyn Future<Output = Result<LinoResult, LinoHttpError>> + Send>>;

/// A registered route handler.
pub type Handler = Arc<dyn Fn(LinoRequest) -> HandlerFuture + Send + Sync>;

/// One HTTP request as it arrives from a server, before it is decoded.
#[derive(Debug, Clone, Default)]
pub struct RawRequest {
    /// HTTP method.
    pub method: String,
    /// Request path, without the query string.
    pub path: String,
    /// Query string, without its leading `?`.
    pub query_string: String,
    /// Request headers.
    pub headers: Headers,
    /// Raw request body.
    pub body: Vec<u8>,
}

impl RawRequest {
    /// A request with a method and a path, and nothing else set.
    pub fn new<M: Into<String>, P: Into<String>>(method: M, path: P) -> Self {
        Self {
            method: method.into().to_uppercase(),
            path: path.into(),
            ..Self::default()
        }
    }

    /// The same request with a query string, without its leading `?`.
    pub fn with_query<S: Into<String>>(mut self, query_string: S) -> Self {
        self.query_string = query_string.into();
        self
    }

    /// The same request with one more header.
    pub fn with_header<N: Into<String>, V: Into<String>>(mut self, name: N, value: V) -> Self {
        self.headers.insert(name, value);
        self
    }

    /// The same request carrying a body of a media type.
    pub fn with_body<B: Into<Vec<u8>>>(mut self, body: B, content_type: &str) -> Self {
        self.body = body.into();
        self.headers.insert("Content-Type", content_type);
        self
    }
}

/// An application that speaks Links Notation.
pub struct LinoApp {
    /// Title, version and prose description of the service.
    pub info: ServiceInfo,
    /// CORS policy, when cross-origin requests are allowed.
    pub cors: Option<CorsPolicy>,
    /// Representations the server may produce; [`None`] means all of them.
    pub supported: Option<Vec<String>>,
    /// Largest accepted request body.
    pub max_body_bytes: usize,
    /// Page-size defaults for collection queries.
    pub query_defaults: QueryDefaults,
    routes: RouteTable,
    handlers: HashMap<(String, String), Handler>,
    describe_routes: bool,
}

impl Default for LinoApp {
    fn default() -> Self {
        Self::new()
    }
}

impl LinoApp {
    /// A new application serving its own description.
    ///
    /// # Examples
    ///
    /// ```
    /// use lino_rest_api::app::{LinoApp, RawRequest};
    /// use lino_rest_api::value::{object, string};
    ///
    /// # tokio_test::block_on(async {
    /// let mut app = LinoApp::new();
    /// app.get_fn("/health", "Health", |_request| {
    ///     Ok(object([("status", string("ok"))]))
    /// });
    ///
    /// let response = app.respond(RawRequest::new("GET", "/health")).await;
    /// assert_eq!(response.status, 200);
    /// assert_eq!(response.body, "(\n  status \"ok\"\n)");
    /// # });
    /// ```
    pub fn new() -> Self {
        let mut app = Self {
            info: ServiceInfo::default(),
            cors: None,
            supported: None,
            max_body_bytes: DEFAULT_MAX_BODY_BYTES,
            query_defaults: QueryDefaults::default(),
            routes: RouteTable::new(),
            handlers: HashMap::new(),
            describe_routes: true,
        };
        app.register_description();
        app
    }

    /// The same application with another title and version.
    pub fn with_info(mut self, info: ServiceInfo) -> Self {
        self.info = info;
        self
    }

    /// The same application with a CORS policy.
    pub fn with_cors(mut self, cors: CorsPolicy) -> Self {
        self.cors = Some(cors);
        self
    }

    /// The same application producing only these representations.
    pub fn with_supported<I: IntoIterator<Item = String>>(mut self, supported: I) -> Self {
        self.supported = Some(supported.into_iter().collect());
        self
    }

    /// The same application refusing request bodies larger than this.
    pub fn with_max_body_bytes(mut self, max_body_bytes: usize) -> Self {
        self.max_body_bytes = max_body_bytes;
        self
    }

    /// The same application with other collection page-size defaults.
    pub fn with_query_defaults(mut self, query_defaults: QueryDefaults) -> Self {
        self.query_defaults = query_defaults;
        self
    }

    /// The same application without the description routes.
    pub fn without_description(mut self) -> Self {
        self.describe_routes = false;
        self.routes.remove("GET", DESCRIPTION_PATH);
        self.routes.remove("GET", OPENAPI_PATH);
        self
    }

    // Registration -----------------------------------------------------------

    /// Register an asynchronous handler for a method and a path.
    ///
    /// # Panics
    ///
    /// When the method is not one of [`HTTP_METHODS`], which is a mistake in the
    /// program rather than in a request.
    pub fn route<F, Fut, R>(
        &mut self,
        method: &str,
        path: &str,
        summary: &str,
        handler: F,
    ) -> &mut Self
    where
        F: Fn(LinoRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<R, LinoHttpError>> + Send + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        let normalized = method.to_uppercase();
        assert!(
            HTTP_METHODS.contains(&normalized.as_str()),
            "Unsupported HTTP method: {method}"
        );

        self.routes
            .register(&normalized, path, RouteMeta::summary(summary));
        let handler: Handler = Arc::new(move |request| {
            let future = handler(request);
            Box::pin(async move { future.await.map(Into::into) })
        });
        self.handlers
            .insert((normalized, path.to_string()), handler);
        self
    }

    /// Register a synchronous handler for a method and a path.
    pub fn route_fn<F, R>(
        &mut self,
        method: &str,
        path: &str,
        summary: &str,
        handler: F,
    ) -> &mut Self
    where
        F: Fn(LinoRequest) -> Result<R, LinoHttpError> + Send + Sync + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route(method, path, summary, move |request| {
            std::future::ready(handler(request))
        })
    }

    /// Register an asynchronous `GET` handler.
    pub fn get<F, Fut, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<R, LinoHttpError>> + Send + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route("GET", path, summary, handler)
    }

    /// Register an asynchronous `POST` handler.
    pub fn post<F, Fut, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<R, LinoHttpError>> + Send + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route("POST", path, summary, handler)
    }

    /// Register an asynchronous `PUT` handler.
    pub fn put<F, Fut, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<R, LinoHttpError>> + Send + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route("PUT", path, summary, handler)
    }

    /// Register an asynchronous `PATCH` handler.
    pub fn patch<F, Fut, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<R, LinoHttpError>> + Send + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route("PATCH", path, summary, handler)
    }

    /// Register an asynchronous `DELETE` handler.
    pub fn delete<F, Fut, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<R, LinoHttpError>> + Send + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route("DELETE", path, summary, handler)
    }

    /// Register a synchronous `GET` handler.
    pub fn get_fn<F, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Result<R, LinoHttpError> + Send + Sync + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route_fn("GET", path, summary, handler)
    }

    /// Register a synchronous `POST` handler.
    pub fn post_fn<F, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Result<R, LinoHttpError> + Send + Sync + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route_fn("POST", path, summary, handler)
    }

    /// Register a synchronous `PUT` handler.
    pub fn put_fn<F, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Result<R, LinoHttpError> + Send + Sync + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route_fn("PUT", path, summary, handler)
    }

    /// Register a synchronous `PATCH` handler.
    pub fn patch_fn<F, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Result<R, LinoHttpError> + Send + Sync + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route_fn("PATCH", path, summary, handler)
    }

    /// Register a synchronous `DELETE` handler.
    pub fn delete_fn<F, R>(&mut self, path: &str, summary: &str, handler: F) -> &mut Self
    where
        F: Fn(LinoRequest) -> Result<R, LinoHttpError> + Send + Sync + 'static,
        R: Into<LinoResult> + Send + 'static,
    {
        self.route_fn("DELETE", path, summary, handler)
    }

    /// Register the six CRUD routes of a collection backed by a store.
    ///
    /// See [`crate::resource::register_resource`] for the options.
    pub fn resource<S: Store + 'static>(
        &mut self,
        path: &str,
        store: Arc<S>,
        options: ResourceOptions,
    ) -> &mut Self {
        register_resource(self, path, store, options);
        self
    }

    /// Register the service description routes of specification section 9.
    ///
    /// The documents are rendered when they are asked for rather than here,
    /// because they describe every route, including the ones registered after
    /// this call.
    fn register_description(&mut self) {
        self.routes.register(
            "GET",
            DESCRIPTION_PATH,
            RouteMeta::summary("Service description"),
        );
        self.routes.register(
            "GET",
            OPENAPI_PATH,
            RouteMeta::summary("OpenAPI 3.1 description"),
        );
    }

    // Description ------------------------------------------------------------

    /// The native service description of specification section 9.
    pub fn describe(&self) -> LinoValue {
        service_description(
            &self.info,
            &self.routes.describe(),
            self.supported.as_deref(),
        )
    }

    /// The OpenAPI 3.1 rendering of the service description.
    pub fn openapi(&self) -> LinoValue {
        openapi_document(
            &self.info,
            &self.routes.describe(),
            self.supported.as_deref(),
        )
    }

    /// The route table, for inspection.
    pub fn routes(&self) -> &RouteTable {
        &self.routes
    }

    // Request handling -------------------------------------------------------

    /// Run one decoded request through routing and its handler.
    ///
    /// # Errors
    ///
    /// A `404` when no route matches, a `405` when the route does not serve the
    /// method, and anything the handler reports.
    pub async fn handle(&self, mut request: LinoRequest) -> Result<ResponseParts, LinoHttpError> {
        let Some((entry, params)) = self.routes.match_path(&request.path) else {
            return Err(LinoHttpError::new(
                404,
                Some(&format!("No resource at {}", request.path)),
            ));
        };
        request.params = params;
        let pattern = entry.pattern.clone();
        let allowed = self.routes.allowed_methods_of(entry).join(", ");

        let method = request.method.clone();
        // HEAD is served by the GET handler with the body dropped, and OPTIONS is
        // answered from the route table unless a handler claims it.
        let lookup = if method == "HEAD" && entry.has_method("GET") {
            "GET".to_string()
        } else {
            method.clone()
        };

        if method == "OPTIONS" && !entry.has_method("OPTIONS") {
            let mut headers = Headers::new();
            headers.insert("Allow", allowed);
            return Ok(ResponseParts::new(204, headers, ""));
        }

        if !entry.has_method(&lookup) {
            return Err(LinoHttpError::new(
                405,
                Some(&format!("{method} is not allowed on {}", request.path)),
            )
            .with_header("Allow", allowed));
        }

        let result = match self.handlers.get(&(lookup.clone(), pattern.clone())) {
            Some(handler) => handler(request.clone()).await?,
            None => self.describe_route(&pattern)?,
        };

        build_response(
            &result.body,
            result.status,
            result.media_type.as_deref().unwrap_or(&request.media_type),
            &result.headers,
            &request.headers,
            &method,
            EtagPolicy {
                etag: result.etag,
                preconditions: result.preconditions,
                require_precondition: result.require_precondition,
            },
        )
    }

    /// Serve one of the description routes registered by the constructor.
    ///
    /// # Errors
    ///
    /// A `500` when the path has no handler and is not a description route,
    /// which can only happen if the route table and the handlers disagree.
    fn describe_route(&self, pattern: &str) -> Result<LinoResult, LinoHttpError> {
        match pattern {
            DESCRIPTION_PATH if self.describe_routes => Ok(self.describe().into()),
            OPENAPI_PATH if self.describe_routes => Ok(raw_response(
                &format!("{}\n", to_json_pretty(&self.openapi())),
                JSON_CONTENT_TYPE,
                200,
            )),
            other => Err(LinoHttpError::new(
                500,
                Some(&format!("No handler registered for {other}")),
            )),
        }
    }

    /// Answer one raw request, decoding it and rendering any error as problem
    /// details.
    ///
    /// This is the whole application in one call: negotiation, body decoding,
    /// routing, CORS and problem rendering. No error escapes it.
    pub async fn respond(&self, raw: RawRequest) -> ResponseParts {
        let method = raw.method.to_uppercase();
        let extra_headers = match &self.cors {
            Some(policy) => cors_headers(policy, raw.headers.get("origin")),
            None => Headers::new(),
        };
        let preflight =
            method == "OPTIONS" && raw.headers.contains("access-control-request-method");

        let mut media_type = LINO_CONTENT_TYPE.to_string();
        let instance = if raw.query_string.is_empty() {
            raw.path.clone()
        } else {
            format!("{}?{}", raw.path, raw.query_string)
        };

        let mut parts = if preflight && !extra_headers.is_empty() {
            ResponseParts::new(204, Headers::new(), "")
        } else {
            match self.decode_and_handle(&raw, &method, &mut media_type).await {
                Ok(parts) => parts,
                Err(error) => build_problem_response(&error, &media_type, Some(&instance)),
            }
        };

        parts.headers.extend_missing(&extra_headers);
        if extra_headers
            .get("Access-Control-Allow-Origin")
            .is_some_and(|origin| origin != "*")
        {
            append_vary(&mut parts.headers, "Origin");
        }
        if method == "HEAD" {
            parts.body = String::new();
        }
        parts
    }

    /// Negotiate, decode and route one raw request.
    ///
    /// # Errors
    ///
    /// A `406`, a `413`, a `415`, a `400`, or anything routing and the handler
    /// report; [`LinoApp::respond`] turns them into problem details.
    async fn decode_and_handle(
        &self,
        raw: &RawRequest,
        method: &str,
        media_type: &mut String,
    ) -> Result<ResponseParts, LinoHttpError> {
        *media_type = negotiate_request(&raw.headers, self.supported.as_deref())?;
        let decoded = decode_request_body(
            &raw.body,
            raw.headers.get("content-type"),
            self.max_body_bytes,
        )?;

        let mut request = LinoRequest::new(method, &raw.path);
        request.headers = raw.headers.clone();
        request.query_string = raw.query_string.clone();
        request.media_type = media_type.clone();
        request.body = decoded.value;
        request.request_media_type = decoded.media_type;
        request.query_defaults = self.query_defaults;
        self.handle(request).await
    }
}

/// Create a new application, for symmetry with the other packages.
pub fn create_lino_app() -> LinoApp {
    LinoApp::new()
}

/// A body that carries no value, for handlers that answer with a status alone.
pub const EMPTY: Body = Body::Empty;
