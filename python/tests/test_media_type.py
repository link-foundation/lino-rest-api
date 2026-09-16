"""Tests for content negotiation (specification section 2.1)."""

from lino_rest_api.media_type import (
    JSON_CONTENT_TYPE,
    JSON_PROBLEM_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_PROBLEM_CONTENT_TYPE,
    SUPPORTED_MEDIA_TYPES,
    is_decodable_media_type,
    negotiate_media_type,
    normalize_media_type,
    parse_accept,
    parse_content_type,
    problem_media_type,
    with_charset,
)


def test_lino_is_the_default_representation():
    assert SUPPORTED_MEDIA_TYPES[0] == LINO_CONTENT_TYPE
    assert negotiate_media_type(None) == LINO_CONTENT_TYPE
    assert negotiate_media_type("") == LINO_CONTENT_TYPE
    assert negotiate_media_type("*/*") == LINO_CONTENT_TYPE


def test_parse_content_type_drops_parameters_and_lower_cases():
    assert parse_content_type("Text/LINO; charset=utf-8") == LINO_CONTENT_TYPE
    assert parse_content_type(None) == ""


def test_parse_accept_orders_ranges_by_quality_then_specificity():
    ranges = parse_accept("text/*;q=0.5, application/json, text/lino;q=0.8")
    assert [entry.type for entry in ranges] == [
        "application/json",
        "text/lino",
        "text/*",
    ]


def test_negotiation_honours_quality_values():
    assert (
        negotiate_media_type("application/json, text/lino;q=0.9") == JSON_CONTENT_TYPE
    )
    assert (
        negotiate_media_type("application/json;q=0.2, text/lino;q=0.9")
        == LINO_CONTENT_TYPE
    )


def test_a_subtype_wildcard_selects_the_first_supported_match():
    assert negotiate_media_type("text/*") == LINO_CONTENT_TYPE
    assert negotiate_media_type("application/*") == JSON_CONTENT_TYPE


def test_quality_zero_excludes_a_representation():
    assert negotiate_media_type("text/lino;q=0, application/json") == JSON_CONTENT_TYPE


def test_negotiation_fails_when_nothing_is_acceptable():
    assert negotiate_media_type("image/png") is None


def test_every_representation_of_the_specification_is_negotiable():
    for media_type in (
        LINO_CONTENT_TYPE,
        LINO_LINE_CONTENT_TYPE,
        LINO_COMPACT_CONTENT_TYPE,
        JSON_CONTENT_TYPE,
    ):
        assert negotiate_media_type(media_type) == media_type
        assert is_decodable_media_type(media_type)


def test_problem_media_types_normalise_to_their_representation():
    assert normalize_media_type(LINO_PROBLEM_CONTENT_TYPE) == LINO_CONTENT_TYPE
    assert normalize_media_type(JSON_PROBLEM_CONTENT_TYPE) == JSON_CONTENT_TYPE
    assert problem_media_type(LINO_CONTENT_TYPE) == LINO_PROBLEM_CONTENT_TYPE
    assert problem_media_type(JSON_CONTENT_TYPE) == JSON_PROBLEM_CONTENT_TYPE
    assert problem_media_type("text/lino-line") == "text/lino-line"


def test_with_charset_appends_utf_8():
    assert with_charset(LINO_CONTENT_TYPE) == "text/lino; charset=utf-8"


def test_an_unknown_media_type_is_not_decodable():
    assert not is_decodable_media_type("application/xml")
