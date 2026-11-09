//! Binary byte transport and shared fixtures for issue #10.
use links_notation::{LiNo, binary::BinaryLinoCodec};
use lino_rest_api::codec::{BINARY_DECODE_LIMITS, from_json};
use lino_rest_api::etag::compute_etag;
use lino_rest_api::{
    BoundServer, LINO_BINARY_CONTENT_TYPE as BINARY, LINO_CONTENT_TYPE as TEXT, LinoApp,
    LinoClient, RawRequest, RequestOptions, decode_from, encode_for_bytes,
};

fn cases() -> serde_json::Value {
    serde_json::from_str(include_str!("fixtures/binary.json")).unwrap()
}

#[test]
fn portable_values_and_golden_bytes() {
    for case in cases().as_array().unwrap() {
        let value = from_json(&case["value"]);
        let bytes = encode_for_bytes(&value, BINARY).unwrap();
        let hex: String = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
        assert_eq!(hex, case["hex"].as_str().unwrap());
        assert_eq!(decode_from(&bytes, BINARY).unwrap(), value);
    }
}

#[test]
fn rejects_malformed_truncated_trailing_and_depth() {
    let bytes = encode_for_bytes(&from_json(&serde_json::json!({"ok":true})), BINARY).unwrap();
    for packet in [
        vec![255],
        bytes[..bytes.len() - 1].to_vec(),
        [bytes, vec![0]].concat(),
    ] {
        assert!(decode_from(&packet, BINARY).is_err());
    }
    let mut node = LiNo::reference("x".to_string());
    for _ in 0..70 {
        node = LiNo::anonymous(vec![node]);
    }
    let mut codec = BinaryLinoCodec {
        limits: BINARY_DECODE_LIMITS,
        ..Default::default()
    };
    codec.limits.max_depth = 128;
    let deep = codec.encode(&[node]).unwrap();
    assert!(decode_from(&deep, BINARY).is_err());
}

fn app() -> LinoApp {
    let mut app = LinoApp::new()
        .with_supported([TEXT.into(), BINARY.into()])
        .with_max_body_bytes(4096);
    app.post_fn("/echo", "Echo", |request| Ok(request.body.unwrap()));
    app.get_fn("/value", "Value", |_| Ok(from_json(&cases()[13]["value"])));
    app
}

#[tokio::test]
async fn server_negotiates_bytes_errors_head_etags_and_disabled_json() {
    let app = app();
    let get = app
        .respond(RawRequest::new("GET", "/value").with_header("Accept", BINARY))
        .await;
    assert_eq!(get.status, 200);
    assert_eq!(get.headers.get("Content-Type"), Some(BINARY));
    assert_eq!(
        get.headers.get("ETag"),
        Some(compute_etag(get.body_bytes()).as_str())
    );
    assert!(decode_from(get.body_bytes(), BINARY).is_ok());
    let head = app
        .respond(RawRequest::new("HEAD", "/value").with_header("Accept", BINARY))
        .await;
    assert!(head.body_bytes().is_empty());
    assert_eq!(head.headers.get("ETag"), get.headers.get("ETag"));
    let cached = app
        .respond(
            RawRequest::new("GET", "/value")
                .with_header("Accept", BINARY)
                .with_header("If-None-Match", get.headers.get("ETag").unwrap()),
        )
        .await;
    assert_eq!(cached.status, 304);
    for (request, status) in [
        (
            RawRequest::new("POST", "/echo").with_header("Accept", "application/json"),
            406,
        ),
        (
            RawRequest::new("POST", "/echo")
                .with_header("Accept", BINARY)
                .with_body("{}", "application/json"),
            415,
        ),
        (
            RawRequest::new("POST", "/echo")
                .with_header("Accept", BINARY)
                .with_body(vec![255], BINARY),
            400,
        ),
        (
            RawRequest::new("POST", "/echo")
                .with_header("Accept", BINARY)
                .with_body(vec![0; 4097], BINARY),
            413,
        ),
    ] {
        assert_eq!(app.respond(request).await.status, status);
    }
}

#[tokio::test]
async fn reqwest_and_axum_roundtrip_without_json() {
    let server = BoundServer::bind(app(), "127.0.0.1:0").await.unwrap();
    let base = server.base_url();
    let task = tokio::spawn(server.serve());
    let client = LinoClient::new(&base)
        .with_accept(BINARY)
        .with_content_type(BINARY);
    let value = from_json(&cases()[13]["value"]);
    let result = client
        .post("/echo", &value, &RequestOptions::new())
        .await
        .unwrap();
    assert_eq!(result.data, Some(value));
    assert!(!result.bytes.is_empty());
    let error = client
        .get("/missing", &RequestOptions::new())
        .await
        .unwrap_err();
    assert_eq!(error.status(), Some(404));
    assert!(error.problem().is_some());
    let text = LinoClient::new(&base).with_accept(TEXT);
    assert!(
        text.get("/value", &RequestOptions::new())
            .await
            .unwrap()
            .data
            .is_some()
    );
    let oversized = reqwest::Client::new()
        .post(format!("{base}/echo"))
        .header("Accept", BINARY)
        .header("Content-Type", BINARY)
        .body(vec![0; 4097])
        .send()
        .await
        .unwrap();
    assert_eq!(oversized.status(), 413);
    assert_eq!(oversized.headers()["content-type"], BINARY);
    assert!(decode_from(oversized.bytes().await.unwrap(), BINARY).is_ok());
    task.abort();
    assert!(task.await.unwrap_err().is_cancelled());
}

#[test]
fn every_graph_budget_rejects_small_hostile_packet() {
    let attacks: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/binary-limits.json")).unwrap();
    for attack in attacks.as_array().unwrap() {
        let hex = attack["hex"].as_str().unwrap();
        let bytes: Vec<u8> = (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect();
        let error = decode_from(&bytes, BINARY).unwrap_err().to_string();
        assert!(
            [
                "limit",
                "budget",
                "excessive",
                "too many",
                "depth",
                "nesting"
            ]
            .iter()
            .any(|word| error.contains(word)),
            "{}: {error}",
            attack["limit"]
        );
    }
}

#[tokio::test]
async fn binary_resource_etags_support_conditional_writes() {
    use lino_rest_api::{resource::ResourceOptions, store::MemoryStore};
    use std::sync::Arc;
    let mut app = LinoApp::new().with_supported([TEXT.into(), BINARY.into()]);
    app.resource(
        "/items",
        Arc::new(MemoryStore::seeded([from_json(
            &serde_json::json!({"name":"old"}),
        )])),
        ResourceOptions::new(),
    );
    let first = app
        .respond(RawRequest::new("GET", "/items/1").with_header("Accept", BINARY))
        .await;
    assert_eq!(first.status, 200);
    let etag = first.headers.get("ETag").unwrap();
    assert_eq!(etag, compute_etag(first.body_bytes()));
    let replacement =
        encode_for_bytes(&from_json(&serde_json::json!({"name":"new"})), BINARY).unwrap();
    for status in [200, 412] {
        let changed = app
            .respond(
                RawRequest::new("PUT", "/items/1")
                    .with_header("Accept", BINARY)
                    .with_header("If-Match", etag)
                    .with_body(replacement.clone(), BINARY),
            )
            .await;
        assert_eq!(changed.status, status);
        assert!(decode_from(changed.body_bytes(), BINARY).is_ok());
    }
}
