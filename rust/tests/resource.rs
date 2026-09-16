//! CRUD resources, ported from `python/tests/test_resource.py`
//! (specification sections 6 and 7).

mod common;

use common::{InProcess, at, items, member, shared};
use lino_objects_codec::LinoValue;
use lino_rest_api::app::LinoApp;
use lino_rest_api::codec::encode;
use lino_rest_api::description::ServiceInfo;
use lino_rest_api::media_type::LINO_CONTENT_TYPE;
use lino_rest_api::resource::ResourceOptions;
use lino_rest_api::store::MemoryStore;
use lino_rest_api::value::{boolean, int, object, string};

/// An application exposing a seeded `/items` resource.
fn items_app(options: ResourceOptions) -> LinoApp {
    let mut app = LinoApp::new().with_info(ServiceInfo::new("Items API", "1.0.0"));
    let store = MemoryStore::seeded([
        object([("name", string("charlie")), ("done", boolean(false))]),
        object([("name", string("alice")), ("done", boolean(true))]),
        object([("name", string("bob")), ("done", boolean(false))]),
    ]);
    app.resource("/items", shared(store), options.with_name("item"));
    app
}

/// The default application, whose resource exposes every operation.
fn default_app() -> InProcess {
    InProcess::new(items_app(ResourceOptions::new()))
}

/// Send a request carrying a Links Notation body.
async fn send(
    api: &InProcess,
    method: &str,
    path: &str,
    body: Option<&LinoValue>,
    extra: &[(&str, &str)],
) -> common::RawResponse {
    let mut headers = vec![("Content-Type", LINO_CONTENT_TYPE)];
    headers.extend_from_slice(extra);
    let encoded = body.map(encode);
    api.raw(method, path, &headers, encoded.as_deref()).await
}

#[tokio::test]
async fn a_collection_is_served_in_the_envelope_of_the_specification() {
    let api = default_app();
    let envelope = api.raw("GET", "/items", &[], None).await.value();
    assert_eq!(items(&envelope).len(), 3);
    assert_eq!(
        member(&envelope, "page"),
        &object([
            ("limit", int(20)),
            ("offset", int(0)),
            ("total", int(3)),
            ("count", int(3)),
        ])
    );
}

#[tokio::test]
async fn a_collection_can_be_filtered_sorted_paginated_and_projected() {
    let api = default_app();
    let response = api
        .raw(
            "GET",
            "/items?done=false&sort=-name&limit=1&fields=name",
            &[],
            None,
        )
        .await;
    let envelope = response.value();
    assert_eq!(
        items(&envelope),
        &vec![object([("name", string("charlie"))])]
    );
    assert_eq!(at(&envelope, &["page", "total"]), &int(2));
    assert!(response.require("link").contains("rel=\"next\""));
}

#[tokio::test]
async fn creating_an_item_answers_201_with_a_location() {
    let api = default_app();
    let response = send(
        &api,
        "POST",
        "/items",
        Some(&object([("name", string("dave"))])),
        &[],
    )
    .await;
    assert_eq!(response.status, 201);
    assert_eq!(response.require("location"), "/items/4");
    assert_eq!(member(&response.value(), "id"), &int(4));
}

#[tokio::test]
async fn creating_an_item_without_a_body_is_a_400() {
    let api = default_app();
    assert_eq!(send(&api, "POST", "/items", None, &[]).await.status, 400);
}

#[tokio::test]
async fn reading_a_missing_item_is_a_404() {
    let api = default_app();
    let response = api.raw("GET", "/items/99", &[], None).await;
    assert_eq!(response.status, 404);
    assert_eq!(member(&response.value(), "title"), &string("Not Found"));
}

#[tokio::test]
async fn a_conditional_read_answers_304() {
    let api = default_app();
    let first = api.raw("GET", "/items/1", &[], None).await;
    let second = api
        .raw(
            "GET",
            "/items/1",
            &[("If-None-Match", first.require("etag"))],
            None,
        )
        .await;
    assert_eq!(second.status, 304);
    assert_eq!(second.text, "");
}

#[tokio::test]
async fn replacing_an_item_requires_a_matching_if_match() {
    let api = default_app();
    let etag = api
        .raw("GET", "/items/1", &[], None)
        .await
        .require("etag")
        .to_string();
    let replacement = object([("name", string("x"))]);

    let stale = send(
        &api,
        "PUT",
        "/items/1",
        Some(&replacement),
        &[("If-Match", "\"stale\"")],
    )
    .await;
    assert_eq!(stale.status, 412);

    let fresh = send(
        &api,
        "PUT",
        "/items/1",
        Some(&replacement),
        &[("If-Match", &etag)],
    )
    .await;
    assert_eq!(fresh.status, 200);
    assert_eq!(
        fresh.value(),
        object([("name", string("x")), ("id", int(1))])
    );
}

#[tokio::test]
async fn a_merge_keeps_the_untouched_members() {
    let api = default_app();
    let response = send(
        &api,
        "PATCH",
        "/items/1",
        Some(&object([("done", boolean(true))])),
        &[],
    )
    .await;
    assert_eq!(
        response.value(),
        object([
            ("name", string("charlie")),
            ("done", boolean(true)),
            ("id", int(1)),
        ])
    );
}

#[tokio::test]
async fn deleting_an_item_answers_204_and_then_404() {
    let api = default_app();
    assert_eq!(api.raw("DELETE", "/items/1", &[], None).await.status, 204);
    assert_eq!(api.raw("GET", "/items/1", &[], None).await.status, 404);
    assert_eq!(api.raw("DELETE", "/items/1", &[], None).await.status, 404);
}

#[tokio::test]
async fn require_precondition_demands_if_match_on_unsafe_methods() {
    let api = InProcess::new(items_app(
        ResourceOptions::new().requiring_precondition(true),
    ));
    let response = send(
        &api,
        "PATCH",
        "/items/1",
        Some(&object([("done", boolean(true))])),
        &[],
    )
    .await;
    assert_eq!(response.status, 428);
    assert_eq!(
        member(&response.value(), "title"),
        &string("Precondition Required")
    );
}

#[tokio::test]
async fn upsert_lets_put_create_a_missing_item() {
    let api = InProcess::new(items_app(ResourceOptions::new().with_upsert(true)));
    let response = send(
        &api,
        "PUT",
        "/items/42",
        Some(&object([("name", string("new"))])),
        &[],
    )
    .await;
    assert_eq!(response.status, 201);
    assert_eq!(response.require("location"), "/items/42");
}

#[tokio::test]
async fn a_subset_of_the_operations_can_be_exposed() {
    let api = InProcess::new(items_app(
        ResourceOptions::new().with_operations(["list", "get"]),
    ));
    let options = api.raw("OPTIONS", "/items", &[], None).await;
    assert_eq!(options.require("allow"), "GET, HEAD, OPTIONS");
    assert_eq!(
        send(
            &api,
            "POST",
            "/items",
            Some(&object([("name", string("x"))])),
            &[],
        )
        .await
        .status,
        405
    );
}

#[tokio::test]
async fn the_resource_name_appears_in_problem_details() {
    let api = default_app();
    let problem = api.raw("GET", "/items/99", &[], None).await.value();
    assert_eq!(
        member(&problem, "detail"),
        &string("item 99 does not exist")
    );
}
