//! Tests for cross-origin requests (specification section 8), ported from
//! `python/tests/test_cors.py`.

use lino_rest_api::cors::{
    CorsPolicy, DEFAULT_ALLOWED_HEADERS, DEFAULT_EXPOSED_HEADERS, cors_headers,
};
use lino_rest_api::headers::Headers;
use lino_rest_api::middleware::append_vary;

#[test]
fn content_type_and_accept_are_allowed_so_browsers_can_negotiate_lino() {
    assert!(DEFAULT_ALLOWED_HEADERS.contains(&"Content-Type"));
    assert!(DEFAULT_ALLOWED_HEADERS.contains(&"Accept"));
    assert!(DEFAULT_ALLOWED_HEADERS.contains(&"If-Match"));
}

#[test]
fn etag_and_link_are_exposed_so_clients_can_follow_the_protocol() {
    assert!(DEFAULT_EXPOSED_HEADERS.contains(&"ETag"));
    assert!(DEFAULT_EXPOSED_HEADERS.contains(&"Link"));
}

#[test]
fn the_default_policy_allows_any_origin() {
    let headers = cors_headers(&CorsPolicy::default(), Some("https://example.com"));
    assert_eq!(headers.get("Access-Control-Allow-Origin"), Some("*"));
    assert!(
        headers
            .get("Access-Control-Allow-Methods")
            .unwrap()
            .contains("PATCH")
    );
}

#[test]
fn an_allow_list_reflects_the_request_origin() {
    let policy = CorsPolicy::permissive().with_origins(["https://example.com"]);
    let allowed = cors_headers(&policy, Some("https://example.com"));
    assert_eq!(
        allowed.get("Access-Control-Allow-Origin"),
        Some("https://example.com")
    );
    assert!(cors_headers(&policy, Some("https://evil.example")).is_empty());
}

#[test]
fn credentialed_requests_echo_the_origin() {
    let policy = CorsPolicy::permissive().with_credentials(true);
    let headers = cors_headers(&policy, Some("https://example.com"));
    assert_eq!(
        headers.get("Access-Control-Allow-Origin"),
        Some("https://example.com")
    );
    assert_eq!(
        headers.get("Access-Control-Allow-Credentials"),
        Some("true")
    );
}

#[test]
fn append_vary_keeps_existing_field_names() {
    let mut headers = Headers::new();
    append_vary(&mut headers, "Accept");
    append_vary(&mut headers, "Origin");
    append_vary(&mut headers, "accept");
    assert_eq!(headers.get("Vary"), Some("Accept, Origin"));
}
