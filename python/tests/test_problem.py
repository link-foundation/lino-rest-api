"""Tests for problem details (specification section 5)."""

from lino_rest_api.problem import (
    PROBLEM_TYPE_BASE,
    LinoHttpError,
    problem_details,
    problem_slug,
    reason_phrase,
    to_http_error,
    validation_error,
)


def test_reason_phrases_follow_rfc_9110():
    assert reason_phrase(404) == "Not Found"
    assert reason_phrase(428) == "Precondition Required"
    assert reason_phrase(599) == "Server Error"
    assert reason_phrase(499) == "Request Error"


def test_problem_slugs_are_the_kebab_case_reason_phrase():
    assert problem_slug("Not Found") == "not-found"
    assert problem_slug("Unsupported Media Type") == "unsupported-media-type"


def test_problem_details_carries_type_title_and_status():
    problem = problem_details(404, "Item 42 does not exist", instance="/items/42")
    assert problem["type"] == f"{PROBLEM_TYPE_BASE}not-found"
    assert problem["title"] == "Not Found"
    assert problem["status"] == 404
    assert problem["detail"] == "Item 42 does not exist"
    assert problem["instance"] == "/items/42"


def test_lino_http_error_renders_itself_as_problem_details():
    error = LinoHttpError(409, "Already exists", extensions={"conflicting_id": 7})
    problem = error.to_problem("/items")
    assert problem["status"] == 409
    assert problem["title"] == "Conflict"
    assert problem["instance"] == "/items"
    assert problem["conflicting_id"] == 7


def test_validation_error_lists_field_failures():
    error = validation_error([{"field": "name", "message": "is required"}])
    problem = error.to_problem("/items")
    assert problem["status"] == 422
    assert problem["type"] == f"{PROBLEM_TYPE_BASE}validation-failed"
    assert problem["errors"] == [{"field": "name", "message": "is required"}]


def test_an_arbitrary_raised_exception_becomes_a_500():
    error = to_http_error(RuntimeError("boom"))
    assert isinstance(error, LinoHttpError)
    assert error.status == 500


def test_a_lino_http_error_passes_through_unchanged():
    original = LinoHttpError(400, "bad")
    assert to_http_error(original) is original


def test_an_error_carrying_a_status_is_honoured():
    class FailureError(Exception):
        status = 403

    error = to_http_error(FailureError("nope"))
    assert error.status == 403
    assert error.detail == "nope"


def test_the_message_is_the_detail_and_falls_back_to_the_title():
    assert LinoHttpError(409, "Already exists").message == "Already exists"
    assert LinoHttpError(409).message == "Conflict"
