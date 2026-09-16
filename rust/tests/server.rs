//! The axum shell, ported from `python/tests/test_server.py`.
//!
//! Every other HTTP test in this suite drives [`LinoApp::respond`] in process,
//! which is fast but never touches a TCP connection or an HTTP parser. This
//! module runs the real server on an ephemeral port so that those layers are
//! covered too.

// A handler reports a `LinoHttpError`, which is larger than clippy's threshold
// for an error type; the crate allows it at its root for the same reason.
#![allow(clippy::result_large_err)]

mod common;

use common::{Served, at, member};
use lino_rest_api::app::{LinoApp, create_lino_app};
use lino_rest_api::codec::decode;
use lino_rest_api::cors::CorsPolicy;
use lino_rest_api::description::ServiceInfo;
use lino_rest_api::media_type::LINO_CONTENT_TYPE;
use lino_rest_api::resource::ResourceOptions;
use lino_rest_api::serve::BoundServer;
use lino_rest_api::store::MemoryStore;
use lino_rest_api::value::{boolean, int, object, string};

/// The application served over a real socket.
fn build_app() -> LinoApp {
    let mut app = create_lino_app()
        .with_info(ServiceInfo::new("Live API", "1.0.0"))
        .with_cors(CorsPolicy::permissive());
    let store = MemoryStore::seeded([object([("name", string("first"))])]);
    app.resource(
        "/items",
        common::shared(store),
        ResourceOptions::new().with_name("item"),
    );
    app.get_fn("/health", "Health check", |_request| {
        Ok(object([("status", string("ok"))]))
    });
    app
}

/// Start the application on an ephemeral port.
async fn live() -> Served {
    Served::start(build_app()).await
}

/// No options at all, which is what most calls send.
fn plain() -> lino_rest_api::client::RequestOptions {
    lino_rest_api::client::RequestOptions::new()
}

#[tokio::test]
async fn the_server_answers_over_a_real_socket() {
    let api = live().await;
    let response = api
        .client
        .get("/health", &plain())
        .await
        .expect("an answer");
    assert_eq!(response.status, 200);
    assert_eq!(response.value(), object([("status", string("ok"))]));
    assert_eq!(
        response.headers.get("content-type"),
        Some("text/lino; charset=utf-8")
    );
}

#[tokio::test]
async fn the_client_drives_a_full_resource_lifecycle() {
    let api = live().await;
    let created = api
        .client
        .post(
            "/items",
            &object([("name", string("second")), ("done", boolean(false))]),
            &plain(),
        )
        .await
        .expect("an item is created");
    assert_eq!(created.status, 201);
    let location = created.location.clone().expect("a Location header");
    assert_eq!(
        location,
        format!("/items/{}", common::text(&created.value(), "id"))
    );

    let read = api.client.get(&location, &plain()).await.expect("the item");
    assert_eq!(read.value(), created.value());
    assert_eq!(read.etag, created.etag);

    let merged = api
        .client
        .patch(
            &location,
            &object([("done", boolean(true))]),
            &plain().if_match(read.etag.clone().expect("a strong tag")),
        )
        .await
        .expect("the precondition holds");
    assert_eq!(member(&merged.value(), "done"), &boolean(true));

    assert_eq!(
        api.client
            .delete(&location, &plain())
            .await
            .expect("a deletion")
            .status,
        204
    );
    let missing = api
        .client
        .get(&location, &plain())
        .await
        .expect_err("the item is gone");
    assert_eq!(missing.status(), Some(404));
}

#[tokio::test]
async fn the_client_reads_the_description_and_the_methods() {
    let api = live().await;
    let description = api.client.describe().await.expect("a description");
    assert_eq!(at(&description, &["info", "title"]), &string("Live API"));
    assert_eq!(
        api.client
            .options("/health", &plain())
            .await
            .expect("an answer"),
        vec!["GET", "HEAD", "OPTIONS"]
    );
}

#[tokio::test]
async fn a_conditional_read_over_a_real_socket_answers_304() {
    let api = live().await;
    let first = api
        .client
        .get("/items/1", &plain())
        .await
        .expect("the item");
    let cached = api
        .client
        .get(
            "/items/1",
            &plain().if_none_match(first.etag.clone().expect("a strong tag")),
        )
        .await
        .expect("a conditional read");
    assert_eq!(cached.status, 304);
    assert_eq!(cached.data, None);
}

#[tokio::test]
async fn a_raw_request_carries_the_expected_headers() {
    let api = live().await;
    let response = api
        .raw(
            "GET",
            "/items/1",
            &[
                ("Accept", LINO_CONTENT_TYPE),
                ("Origin", "https://example.com"),
            ],
            None,
        )
        .await;
    assert_eq!(response.status, 200);
    assert_eq!(response.require("access-control-allow-origin"), "*");
    assert!(!response.vary_fields().is_empty());
    assert_eq!(
        member(&decode(&response.text).expect("a well-formed body"), "name"),
        &string("first")
    );
}

#[tokio::test]
async fn a_preflight_is_answered_before_the_route_is_looked_up() {
    let api = live().await;
    let response = api
        .raw(
            "OPTIONS",
            "/items",
            &[
                ("Origin", "https://example.com"),
                ("Access-Control-Request-Method", "POST"),
            ],
            None,
        )
        .await;
    assert_eq!(response.status, 204);
    assert_eq!(response.require("access-control-allow-origin"), "*");
    assert!(
        response
            .require("access-control-allow-methods")
            .contains("POST")
    );
}

#[tokio::test]
async fn an_unknown_path_is_a_problem_document_over_the_socket() {
    let api = live().await;
    let response = api.raw("GET", "/nothing/here", &[], None).await;
    assert_eq!(response.status, 404);
    assert_eq!(response.content_type(), "application/problem+lino");
    assert_eq!(member(&response.lino(), "status"), &int(404));
}

#[tokio::test]
async fn a_body_sent_over_the_socket_reaches_the_handler() {
    let api = live().await;
    let response = api
        .raw(
            "POST",
            "/items",
            &[
                ("Content-Type", LINO_CONTENT_TYPE),
                ("Accept", LINO_CONTENT_TYPE),
            ],
            Some("(\n  name \"over the wire\"\n)"),
        )
        .await;
    assert_eq!(response.status, 201);
    assert_eq!(member(&response.value(), "name"), &string("over the wire"));
}

#[tokio::test]
async fn binding_reports_the_port_that_was_chosen() {
    let server = BoundServer::bind(build_app(), "127.0.0.1:0")
        .await
        .expect("an ephemeral port is available");
    assert_ne!(server.address.port(), 0);
    assert_eq!(server.base_url(), format!("http://{}", server.address));
}
