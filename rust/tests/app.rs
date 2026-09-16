//! The application itself, ported from `python/tests/test_app.py`.
//!
//! The Python package is an ASGI application, so its suite also drives the
//! lifespan protocol; the Rust application is a plain request handler, and
//! [`crate::serve`] is what carries it over HTTP, so those tests live in
//! `tests/server.rs` instead. A handler here returns an error rather than
//! raising one, so there is no traceback to expose either.

// A handler reports a `LinoHttpError`, which is larger than clippy's threshold
// for an error type; the crate allows it at its root for the same reason.
#![allow(clippy::result_large_err)]

mod common;

use common::{InProcess, at, member};
use lino_objects_codec::LinoValue;
use lino_rest_api::app::{DESCRIPTION_PATH, LinoApp, OPENAPI_PATH, RawRequest, create_lino_app};
use lino_rest_api::codec::encode;
use lino_rest_api::description::ServiceInfo;
use lino_rest_api::media_type::LINO_CONTENT_TYPE;
use lino_rest_api::problem::LinoHttpError;
use lino_rest_api::response::{created, no_content, raw_response, status};
use lino_rest_api::value::{array, as_array, boolean, int, object, string};

/// An application exercising the whole surface.
fn build_app() -> LinoApp {
    let mut app = create_lino_app().with_info(ServiceInfo::new("Test API", "2.0.0"));
    app.get_fn("/health", "Health check", |_request| {
        Ok(object([("status", string("ok"))]))
    });
    app.post_fn("/echo", "Echo the body", |request| {
        Ok(created(
            object([("echoed", request.body.clone().unwrap_or(LinoValue::Null))]),
            "/echo/1",
        ))
    });
    app.put_fn("/replace", "Replace the body", |request| {
        Ok(object([(
            "replaced",
            request.body.clone().unwrap_or(LinoValue::Null),
        )]))
    });
    app.patch_fn("/merge", "Merge the body", |request| {
        Ok(status(
            202,
            object([("queued", request.body.clone().unwrap_or(LinoValue::Null))]),
        ))
    });
    app.delete_fn("/gone", "Delete", |_request| Ok(no_content()));
    app.get_fn("/boom", "Fail", |_request| {
        Err::<LinoValue, _>(LinoHttpError::new(409, Some("Already exists")))
    });
    app.get_fn("/raw", "A pre-encoded body", |_request| {
        Ok(raw_response(
            &encode(&object([("raw", boolean(true))])),
            LINO_CONTENT_TYPE,
            200,
        ))
    });
    app
}

#[test]
fn create_lino_app_returns_an_application_serving_its_own_description() {
    let app = create_lino_app();
    assert!(app.routes().find(DESCRIPTION_PATH).is_some());
    assert!(app.routes().find(OPENAPI_PATH).is_some());
}

#[test]
fn route_registration_is_chainable() {
    let mut app = create_lino_app();
    app.get_fn("/a", "A", |_request| Ok(LinoValue::Object(Vec::new())))
        .post_fn("/a", "A", |_request| Ok(LinoValue::Object(Vec::new())));
    assert_eq!(
        app.routes().allowed_methods("/a"),
        Some(vec![
            "GET".to_string(),
            "HEAD".to_string(),
            "OPTIONS".to_string(),
            "POST".to_string(),
        ])
    );
}

#[test]
#[should_panic(expected = "Unsupported HTTP method: TRACE")]
fn registering_an_unknown_method_is_a_programming_error() {
    create_lino_app().route_fn("TRACE", "/a", "Trace", |_request| {
        Ok(LinoValue::Object(Vec::new()))
    });
}

#[tokio::test]
async fn a_handler_return_value_is_encoded_as_links_notation() {
    let api = InProcess::new(build_app());
    let response = api.raw("GET", "/health", &[], None).await;
    assert_eq!(response.status, 200);
    assert_eq!(response.require("content-type"), "text/lino; charset=utf-8");
    assert_eq!(response.require("vary"), "Accept");
    assert_eq!(response.value(), object([("status", string("ok"))]));
}

#[tokio::test]
async fn a_request_body_is_decoded_from_links_notation() {
    let api = InProcess::new(build_app());
    let body = object([("name", string("Alice"))]);
    let response = api
        .raw(
            "POST",
            "/echo",
            &[("Content-Type", LINO_CONTENT_TYPE)],
            Some(&encode(&body)),
        )
        .await;
    assert_eq!(response.status, 201);
    assert_eq!(response.require("location"), "/echo/1");
    assert_eq!(response.value(), object([("echoed", body)]));
}

#[tokio::test]
async fn explicit_results_carry_their_status_code() {
    let api = InProcess::new(build_app());
    let accepted = api
        .raw(
            "PATCH",
            "/merge",
            &[("Content-Type", LINO_CONTENT_TYPE)],
            Some(&encode(&object([("a", int(1))]))),
        )
        .await;
    assert_eq!(accepted.status, 202);

    let deleted = api.raw("DELETE", "/gone", &[], None).await;
    assert_eq!(deleted.status, 204);
    assert_eq!(deleted.text, "");
}

#[tokio::test]
async fn a_handler_may_encode_the_response_itself() {
    let api = InProcess::new(build_app());
    let response = api.raw("GET", "/raw", &[], None).await;
    assert_eq!(response.value(), object([("raw", boolean(true))]));
}

#[tokio::test]
async fn an_asynchronous_handler_is_awaited() {
    let mut app = create_lino_app();
    app.get("/async", "Asynchronous", |_request| async {
        Ok(object([("asynchronous", boolean(true))]))
    });
    let api = InProcess::new(app);
    assert_eq!(
        api.raw("GET", "/async", &[], None).await.value(),
        object([("asynchronous", boolean(true))])
    );
}

#[tokio::test]
async fn a_handler_returning_nothing_answers_204() {
    let mut app = create_lino_app();
    app.get_fn("/nothing", "Nothing", |_request| Ok(()));
    let api = InProcess::new(app);
    let response = api.raw("GET", "/nothing", &[], None).await;
    assert_eq!(response.status, 204);
    assert_eq!(response.text, "");
}

#[tokio::test]
async fn a_returned_error_becomes_problem_details() {
    let api = InProcess::new(build_app());
    let response = api.raw("GET", "/boom", &[], None).await;
    assert_eq!(response.status, 409);
    assert_eq!(
        response.require("content-type"),
        "application/problem+lino; charset=utf-8"
    );
    let problem = response.value();
    assert_eq!(member(&problem, "status"), &int(409));
    assert_eq!(member(&problem, "title"), &string("Conflict"));
    assert_eq!(member(&problem, "instance"), &string("/boom"));
}

#[tokio::test]
async fn the_service_description_reflects_the_registered_routes() {
    let api = InProcess::new(build_app());
    let description = api.raw("GET", DESCRIPTION_PATH, &[], None).await.value();
    assert_eq!(at(&description, &["info", "title"]), &string("Test API"));
    assert_eq!(at(&description, &["info", "version"]), &string("2.0.0"));
    let routes = as_array(member(&description, "routes")).expect("routes is an array");
    let health = routes
        .iter()
        .find(|route| member(route, "path") == &string("/health"))
        .expect("the health route is described");
    assert_eq!(member(health, "summary"), &string("Health check"));
    assert_eq!(
        member(health, "methods"),
        &array([string("GET"), string("HEAD"), string("OPTIONS")])
    );
}

#[tokio::test]
async fn the_openapi_document_is_served_as_json() {
    let api = InProcess::new(build_app());
    let response = api.raw("GET", OPENAPI_PATH, &[], None).await;
    assert_eq!(
        response.require("content-type"),
        "application/json; charset=utf-8"
    );
    let document = response.json();
    assert_eq!(member(&document, "openapi"), &string("3.1.0"));
    assert!(matches!(
        at(&document, &["paths", "/health", "get"]),
        LinoValue::Object(_)
    ));
}

#[tokio::test]
async fn the_description_can_be_turned_off() {
    let mut app = create_lino_app().without_description();
    app.get_fn("/health", "Health check", |_request| {
        Ok(object([("status", string("ok"))]))
    });
    let api = InProcess::new(app);
    assert_eq!(
        api.raw("GET", DESCRIPTION_PATH, &[], None).await.status,
        404
    );
}

#[tokio::test]
async fn an_unknown_path_is_a_problem_shaped_404() {
    let api = InProcess::new(build_app());
    let response = api.raw("GET", "/nothing/here", &[], None).await;
    assert_eq!(response.status, 404);
    assert_eq!(response.content_type(), "application/problem+lino");
}

#[tokio::test]
async fn the_query_string_of_a_request_reaches_the_problem_instance() {
    let api = InProcess::new(build_app());
    let response = api
        .send(RawRequest::new("GET", "/nothing/here").with_query("a=1"))
        .await;
    assert_eq!(
        member(&response.value(), "instance"),
        &string("/nothing/here?a=1")
    );
}
