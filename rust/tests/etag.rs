//! Tests for entity tags and conditional requests (specification section 7),
//! ported from `python/tests/test_etag.py`.

use lino_rest_api::etag::{compute_etag, etag_matches, evaluate_preconditions, parse_etag_list};
use lino_rest_api::headers::Headers;

/// The request headers of a conditional request.
fn conditional(pairs: &[(&str, &str)]) -> Headers {
    Headers::from_pairs(pairs.iter().map(|(name, value)| (*name, *value)))
}

#[test]
fn an_entity_tag_is_a_quoted_hex_sha_256_of_the_body() {
    let etag = compute_etag("hello");
    assert_eq!(etag.len(), 66);
    assert!(etag.starts_with('"') && etag.ends_with('"'));
    assert!(
        etag[1..65]
            .chars()
            .all(|character| character.is_ascii_hexdigit() && !character.is_ascii_uppercase())
    );
    assert_eq!(etag, compute_etag("hello"));
    assert_ne!(etag, compute_etag("hellp"));
}

#[test]
fn an_entity_tag_list_is_split_on_commas_and_weak_prefixes_dropped() {
    // This package only ever emits strong tags, so a weak reference to one of
    // them is treated as a reference to the tag itself.
    assert_eq!(
        parse_etag_list(Some("\"a\", W/\"b\"")),
        vec!["\"a\"".to_string(), "\"b\"".to_string()]
    );
    assert!(parse_etag_list(None).is_empty());
}

#[test]
fn a_wildcard_matches_any_entity_tag() {
    assert!(etag_matches(Some("*"), "\"a\""));
    assert!(etag_matches(Some("\"a\", \"b\""), "\"b\""));
    assert!(!etag_matches(Some("\"a\""), "\"b\""));
}

#[test]
fn if_none_match_on_a_safe_method_yields_304() {
    let result = evaluate_preconditions(
        &conditional(&[("if-none-match", "\"a\"")]),
        "GET",
        "\"a\"",
        false,
    )
    .unwrap();
    assert!(result.not_modified);
}

#[test]
fn a_stale_if_match_is_a_412() {
    let error = evaluate_preconditions(
        &conditional(&[("if-match", "\"old\"")]),
        "PUT",
        "\"new\"",
        false,
    )
    .unwrap_err();
    assert_eq!(error.status, 412);
}

#[test]
fn a_matching_if_match_lets_the_request_through() {
    let result = evaluate_preconditions(
        &conditional(&[("if-match", "\"a\"")]),
        "PUT",
        "\"a\"",
        false,
    )
    .unwrap();
    assert!(!result.not_modified);
}

#[test]
fn a_missing_required_precondition_is_a_428() {
    let error = evaluate_preconditions(&Headers::new(), "DELETE", "\"a\"", true).unwrap_err();
    assert_eq!(error.status, 428);
}

#[test]
fn if_none_match_on_an_unsafe_method_is_a_412() {
    let error = evaluate_preconditions(
        &conditional(&[("if-none-match", "*")]),
        "PUT",
        "\"a\"",
        false,
    )
    .unwrap_err();
    assert_eq!(error.status, 412);
}
