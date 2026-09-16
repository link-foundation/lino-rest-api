//! Content negotiation, ported from `python/tests/test_media_type.py`
//! (specification section 2.1).

use lino_rest_api::media_type::{
    JSON_CONTENT_TYPE, JSON_PROBLEM_CONTENT_TYPE, LINO_COMPACT_CONTENT_TYPE, LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE, LINO_PROBLEM_CONTENT_TYPE, SUPPORTED_MEDIA_TYPES,
    is_decodable_media_type, negotiate_media_type, normalize_media_type, parse_accept,
    parse_content_type, problem_media_type, supported_media_types, with_charset,
};

/// Negotiate against everything this package can produce.
fn negotiate(accept: Option<&str>) -> Option<String> {
    negotiate_media_type(accept, &supported_media_types())
}

#[test]
fn lino_is_the_default_representation() {
    assert_eq!(SUPPORTED_MEDIA_TYPES[0], LINO_CONTENT_TYPE);
    assert_eq!(negotiate(None).as_deref(), Some(LINO_CONTENT_TYPE));
    assert_eq!(negotiate(Some("")).as_deref(), Some(LINO_CONTENT_TYPE));
    assert_eq!(negotiate(Some("*/*")).as_deref(), Some(LINO_CONTENT_TYPE));
}

#[test]
fn parse_content_type_drops_parameters_and_lower_cases() {
    assert_eq!(
        parse_content_type(Some("Text/LINO; charset=utf-8")),
        LINO_CONTENT_TYPE
    );
    assert_eq!(parse_content_type(None), "");
}

#[test]
fn parse_accept_orders_ranges_by_quality_then_specificity() {
    let ranges = parse_accept(Some("text/*;q=0.5, application/json, text/lino;q=0.8"));
    let types: Vec<&str> = ranges
        .iter()
        .map(|range| range.media_type.as_str())
        .collect();
    assert_eq!(types, vec!["application/json", "text/lino", "text/*"]);
}

#[test]
fn negotiation_honours_quality_values() {
    assert_eq!(
        negotiate(Some("application/json, text/lino;q=0.9")).as_deref(),
        Some(JSON_CONTENT_TYPE)
    );
    assert_eq!(
        negotiate(Some("application/json;q=0.2, text/lino;q=0.9")).as_deref(),
        Some(LINO_CONTENT_TYPE)
    );
}

#[test]
fn a_subtype_wildcard_selects_the_first_supported_match() {
    assert_eq!(
        negotiate(Some("text/*")).as_deref(),
        Some(LINO_CONTENT_TYPE)
    );
    assert_eq!(
        negotiate(Some("application/*")).as_deref(),
        Some(JSON_CONTENT_TYPE)
    );
}

#[test]
fn quality_zero_excludes_a_representation() {
    assert_eq!(
        negotiate(Some("text/lino;q=0, application/json")).as_deref(),
        Some(JSON_CONTENT_TYPE)
    );
}

#[test]
fn negotiation_fails_when_nothing_is_acceptable() {
    assert_eq!(negotiate(Some("image/png")), None);
}

#[test]
fn every_representation_of_the_specification_is_negotiable() {
    for media_type in [
        LINO_CONTENT_TYPE,
        LINO_LINE_CONTENT_TYPE,
        LINO_COMPACT_CONTENT_TYPE,
        JSON_CONTENT_TYPE,
    ] {
        assert_eq!(negotiate(Some(media_type)).as_deref(), Some(media_type));
        assert!(is_decodable_media_type(media_type));
    }
}

#[test]
fn problem_media_types_normalise_to_their_representation() {
    assert_eq!(
        normalize_media_type(LINO_PROBLEM_CONTENT_TYPE),
        LINO_CONTENT_TYPE
    );
    assert_eq!(
        normalize_media_type(JSON_PROBLEM_CONTENT_TYPE),
        JSON_CONTENT_TYPE
    );
    assert_eq!(
        problem_media_type(LINO_CONTENT_TYPE),
        LINO_PROBLEM_CONTENT_TYPE
    );
    assert_eq!(
        problem_media_type(JSON_CONTENT_TYPE),
        JSON_PROBLEM_CONTENT_TYPE
    );
    assert_eq!(problem_media_type("text/lino-line"), "text/lino-line");
}

#[test]
fn with_charset_appends_utf_8() {
    assert_eq!(with_charset(LINO_CONTENT_TYPE), "text/lino; charset=utf-8");
}

#[test]
fn an_unknown_media_type_is_not_decodable() {
    assert!(!is_decodable_media_type("application/xml"));
}
