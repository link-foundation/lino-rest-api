"""Tests for collection query parsing (specification section 6)."""

import pytest

from lino_rest_api.problem import LinoHttpError
from lino_rest_api.query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SortKey,
    parse_collection_query,
    parse_fields,
    parse_scalar,
    parse_sort,
)


def test_scalars_in_the_query_string_are_typed():
    assert parse_scalar("42") == 42
    assert parse_scalar("1.5") == 1.5
    assert parse_scalar("true") is True
    assert parse_scalar("false") is False
    assert parse_scalar("null") is None
    assert parse_scalar("text") == "text"
    assert parse_scalar("") == ""


def test_sort_accepts_a_comma_separated_list_with_descending_prefixes():
    assert parse_sort("-created,name") == [
        SortKey("created", True),
        SortKey("name", False),
    ]
    assert parse_sort(None) == []


def test_fields_is_none_when_absent_and_a_list_when_present():
    assert parse_fields(None) is None
    assert parse_fields("id,name") == ["id", "name"]


def test_defaults_apply_when_the_query_is_empty():
    query = parse_collection_query({})
    assert query.limit == DEFAULT_LIMIT
    assert query.offset == 0
    assert query.sort == []
    assert query.fields is None
    assert query.filters == {}


def test_non_reserved_parameters_become_filters():
    query = parse_collection_query(
        {
            "limit": "5",
            "offset": "10",
            "sort": "-name",
            "fields": "id",
            "done": "true",
            "tag": ["a", "b"],
        }
    )
    assert query.limit == 5
    assert query.offset == 10
    assert query.filters == {"done": True, "tag": ["a", "b"]}


def test_limit_is_clamped_to_the_maximum():
    assert parse_collection_query({"limit": str(MAX_LIMIT + 50)}).limit == MAX_LIMIT


def test_a_malformed_limit_is_a_400():
    with pytest.raises(LinoHttpError) as bad_limit:
        parse_collection_query({"limit": "abc"})
    assert bad_limit.value.status == 400

    with pytest.raises(LinoHttpError) as bad_offset:
        parse_collection_query({"offset": "-1"})
    assert bad_offset.value.status == 400


def test_the_page_size_bounds_can_be_overridden():
    query = parse_collection_query({"limit": "500"}, default_limit=5, max_limit=200)
    assert query.limit == 200
    assert parse_collection_query({}, default_limit=5).limit == 5
