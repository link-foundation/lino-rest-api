//! Running an application over HTTP.
//!
//! The application itself knows nothing about sockets: it turns a [`RawRequest`]
//! into [`crate::middleware::ResponseParts`]. This module is the shell that
//! carries those over HTTP, built on axum, and it is the only place in the crate
//! that depends on a server.

use std::net::SocketAddr;
use std::sync::Arc;

use axum::Router;
use axum::body::{Body, Bytes};
use axum::extract::State;
use axum::http::{HeaderName, HeaderValue, Method, Response, StatusCode, Uri};
use tokio::net::TcpListener;

use crate::app::{LinoApp, RawRequest};

/// Build the axum router that serves an application.
///
/// Every method and every path reaches the application, which does its own
/// routing and answers a `404` or a `405` itself, with problem details and an
/// `Allow` header, as the specification requires.
pub fn router(app: Arc<LinoApp>) -> Router {
    Router::new().fallback(dispatch).with_state(app)
}

/// Serve one request through the application.
async fn dispatch(
    State(app): State<Arc<LinoApp>>,
    method: Method,
    uri: Uri,
    headers: axum::http::HeaderMap,
    body: Bytes,
) -> Response<Body> {
    let mut raw = RawRequest::new(method.as_str(), uri.path());
    raw.query_string = uri.query().unwrap_or_default().to_string();
    for (name, value) in &headers {
        raw.headers
            .insert(name.as_str(), value.to_str().unwrap_or_default());
    }
    raw.body = body.to_vec();

    let parts = app.respond(raw).await;
    let status = StatusCode::from_u16(parts.status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    let mut response = Response::builder().status(status);
    for (name, value) in parts.headers.iter() {
        // A header the application could not have produced is dropped rather
        // than allowed to fail the whole response.
        if let (Ok(name), Ok(value)) = (
            HeaderName::from_bytes(name.as_bytes()),
            HeaderValue::from_str(value),
        ) {
            response = response.header(name, value);
        }
    }
    response
        .body(Body::from(parts.body))
        .unwrap_or_else(|_| Response::new(Body::empty()))
}

/// An application bound to a port, before it starts serving.
///
/// Binding and serving are separate so that a test can bind port `0`, read the
/// port that was chosen and then serve in the background.
pub struct BoundServer {
    /// The address the server listens on.
    pub address: SocketAddr,
    listener: TcpListener,
    router: Router,
}

impl BoundServer {
    /// Bind an application to an address.
    ///
    /// # Errors
    ///
    /// Whatever binding the socket reports.
    pub async fn bind(app: LinoApp, address: &str) -> std::io::Result<Self> {
        let listener = TcpListener::bind(address).await?;
        Ok(Self {
            address: listener.local_addr()?,
            listener,
            router: router(Arc::new(app)),
        })
    }

    /// The base URL of the bound server, as a client needs it.
    pub fn base_url(&self) -> String {
        format!("http://{}", self.address)
    }

    /// Serve until the process ends.
    ///
    /// # Errors
    ///
    /// Whatever the server reports while accepting connections.
    pub async fn serve(self) -> std::io::Result<()> {
        axum::serve(self.listener, self.router).await
    }
}

/// Bind an application to an address and serve it.
///
/// # Errors
///
/// Whatever binding the socket or accepting a connection reports.
///
/// # Examples
///
/// ```no_run
/// use lino_rest_api::app::LinoApp;
/// use lino_rest_api::serve::serve;
///
/// # async fn run() -> std::io::Result<()> {
/// serve(LinoApp::new(), "0.0.0.0:8000").await
/// # }
/// ```
pub async fn serve(app: LinoApp, address: &str) -> std::io::Result<()> {
    BoundServer::bind(app, address).await?.serve().await
}
