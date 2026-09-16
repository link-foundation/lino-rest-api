//! The middleware layer, ported from `python/tests/test_middleware.py`
//! (specification sections 2.1, 5 and 7).

// A handler reports a `LinoHttpError`, which is larger than clippy's threshold
// for an error type; the crate allows it at its root for the same reason.
#![allow(clippy::result_large_err)]

mod common;

use common::InProcess;
use lino_objects_codec::LinoValue;
use lino_rest_api::app::LinoApp;
use lino_rest_api::codec::{
    decode, encode, encode_compact_notation, encode_for, encode_single_line,
};
use lino_rest_api::headers::Headers;
use lino_rest_api::media_type::{
    JSON_CONTENT_TYPE, LINO_COMPACT_CONTENT_TYPE, LINO_CONTENT_TYPE, LINO_LINE_CONTENT_TYPE,
};
use lino_rest_api::middleware::{
    DEFAULT_MAX_BODY_BYTES, EtagPolicy, build_problem_response, build_response,
    decode_request_body, negotiate_request,
};
use lino_rest_api::problem::LinoHttpError;
use lino_rest_api::response::Body;
use lino_rest_api::value::{array, get, int, object, string};

/// The value the `/value` route answers with.
fn value() -> LinoValue {
    object([("a", int(1)), ("b", array([int(2), int(3)]))])
}

/// An application that echoes whatever body it receives.
fn echo_app() -> LinoApp {
    let mut app = LinoApp::new();
    app.get_fn("/value", "A value", |_request| Ok(value()));
    app.post_fn("/echo", "Echo the body", |request| {
        Ok(object([(
            "echoed",
            request.body.clone().unwrap_or(LinoValue::Null),
        )]))
    });
    app
}

/// Whether a header value is a strong entity tag: a quoted SHA-256 in hex.
fn is_strong_etag(tag: &str) -> bool {
    let Some(digest) = tag.strip_prefix('"').and_then(|tag| tag.strip_suffix('"')) else {
        return false;
    };
    digest.len() == 64
        && digest
            .chars()
            .all(|character| character.is_ascii_digit() || ('a'..='f').contains(&character))
}

#[test]
fn the_middleware_entry_points_are_plain_functions() {
    assert_eq!(LINO_CONTENT_TYPE, "text/lino");
    assert_eq!(DEFAULT_MAX_BODY_BYTES, 1024 * 1024);
}

#[tokio::test]
async fn accept_selects_the_response_representation() {
    let api = InProcess::new(echo_app());
    let cases = [
        (LINO_CONTENT_TYPE, encode(&value())),
        (LINO_LINE_CONTENT_TYPE, encode_single_line(&value())),
        (LINO_COMPACT_CONTENT_TYPE, encode_compact_notation(&value())),
        (
            JSON_CONTENT_TYPE,
            encode_for(&value(), JSON_CONTENT_TYPE).expect("JSON is supported"),
        ),
    ];
    for (accept, expected) in cases {
        let response = api.raw("GET", "/value", &[("Accept", accept)], None).await;
        assert_eq!(
            response.require("content-type"),
            format!("{accept}; charset=utf-8")
        );
        assert_eq!(response.text, expected);
    }
}

#[tokio::test]
async fn an_unacceptable_accept_is_a_406_listing_what_is_supported() {
    let api = InProcess::new(echo_app());
    let response = api
        .raw("GET", "/value", &[("Accept", "image/png")], None)
        .await;
    assert_eq!(response.status, 406);
    let problem = response.value();
    let supported = get(&problem, "supported").expect("the problem lists what is supported");
    assert_eq!(
        supported,
        &array([
            string(LINO_CONTENT_TYPE),
            string(LINO_LINE_CONTENT_TYPE),
            string(LINO_COMPACT_CONTENT_TYPE),
            string(JSON_CONTENT_TYPE),
        ])
    );
}

#[tokio::test]
async fn the_supported_representations_can_be_narrowed() {
    let api = InProcess::new(echo_app().with_supported([LINO_CONTENT_TYPE.to_string()]));
    let response = api
        .raw("GET", "/value", &[("Accept", JSON_CONTENT_TYPE)], None)
        .await;
    assert_eq!(response.status, 406);
    assert_eq!(
        get(&response.value(), "supported"),
        Some(&array([string(LINO_CONTENT_TYPE)]))
    );
}

#[tokio::test]
async fn content_type_selects_the_request_codec() {
    let api = InProcess::new(echo_app());
    let body = object([("name", string("a"))]);
    let cases = [
        (LINO_CONTENT_TYPE, encode(&body)),
        (LINO_LINE_CONTENT_TYPE, encode_single_line(&body)),
        (LINO_COMPACT_CONTENT_TYPE, encode_compact_notation(&body)),
        (
            JSON_CONTENT_TYPE,
            encode_for(&body, JSON_CONTENT_TYPE).expect("JSON is supported"),
        ),
    ];
    for (content_type, encoded) in cases {
        let response = api
            .raw(
                "POST",
                "/echo",
                &[("Content-Type", content_type)],
                Some(&encoded),
            )
            .await;
        assert_eq!(response.status, 200);
        assert_eq!(response.value(), object([("echoed", body.clone())]));
    }
}

#[tokio::test]
async fn an_unsupported_content_type_is_a_415() {
    let api = InProcess::new(echo_app());
    let response = api
        .raw(
            "POST",
            "/echo",
            &[("Content-Type", "application/xml")],
            Some("<a/>"),
        )
        .await;
    assert_eq!(response.status, 415);
    assert_eq!(
        get(&response.value(), "title"),
        Some(&string("Unsupported Media Type"))
    );
}

#[tokio::test]
async fn a_malformed_body_is_a_400() {
    let api = InProcess::new(echo_app());
    let response = api
        .raw(
            "POST",
            "/echo",
            &[("Content-Type", JSON_CONTENT_TYPE)],
            Some("{not json"),
        )
        .await;
    assert_eq!(response.status, 400);
}

#[tokio::test]
async fn an_oversized_body_is_a_413() {
    let api = InProcess::new(echo_app().with_max_body_bytes(64));
    let padded = object([("padding", string("x".repeat(200)))]);
    let response = api
        .raw(
            "POST",
            "/echo",
            &[("Content-Type", LINO_CONTENT_TYPE)],
            Some(&encode(&padded)),
        )
        .await;
    assert_eq!(response.status, 413);
    assert_eq!(response.header("connection"), Some("close"));
}

#[tokio::test]
async fn an_empty_body_leaves_the_request_body_unset() {
    let api = InProcess::new(echo_app());
    let response = api.raw("POST", "/echo", &[], None).await;
    assert_eq!(response.value(), object([("echoed", LinoValue::Null)]));
}

#[tokio::test]
async fn responses_carry_a_strong_entity_tag() {
    let api = InProcess::new(echo_app());
    let response = api.raw("GET", "/value", &[], None).await;
    assert!(is_strong_etag(response.require("etag")));
}

#[tokio::test]
async fn the_entity_tag_depends_on_the_representation() {
    let api = InProcess::new(echo_app());
    let lino = api
        .raw("GET", "/value", &[("Accept", LINO_CONTENT_TYPE)], None)
        .await;
    let json = api
        .raw("GET", "/value", &[("Accept", JSON_CONTENT_TYPE)], None)
        .await;
    assert_ne!(lino.require("etag"), json.require("etag"));
}

#[test]
fn negotiate_request_falls_back_to_links_notation() {
    assert_eq!(
        negotiate_request(&Headers::new(), None).expect("LINO is acceptable"),
        LINO_CONTENT_TYPE
    );
    let mut headers = Headers::new();
    headers.insert("accept", JSON_CONTENT_TYPE);
    assert_eq!(
        negotiate_request(&headers, None).expect("JSON is acceptable"),
        JSON_CONTENT_TYPE
    );
}

#[test]
fn decode_request_body_reports_the_media_type_it_used() {
    let body = object([("a", int(1))]);
    let decoded = decode_request_body(
        encode(&body).as_bytes(),
        Some("text/lino; charset=utf-8"),
        DEFAULT_MAX_BODY_BYTES,
    )
    .expect("the body decodes");
    assert_eq!(decoded.value, Some(body));
    assert_eq!(decoded.media_type.as_deref(), Some(LINO_CONTENT_TYPE));

    let empty = decode_request_body(b"", None, DEFAULT_MAX_BODY_BYTES).expect("no body decodes");
    assert_eq!(empty.value, None);
    assert_eq!(empty.media_type, None);
}

#[test]
fn build_response_encodes_and_tags_a_value() {
    let parts = build_response(
        &Body::Value(object([("a", int(1))])),
        200,
        LINO_CONTENT_TYPE,
        &Headers::new(),
        &Headers::new(),
        "GET",
        EtagPolicy::default(),
    )
    .expect("the value encodes");
    assert_eq!(parts.status, 200);
    assert_eq!(
        parts.headers.get("Content-Type"),
        Some("text/lino; charset=utf-8")
    );
    assert_eq!(parts.headers.get("Vary"), Some("Accept"));
    assert!(is_strong_etag(
        parts.headers.get("ETag").expect("the response is tagged")
    ));
    assert_eq!(
        decode(&parts.body).expect("the body decodes"),
        object([("a", int(1))])
    );
}

#[test]
fn build_response_sends_a_raw_body_verbatim() {
    let parts = build_response(
        &Body::Raw("(a 1)".to_string()),
        200,
        LINO_CONTENT_TYPE,
        &Headers::new(),
        &Headers::new(),
        "GET",
        EtagPolicy {
            etag: false,
            ..EtagPolicy::default()
        },
    )
    .expect("a raw body is sent as it is");
    assert_eq!(parts.body, "(a 1)");
    assert_eq!(parts.headers.get("ETag"), None);
}

#[test]
fn an_empty_body_becomes_a_204() {
    let parts = build_response(
        &Body::Empty,
        200,
        LINO_CONTENT_TYPE,
        &Headers::new(),
        &Headers::new(),
        "DELETE",
        EtagPolicy::default(),
    )
    .expect("an empty body needs no encoding");
    assert_eq!(parts.status, 204);
    assert_eq!(parts.body, "");
}

#[test]
fn build_problem_response_renders_problem_details() {
    let parts = build_problem_response(
        &LinoHttpError::new(500, Some("nope")),
        LINO_CONTENT_TYPE,
        Some("/here"),
    );
    assert_eq!(parts.status, 500);
    assert_eq!(
        parts.headers.get("Content-Type"),
        Some("application/problem+lino; charset=utf-8")
    );
    assert_eq!(
        get(
            &decode(&parts.body).expect("the problem decodes"),
            "instance"
        ),
        Some(&string("/here"))
    );
}
