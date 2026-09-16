//! Problem details, ported from `python/tests/test_problem.py`
//! (specification section 5).
//!
//! The Python package also converts an arbitrary raised exception into an error;
//! Rust has no such conversion, because a handler returns a [`LinoHttpError`]
//! rather than raising, so those two tests have no counterpart here.

use lino_objects_codec::LinoValue;
use lino_rest_api::problem::{
    LinoHttpError, PROBLEM_TYPE_BASE, problem_details, problem_slug, reason_phrase,
    validation_error,
};
use lino_rest_api::value::{array, get, int, object, string};

/// The member of a problem, which every test below expects to be there.
fn member<'a>(problem: &'a LinoValue, key: &str) -> &'a LinoValue {
    get(problem, key).unwrap_or_else(|| panic!("problem has no member {key}"))
}

#[test]
fn reason_phrases_follow_rfc_9110() {
    assert_eq!(reason_phrase(404), "Not Found");
    assert_eq!(reason_phrase(428), "Precondition Required");
    assert_eq!(reason_phrase(599), "Server Error");
    assert_eq!(reason_phrase(499), "Request Error");
}

#[test]
fn problem_slugs_are_the_kebab_case_reason_phrase() {
    assert_eq!(problem_slug("Not Found"), "not-found");
    assert_eq!(
        problem_slug("Unsupported Media Type"),
        "unsupported-media-type"
    );
}

#[test]
fn problem_details_carries_type_title_and_status() {
    let problem = problem_details(404, Some("Item 42 does not exist"), Some("/items/42"));
    assert_eq!(
        member(&problem, "type"),
        &string(format!("{PROBLEM_TYPE_BASE}not-found"))
    );
    assert_eq!(member(&problem, "title"), &string("Not Found"));
    assert_eq!(member(&problem, "status"), &int(404));
    assert_eq!(
        member(&problem, "detail"),
        &string("Item 42 does not exist")
    );
    assert_eq!(member(&problem, "instance"), &string("/items/42"));
}

#[test]
fn lino_http_error_renders_itself_as_problem_details() {
    let error =
        LinoHttpError::new(409, Some("Already exists")).with_extension("conflicting_id", int(7));
    let problem = error.to_problem(Some("/items"));
    assert_eq!(member(&problem, "status"), &int(409));
    assert_eq!(member(&problem, "title"), &string("Conflict"));
    assert_eq!(member(&problem, "instance"), &string("/items"));
    assert_eq!(member(&problem, "conflicting_id"), &int(7));
}

#[test]
fn validation_error_lists_field_failures() {
    let error = validation_error(
        vec![("name".to_string(), "is required".to_string())],
        "Request body failed validation",
    );
    let problem = error.to_problem(Some("/items"));
    assert_eq!(member(&problem, "status"), &int(422));
    assert_eq!(
        member(&problem, "type"),
        &string(format!("{PROBLEM_TYPE_BASE}validation-failed"))
    );
    assert_eq!(
        member(&problem, "errors"),
        &array([object([
            ("field", string("name")),
            ("message", string("is required")),
        ])])
    );
}

#[test]
fn the_message_is_the_detail_and_falls_back_to_the_title() {
    assert_eq!(
        LinoHttpError::new(409, Some("Already exists")).message(),
        "Already exists"
    );
    assert_eq!(LinoHttpError::new(409, None).message(), "Conflict");
}

#[test]
fn an_error_displays_itself_as_its_message() {
    let error = LinoHttpError::new(400, Some("bad"));
    assert_eq!(error.to_string(), "bad");
    assert_eq!(LinoHttpError::new(400, None).to_string(), "Bad Request");
}

#[test]
fn a_retitled_error_retitles_its_type_uri() {
    let error = LinoHttpError::new(409, Some("Already exists")).with_title("Duplicate Item");
    assert_eq!(error.title, "Duplicate Item");
    assert_eq!(error.type_uri, format!("{PROBLEM_TYPE_BASE}duplicate-item"));
}

#[test]
fn an_explicit_instance_wins_over_the_request_path() {
    let error = LinoHttpError::new(404, Some("gone")).with_instance("/items/7");
    let problem = error.to_problem(Some("/items"));
    assert_eq!(member(&problem, "instance"), &string("/items/7"));
}

#[test]
fn headers_travel_with_the_error() {
    let error = LinoHttpError::new(405, None).with_header("Allow", "GET, HEAD, OPTIONS");
    assert_eq!(
        error.headers.get("Allow").map(String::as_str),
        Some("GET, HEAD, OPTIONS")
    );
}
