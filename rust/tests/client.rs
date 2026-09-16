//! The client, ported from `python/tests/test_client.py`
//! (specification section 10).
//!
//! Every test here talks to a real server on an ephemeral port, because the
//! Rust client is built on `reqwest` and has no in-process transport to
//! shortcut through the way the Python suite does. There is only one client
//! rather than a synchronous and an asynchronous one, so the Python tests that
//! compare the two surfaces have no counterpart.

// A handler reports a `LinoHttpError`, which is larger than clippy's threshold
// for an error type; the crate allows it at its root for the same reason.
#![allow(clippy::result_large_err)]

mod common;

use common::{Served, at, items, member};
use lino_objects_codec::LinoValue;
use lino_rest_api::app::{LinoApp, create_lino_app};
use lino_rest_api::client::{
    DEFAULT_ACCEPT, LinoClient, LinoClientError, RequestOptions, create_lino_client,
};
use lino_rest_api::description::ServiceInfo;
use lino_rest_api::media_type::{JSON_CONTENT_TYPE, LINO_CONTENT_TYPE};
use lino_rest_api::problem::LinoHttpError;
use lino_rest_api::resource::ResourceOptions;
use lino_rest_api::response::{no_content, raw_response};
use lino_rest_api::store::MemoryStore;
use lino_rest_api::value::{array, as_array, boolean, int, object, string};

/// An application the client can talk to.
fn build_app() -> LinoApp {
    let mut app = create_lino_app().with_info(ServiceInfo::new("Items API", "1.0.0"));
    let store = MemoryStore::seeded([object([("name", string("first"))])]);
    app.resource(
        "/items",
        common::shared(store),
        ResourceOptions::new().with_name("item"),
    );
    app.get_fn("/health", "Health check", |_request| {
        Ok(object([("status", string("ok"))]))
    });
    app.get_fn("/empty", "Nothing at all", |_request| Ok(no_content()));
    app.get_fn("/boom", "Always conflicts", |_request| {
        Err::<LinoValue, _>(LinoHttpError::new(409, Some("Already exists")))
    });
    app
}

/// No options at all, which is what most calls send.
fn plain() -> RequestOptions {
    RequestOptions::new()
}

#[test]
fn the_client_asks_for_links_notation_first() {
    assert_eq!(DEFAULT_ACCEPT, "text/lino, application/json;q=0.5");
    // The constant is spelled out in the source, so the media types it names
    // are checked against the constants the rest of the crate uses.
    assert!(DEFAULT_ACCEPT.starts_with(LINO_CONTENT_TYPE));
    assert!(DEFAULT_ACCEPT.contains(JSON_CONTENT_TYPE));
}

#[test]
fn a_trailing_slash_on_the_base_url_is_not_repeated_in_every_path() {
    let client = create_lino_client("http://example.com/");
    assert_eq!(client.base_url(), "http://example.com");
    assert_eq!(
        LinoClient::new("http://example.com").base_url(),
        "http://example.com"
    );
}

#[test]
fn query_strings_expand_repeated_values() {
    assert_eq!(plain().query.to_query_string(), "");
    let options = plain()
        .with_query("a", &int(1))
        .with_query("b", &int(2))
        .with_query("b", &int(3));
    assert_eq!(options.query.to_query_string(), "a=1&b=2&b=3");
}

#[test]
fn query_strings_spell_booleans_the_way_the_filters_read_them() {
    // Rust would render `false` as "false" anyway, but the spelling is what a
    // filter of section 6.1 matches, so it is asserted rather than assumed.
    let options = plain()
        .with_query("done", &boolean(false))
        .with_query("ok", &boolean(true));
    assert_eq!(options.query.to_query_string(), "done=false&ok=true");
}

#[tokio::test]
async fn the_client_encodes_requests_and_decodes_responses() {
    let api = Served::start(build_app()).await;

    let health = api
        .client
        .get("/health", &plain())
        .await
        .expect("a health check");
    assert_eq!(health.status, 200);
    assert_eq!(health.value(), object([("status", string("ok"))]));

    let created = api
        .client
        .post("/items", &object([("name", string("second"))]), &plain())
        .await
        .expect("an item is created");
    assert_eq!(created.status, 201);
    assert_eq!(created.location.as_deref(), Some("/items/2"));
    assert_eq!(member(&created.value(), "name"), &string("second"));
}

#[tokio::test]
async fn a_4xx_raises_a_typed_error_carrying_the_problem_details() {
    let api = Served::start(build_app()).await;
    let error = api
        .client
        .get("/boom", &plain())
        .await
        .expect_err("the route always conflicts");
    assert_eq!(error.status(), Some(409));
    let problem = error.problem().expect("the body carries problem details");
    assert_eq!(member(problem, "title"), &string("Conflict"));
    assert_eq!(error.to_string(), "Already exists");
}

#[tokio::test]
async fn a_204_is_the_absence_of_a_representation_not_a_null_one() {
    let api = Served::start(build_app()).await;
    let response = api.client.get("/empty", &plain()).await.expect("an answer");
    assert_eq!(response.status, 204);
    assert_eq!(response.data, None);
    assert_eq!(response.value(), LinoValue::Null);
}

#[tokio::test]
async fn the_client_honours_conditional_requests() {
    let api = Served::start(build_app()).await;
    let first = api
        .client
        .get("/items/1", &plain())
        .await
        .expect("the item");
    let tag = first.etag.clone().expect("a strong tag");

    let cached = api
        .client
        .get("/items/1", &plain().if_none_match(tag.clone()))
        .await
        .expect("a conditional read");
    assert_eq!(cached.status, 304);
    assert_eq!(cached.data, None);

    let updated = api
        .client
        .patch(
            "/items/1",
            &object([("done", boolean(true))]),
            &plain().if_match(tag.clone()),
        )
        .await
        .expect("the precondition holds");
    assert_eq!(member(&updated.value(), "done"), &boolean(true));

    let stale = api
        .client
        .patch(
            "/items/1",
            &object([("done", boolean(false))]),
            &plain().if_match(tag),
        )
        .await
        .expect_err("the representation has changed");
    assert_eq!(stale.status(), Some(412));
}

#[tokio::test]
async fn the_client_can_list_a_collection() {
    let api = Served::start(build_app()).await;
    let envelope = api
        .client
        .list("/items", &plain().with_query("limit", &int(1)))
        .await
        .expect("a collection");
    assert_eq!(items(&envelope).len(), 1);
    assert_eq!(at(&envelope, &["page", "limit"]), &int(1));
}

#[tokio::test]
async fn the_client_reads_the_advertised_methods() {
    let api = Served::start(build_app()).await;
    assert_eq!(
        api.client
            .options("/health", &plain())
            .await
            .expect("an answer"),
        vec!["GET", "HEAD", "OPTIONS"]
    );
}

#[tokio::test]
async fn head_yields_headers_without_a_body() {
    let api = Served::start(build_app()).await;
    let response = api
        .client
        .head("/health", &plain())
        .await
        .expect("an answer");
    assert_eq!(response.status, 200);
    assert_eq!(response.data, None);
    assert!(response.etag.is_some());
}

#[tokio::test]
async fn the_client_can_read_the_service_description() {
    let api = Served::start(build_app()).await;
    let description = api.client.describe().await.expect("a description");
    assert_eq!(at(&description, &["info", "title"]), &string("Items API"));
    let routes = as_array(member(&description, "routes")).expect("routes is a list");
    assert!(
        routes
            .iter()
            .any(|route| member(route, "path") == &string("/items"))
    );
}

#[tokio::test]
async fn the_request_representation_can_be_switched_to_json() {
    let api = Served::start(build_app()).await;
    let client = LinoClient::new(api.base.clone())
        .with_accept(JSON_CONTENT_TYPE)
        .with_content_type(JSON_CONTENT_TYPE);
    let created = client
        .post("/items", &object([("name", string("json"))]), &plain())
        .await
        .expect("an item is created");
    assert_eq!(created.status, 201);
    assert_eq!(
        created.headers.get("content-type"),
        Some("application/json; charset=utf-8")
    );
    assert_eq!(member(&created.value(), "name"), &string("json"));
}

#[tokio::test]
async fn the_client_deletes_a_resource() {
    let api = Served::start(build_app()).await;
    assert_eq!(
        api.client
            .delete("/items/1", &plain())
            .await
            .expect("a deletion")
            .status,
        204
    );
    let missing = api
        .client
        .get("/items/1", &plain())
        .await
        .expect_err("the item is gone");
    assert_eq!(missing.status(), Some(404));
}

#[tokio::test]
async fn a_boolean_filter_is_sent_in_the_spelling_the_server_parses() {
    let mut app = create_lino_app();
    let store = MemoryStore::seeded([
        object([("name", string("open")), ("done", boolean(false))]),
        object([("name", string("shut")), ("done", boolean(true))]),
    ]);
    app.resource("/items", common::shared(store), ResourceOptions::new());
    let api = Served::start(app).await;

    let envelope = api
        .client
        .list("/items", &plain().with_query("done", &boolean(false)))
        .await
        .expect("a collection");
    let names: Vec<&LinoValue> = items(&envelope)
        .iter()
        .map(|item| member(item, "name"))
        .collect();
    assert_eq!(names, vec![&string("open")]);
}

#[tokio::test]
async fn a_client_header_is_sent_with_every_request() {
    let mut app = LinoApp::new();
    app.get_fn("/echo-header", "Echo a request header", |request| {
        Ok(object([(
            "seen",
            request
                .headers
                .get("X-Trace")
                .map(string)
                .unwrap_or(LinoValue::Null),
        )]))
    });
    let api = Served::start(app).await;
    let client = LinoClient::new(api.base.clone()).with_header("X-Trace", "abc");

    let response = client
        .get("/echo-header", &plain())
        .await
        .expect("an answer");
    assert_eq!(member(&response.value(), "seen"), &string("abc"));

    // A per-call header overrides the one the client always sends.
    let overridden = client
        .get("/echo-header", &plain().with_header("X-Trace", "xyz"))
        .await
        .expect("an answer");
    assert_eq!(member(&overridden.value(), "seen"), &string("xyz"));
}

#[tokio::test]
async fn a_representation_the_client_cannot_decode_is_handed_over_as_text() {
    // A service may answer with a representation of its own choosing; rather
    // than fail, the client hands the body over as text (section 10).
    let mut app = LinoApp::new();
    app.get_fn("/report", "A report", |_request| {
        Ok(raw_response("name,id\nfirst,1\n", "text/csv", 200))
    });
    let api = Served::start(app).await;

    let response = api
        .client
        .get("/report", &plain())
        .await
        .expect("an answer");
    assert_eq!(response.status, 200);
    assert_eq!(response.data, None);
    assert_eq!(response.text, "name,id\nfirst,1\n");
}

#[tokio::test]
async fn a_transport_failure_is_reported_as_such() {
    // Port 1 on the loopback interface is not listening, so the request never
    // reaches a service and there is no problem document to decode.
    let client = LinoClient::new("http://127.0.0.1:1");
    let error = client
        .get("/health", &plain())
        .await
        .expect_err("nothing is listening");
    assert!(matches!(error, LinoClientError::Transport(_)));
    assert_eq!(error.status(), None);
    assert_eq!(error.problem(), None);
}

#[tokio::test]
async fn query_parameters_survive_the_round_trip_to_the_server() {
    let mut app = LinoApp::new();
    app.get_fn("/echo-query", "Echo the query", |request| {
        Ok(object([(
            "tags",
            array(
                request
                    .query()
                    .get_all("tag")
                    .into_iter()
                    .map(string)
                    .collect::<Vec<_>>(),
            ),
        )]))
    });
    let api = Served::start(app).await;

    let response = api
        .client
        .get(
            "/echo-query",
            &plain()
                .with_query_text("tag", "a b")
                .with_query_text("tag", "é"),
        )
        .await
        .expect("an answer");
    assert_eq!(
        member(&response.value(), "tags"),
        &array([string("a b"), string("é")])
    );
}
