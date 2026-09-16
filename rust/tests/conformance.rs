//! The conformance checklist of the specification (section 11), one test per
//! item, mirroring `python/tests/test_conformance.py` and the JavaScript suite.
//!
//! Every test drives a complete application over a real socket, so they double
//! as the executable definition of "this implementation conforms".

mod common;

use std::sync::Arc;

use lino_objects_codec::LinoValue;
use lino_rest_api::{
    CorsPolicy, JSON_CONTENT_TYPE, LINO_COMPACT_CONTENT_TYPE, LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE, LinoApp, LinoClientError, MemoryStore, RequestOptions, ResourceOptions,
    ServiceInfo, array, decode_from, encode_for, encode_single_line, int, object, string,
};

use common::{Served, at, items, member, text};

/// The first item of the seeded collection, as stored.
///
/// The members are in creation order, with the assigned identifier last, which
/// is what the JavaScript and Python stores produce too; comparing the whole
/// value therefore also checks that the three implementations agree on the bytes
/// an entity tag is computed over.
fn first_item() -> LinoValue {
    object([
        ("name", string("first")),
        ("tag", string("a")),
        ("rank", int(2)),
        ("id", int(1)),
    ])
}

/// Build the application every conformance test runs against.
fn build_app() -> LinoApp {
    let mut app = LinoApp::new()
        .with_info(ServiceInfo::new("Conformance API", "1.0.0"))
        .with_cors(CorsPolicy::permissive());
    let items = MemoryStore::seeded([
        object([
            ("name", string("first")),
            ("tag", string("a")),
            ("rank", int(2)),
        ]),
        object([
            ("name", string("second")),
            ("tag", string("b")),
            ("rank", int(1)),
        ]),
        object([
            ("name", string("third")),
            ("tag", string("a")),
            ("rank", int(3)),
        ]),
    ]);
    app.resource(
        "/items",
        Arc::new(items),
        ResourceOptions::new().with_name("item"),
    );
    app
}

#[tokio::test]
async fn test_1_text_lino_is_decoded_on_requests_and_encoded_on_responses() {
    let api = Served::start(build_app()).await;
    let body = encode_for(
        &object([("name", string("fourth")), ("tag", string("c"))]),
        LINO_CONTENT_TYPE,
    )
    .unwrap();

    let response = api
        .raw(
            "POST",
            "/items",
            &[
                ("Content-Type", LINO_CONTENT_TYPE),
                ("Accept", LINO_CONTENT_TYPE),
            ],
            Some(&body),
        )
        .await;

    assert_eq!(response.status, 201);
    assert!(
        response
            .require("content-type")
            .starts_with(LINO_CONTENT_TYPE)
    );
    let created = decode_from(&response.text, LINO_CONTENT_TYPE).unwrap();
    assert_eq!(text(&created, "name"), "fourth");
    assert_eq!(text(&created, "tag"), "c");
}

#[tokio::test]
async fn test_2_the_single_line_and_compact_representations_are_negotiable() {
    let api = Served::start(build_app()).await;

    let line = api
        .raw(
            "GET",
            "/items/1",
            &[("Accept", LINO_LINE_CONTENT_TYPE)],
            None,
        )
        .await;
    assert_eq!(line.content_type(), LINO_LINE_CONTENT_TYPE);
    assert!(!line.text.contains('\n'));
    assert_eq!(
        decode_from(&line.text, LINO_LINE_CONTENT_TYPE).unwrap(),
        first_item()
    );

    let compact = api
        .raw(
            "GET",
            "/items/1",
            &[("Accept", LINO_COMPACT_CONTENT_TYPE)],
            None,
        )
        .await;
    assert_eq!(compact.content_type(), LINO_COMPACT_CONTENT_TYPE);
    assert_eq!(
        decode_from(&compact.text, LINO_COMPACT_CONTENT_TYPE).unwrap(),
        first_item()
    );
}

#[tokio::test]
async fn test_3_application_json_remains_available_as_a_fallback() {
    let api = Served::start(build_app()).await;

    let response = api
        .raw("GET", "/items/1", &[("Accept", JSON_CONTENT_TYPE)], None)
        .await;
    assert_eq!(response.content_type(), JSON_CONTENT_TYPE);
    assert_eq!(response.json(), first_item());

    let sent = api
        .raw(
            "POST",
            "/items",
            &[
                ("Content-Type", JSON_CONTENT_TYPE),
                ("Accept", JSON_CONTENT_TYPE),
            ],
            Some(r#"{"name":"json"}"#),
        )
        .await;
    assert_eq!(sent.status, 201);
    assert_eq!(text(&sent.json(), "name"), "json");
}

#[tokio::test]
async fn test_4_accept_quality_values_select_a_representation_406_and_vary_accept() {
    let api = Served::start(build_app()).await;

    let accept = format!("{JSON_CONTENT_TYPE};q=0.4, {LINO_LINE_CONTENT_TYPE};q=0.9");
    let negotiated = api
        .raw("GET", "/items/1", &[("Accept", accept.as_str())], None)
        .await;
    assert_eq!(negotiated.content_type(), LINO_LINE_CONTENT_TYPE);
    assert!(negotiated.vary_fields().contains(&"accept".to_string()));

    let unacceptable = api
        .raw("GET", "/items/1", &[("Accept", "image/png")], None)
        .await;
    assert_eq!(unacceptable.status, 406);
    let problem = unacceptable.lino();
    assert!(supported_contains(&problem, LINO_CONTENT_TYPE));
}

#[tokio::test]
async fn test_5_an_unsupported_request_media_type_is_a_415() {
    let api = Served::start(build_app()).await;

    let response = api
        .raw(
            "POST",
            "/items",
            &[
                ("Content-Type", "application/xml"),
                ("Accept", LINO_CONTENT_TYPE),
            ],
            Some("<item/>"),
        )
        .await;

    assert_eq!(response.status, 415);
    let problem = response.lino();
    assert_eq!(member(&problem, "status"), &int(415));
    assert!(supported_contains(&problem, LINO_CONTENT_TYPE));
}

#[tokio::test]
async fn test_6_every_method_carries_the_semantics_of_section_4_1() {
    let api = Served::start(build_app()).await;
    let client = &api.client;
    let options = RequestOptions::new();

    let created = client
        .post(
            "/items",
            &object([("name", string("sixth")), ("tag", string("z"))]),
            &options,
        )
        .await
        .unwrap();
    assert_eq!(created.status, 201);
    let body = created.value();
    let identifier = member(&body, "id").clone();
    let location = created.location.clone().expect("a Location header");
    assert_eq!(location, format!("/items/{}", text(&body, "id")));

    let read = client.get(&location, &options).await.unwrap();
    assert_eq!(read.data, created.data);

    let head = client.head(&location, &options).await.unwrap();
    assert_eq!(head.status, 200);
    assert_eq!(head.data, None);
    assert_eq!(head.etag, read.etag);

    let replaced = client
        .put(&location, &object([("name", string("replaced"))]), &options)
        .await
        .unwrap();
    assert_eq!(
        replaced.value(),
        object([("name", string("replaced")), ("id", identifier.clone())])
    );

    let merged = client
        .patch(&location, &object([("tag", string("y"))]), &options)
        .await
        .unwrap();
    assert_eq!(
        merged.value(),
        object([
            ("name", string("replaced")),
            ("id", identifier),
            ("tag", string("y")),
        ])
    );

    let removed = client.delete(&location, &options).await.unwrap();
    assert_eq!(removed.status, 204);
    assert_eq!(removed.data, None);
}

#[tokio::test]
async fn test_7_head_options_and_405_are_automatic_and_carry_allow() {
    let item_methods = "DELETE, GET, HEAD, OPTIONS, PATCH, PUT";
    let api = Served::start(build_app()).await;

    let head = api.raw("HEAD", "/items/1", &[], None).await;
    assert_eq!(head.status, 200);
    assert_eq!(head.text, "");
    assert!(!head.require("etag").is_empty());

    let options = api.raw("OPTIONS", "/items/1", &[], None).await;
    assert_eq!(options.status, 204);
    assert_eq!(options.require("allow"), item_methods);

    let collection_options = api.raw("OPTIONS", "/items", &[], None).await;
    assert_eq!(
        collection_options.require("allow"),
        "GET, HEAD, OPTIONS, POST"
    );

    let body = encode_for(&LinoValue::Object(Vec::new()), LINO_CONTENT_TYPE).unwrap();
    let not_allowed = api
        .raw(
            "POST",
            "/items/1",
            &[("Content-Type", LINO_CONTENT_TYPE)],
            Some(&body),
        )
        .await;
    assert_eq!(not_allowed.status, 405);
    assert_eq!(not_allowed.require("allow"), item_methods);
}

#[tokio::test]
async fn test_8_every_error_path_answers_with_problem_details_in_lino() {
    let api = Served::start(build_app()).await;

    let response = api
        .raw("GET", "/items/404", &[("Accept", LINO_CONTENT_TYPE)], None)
        .await;
    assert_eq!(response.status, 404);
    assert_eq!(response.content_type(), "application/problem+lino");

    let problem = response.lino();
    assert_eq!(
        text(&problem, "type"),
        "https://link-foundation.github.io/lino-rest-api/errors/not-found"
    );
    assert_eq!(text(&problem, "title"), "Not Found");
    assert_eq!(member(&problem, "status"), &int(404));
    assert_eq!(text(&problem, "instance"), "/items/404");
    assert!(!text(&problem, "detail").is_empty());

    let unknown = api.raw("GET", "/nothing/here", &[], None).await;
    assert_eq!(unknown.status, 404);
    assert_eq!(unknown.content_type(), "application/problem+lino");
}

#[tokio::test]
async fn test_9_collections_paginate_filter_sort_and_project() {
    let api = Served::start(build_app()).await;
    let client = &api.client;

    let page = client
        .get(
            "/items",
            &RequestOptions::new()
                .with_query("limit", &int(2))
                .with_query("offset", &int(1)),
        )
        .await
        .unwrap();
    let envelope = page.value();
    assert_eq!(items(&envelope).len(), 2);
    assert_eq!(
        member(&envelope, "page"),
        &object([
            ("limit", int(2)),
            ("offset", int(1)),
            ("total", int(3)),
            ("count", int(2)),
        ])
    );
    let links = page.headers.get("link").expect("a Link header");
    assert!(links.contains(r#"rel="first""#));
    assert!(links.contains(r#"rel="prev""#));
    assert!(links.contains(r#"rel="last""#));

    let filtered = client
        .list("/items", &RequestOptions::new().with_query_text("tag", "a"))
        .await
        .unwrap();
    assert_eq!(at(&filtered, &["page", "total"]), &int(2));
    assert!(items(&filtered).iter().all(|item| text(item, "tag") == "a"));

    let sorted = client
        .list(
            "/items",
            &RequestOptions::new().with_query_text("sort", "-rank"),
        )
        .await
        .unwrap();
    let ranks: Vec<LinoValue> = items(&sorted)
        .iter()
        .map(|item| member(item, "rank").clone())
        .collect();
    assert_eq!(ranks, vec![int(3), int(2), int(1)]);

    let sparse = client
        .list(
            "/items",
            &RequestOptions::new()
                .with_query_text("fields", "id,name")
                .with_query("limit", &int(1)),
        )
        .await
        .unwrap();
    assert_eq!(
        member(&sparse, "items"),
        &array([object([("id", int(1)), ("name", string("first"))])])
    );
}

#[tokio::test]
async fn test_10_conditional_requests_answer_304_412_and_428() {
    let api = Served::start(build_app()).await;
    let client = &api.client;
    let options = RequestOptions::new();

    let first = client.get("/items/1", &options).await.unwrap();
    let tag = first.etag.clone().expect("an ETag");

    let cached = client
        .get(
            "/items/1",
            &RequestOptions::new().if_none_match(tag.clone()),
        )
        .await
        .unwrap();
    assert_eq!(cached.status, 304);
    assert_eq!(cached.data, None);

    let body = encode_for(&object([("tag", string("c"))]), LINO_CONTENT_TYPE).unwrap();
    let stale = api
        .raw(
            "PATCH",
            "/items/1",
            &[
                ("Content-Type", LINO_CONTENT_TYPE),
                ("If-Match", "\"stale\""),
            ],
            Some(&body),
        )
        .await;
    assert_eq!(stale.status, 412);

    let fresh = client
        .patch(
            "/items/1",
            &object([("tag", string("c"))]),
            &RequestOptions::new().if_match(tag.clone()),
        )
        .await
        .unwrap();
    assert_eq!(fresh.status, 200);
    assert_eq!(text(&fresh.value(), "tag"), "c");
    assert_ne!(fresh.etag, Some(tag));

    let mut strict = LinoApp::new().with_info(ServiceInfo::new("Strict", "1.0.0"));
    let store = MemoryStore::seeded([object([("name", string("guarded"))])]);
    strict.resource(
        "/guarded",
        Arc::new(store),
        ResourceOptions::new().requiring_precondition(true),
    );
    let strict_api = Served::start(strict).await;
    let missing = strict_api.raw("DELETE", "/guarded/1", &[], None).await;
    assert_eq!(missing.status, 428);
}

#[tokio::test]
async fn test_11_cors_preflight_and_actual_requests_are_answered() {
    let api = Served::start(build_app()).await;
    let wildcard = api
        .raw(
            "GET",
            "/items/1",
            &[("Origin", "https://example.com")],
            None,
        )
        .await;
    assert_eq!(wildcard.require("access-control-allow-origin"), "*");
    assert!(
        wildcard
            .require("access-control-expose-headers")
            .contains("ETag")
    );

    let mut restricted = LinoApp::new()
        .with_info(ServiceInfo::new("Restricted", "1.0.0"))
        .with_cors(CorsPolicy::permissive().with_origins(["https://example.com"]));
    restricted.resource(
        "/items",
        Arc::new(MemoryStore::new()),
        ResourceOptions::new(),
    );
    let api = Served::start(restricted).await;

    let preflight = api
        .raw(
            "OPTIONS",
            "/items",
            &[
                ("Origin", "https://example.com"),
                ("Access-Control-Request-Method", "POST"),
                ("Access-Control-Request-Headers", "Content-Type"),
            ],
            None,
        )
        .await;
    assert_eq!(preflight.status, 204);
    assert_eq!(
        preflight.require("access-control-allow-origin"),
        "https://example.com"
    );
    assert!(
        preflight
            .require("access-control-allow-methods")
            .contains("POST")
    );
    assert!(preflight.vary_fields().contains(&"origin".to_string()));

    let rejected = api
        .raw(
            "GET",
            "/items",
            &[("Origin", "https://elsewhere.example")],
            None,
        )
        .await;
    assert_eq!(rejected.header("access-control-allow-origin"), None);
}

#[tokio::test]
async fn test_12_the_service_description_and_the_openapi_document_are_published() {
    let api = Served::start(build_app()).await;

    let description = api.client.describe().await.unwrap();
    assert_eq!(text(&description, "lino_api"), "1.0");
    assert_eq!(
        at(&description, &["info", "title"]),
        &string("Conformance API")
    );
    assert!(members_of(member(&description, "media_types")).contains(&string(LINO_CONTENT_TYPE)));
    let routes = members_of(member(&description, "routes"));
    let items_route = routes
        .iter()
        .find(|route| text(route, "path") == "/items")
        .expect("the /items route is described");
    assert_eq!(
        member(items_route, "methods"),
        &array([
            string("GET"),
            string("HEAD"),
            string("OPTIONS"),
            string("POST"),
        ])
    );

    let openapi = api.raw("GET", "/.well-known/openapi.json", &[], None).await;
    assert_eq!(openapi.content_type(), JSON_CONTENT_TYPE);
    let document = openapi.json();
    assert_eq!(text(&document, "openapi"), "3.1.0");
    assert_eq!(
        at(&document, &["info", "title"]),
        &string("Conformance API")
    );
    at(&document, &["paths", "/items/{id}", "get"]);
    at(
        &document,
        &[
            "paths",
            "/items",
            "post",
            "requestBody",
            "content",
            LINO_CONTENT_TYPE,
        ],
    );
}

#[tokio::test]
async fn test_13_the_client_library_covers_the_surface_of_section_10() {
    let api = Served::start(build_app()).await;
    let client = &api.client;
    let options = RequestOptions::new();

    let created = client
        .post("/items", &object([("name", string("client"))]), &options)
        .await
        .unwrap();
    assert_eq!(created.status, 201);

    let listed = client
        .list(
            "/items",
            &RequestOptions::new().with_query("limit", &int(10)),
        )
        .await
        .unwrap();
    assert_eq!(at(&listed, &["page", "total"]), &int(4));

    assert_eq!(
        client.options("/items", &options).await.unwrap(),
        vec!["GET", "HEAD", "OPTIONS", "POST"]
    );

    match client.get("/items/999", &options).await {
        Ok(_) => panic!("expected a 404"),
        Err(error) => {
            assert_eq!(error.status(), Some(404));
            let problem = error.problem().expect("problem details").clone();
            assert_eq!(text(&problem, "title"), "Not Found");
            assert_eq!(error.to_string(), text(&problem, "detail"));
            assert!(matches!(error, LinoClientError::Status { .. }));
        }
    }

    assert!(!encode_single_line(&object([("ok", LinoValue::Bool(true))])).is_empty());
}

/// The members of a list value, for the checks above.
fn members_of(value: &LinoValue) -> Vec<LinoValue> {
    lino_rest_api::value::as_array(value)
        .cloned()
        .unwrap_or_default()
}

/// Whether the `supported` member of a problem lists a media type.
fn supported_contains(problem: &LinoValue, media_type: &str) -> bool {
    members_of(member(problem, "supported")).contains(&string(media_type))
}
