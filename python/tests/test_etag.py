"""Tests for entity tags and conditional requests (specification section 7)."""

import re

import pytest

from lino_rest_api.etag import (
    compute_etag,
    etag_matches,
    evaluate_preconditions,
    parse_etag_list,
)
from lino_rest_api.problem import LinoHttpError


def test_an_entity_tag_is_a_quoted_hex_sha_256_of_the_body():
    etag = compute_etag("hello")
    assert re.fullmatch(r'"[0-9a-f]{64}"', etag)
    assert etag == compute_etag("hello")
    assert etag != compute_etag("hellp")


def test_an_entity_tag_list_is_split_on_commas_and_weak_prefixes_dropped():
    # This package only ever emits strong tags, so a weak reference to one of
    # them is treated as a reference to the tag itself.
    assert parse_etag_list('"a", W/"b"') == ['"a"', '"b"']
    assert parse_etag_list(None) == []


def test_a_wildcard_matches_any_entity_tag():
    assert etag_matches("*", '"a"')
    assert etag_matches('"a", "b"', '"b"')
    assert not etag_matches('"a"', '"b"')


def test_if_none_match_on_a_safe_method_yields_304():
    result = evaluate_preconditions({"if-none-match": '"a"'}, "GET", '"a"')
    assert result.not_modified is True


def test_a_stale_if_match_is_a_412():
    with pytest.raises(LinoHttpError) as raised:
        evaluate_preconditions({"if-match": '"old"'}, "PUT", '"new"')
    assert raised.value.status == 412


def test_a_matching_if_match_lets_the_request_through():
    result = evaluate_preconditions({"if-match": '"a"'}, "PUT", '"a"')
    assert result.not_modified is False


def test_a_missing_required_precondition_is_a_428():
    with pytest.raises(LinoHttpError) as raised:
        evaluate_preconditions({}, "DELETE", '"a"', require_precondition=True)
    assert raised.value.status == 428


def test_if_none_match_on_an_unsafe_method_is_a_412():
    with pytest.raises(LinoHttpError) as raised:
        evaluate_preconditions({"if-none-match": "*"}, "PUT", '"a"')
    assert raised.value.status == 412
