"""Tests for collection processing (specification section 6)."""

from lino_rest_api.collection import (
    apply_collection_query,
    collection_envelope,
    matches_filters,
    pagination_link_header,
    project_fields,
    sort_items,
)
from lino_rest_api.query import SortKey, parse_collection_query

ITEMS = [
    {"id": 1, "name": "charlie", "done": False, "score": 3},
    {"id": 2, "name": "alice", "done": True, "score": 1},
    {"id": 3, "name": "bob", "done": False, "score": 2},
]


def test_filters_compare_equal_values():
    assert matches_filters(ITEMS[0], {"done": False})
    assert not matches_filters(ITEMS[0], {"done": True})


def test_a_list_filter_behaves_like_an_any_of_match():
    assert matches_filters(ITEMS[0], {"name": ["alice", "charlie"]})
    assert not matches_filters(ITEMS[0], {"name": ["alice", "bob"]})


def test_sorting_supports_several_keys_and_directions():
    ordered = sort_items(
        ITEMS,
        [SortKey("done", False), SortKey("name", True)],
    )
    assert [item["id"] for item in ordered] == [1, 3, 2]


def test_sparse_fieldsets_keep_only_the_requested_members():
    assert project_fields(ITEMS[0], ["id", "name"]) == {"id": 1, "name": "charlie"}
    assert project_fields(ITEMS[0], None) == ITEMS[0]


def test_the_envelope_reports_the_page_and_the_total():
    envelope = collection_envelope([ITEMS[0]], limit=1, offset=2, total=3)
    assert envelope["page"] == {"limit": 1, "offset": 2, "total": 3, "count": 1}


def test_a_query_filters_sorts_paginates_and_projects():
    envelope = apply_collection_query(
        ITEMS,
        parse_collection_query(
            {"done": "false", "sort": "name", "limit": "1", "fields": "name"}
        ),
    )
    assert envelope["items"] == [{"name": "bob"}]
    assert envelope["page"] == {"limit": 1, "offset": 0, "total": 2, "count": 1}


def test_link_carries_first_prev_next_and_last():
    header = pagination_link_header(
        "/items", {"done": "false"}, limit=10, offset=10, total=35
    )
    assert 'rel="first"' in header
    assert "offset=0" in header
    assert 'rel="prev"' in header
    assert 'rel="next"' in header
    assert "offset=30" in header
    assert "done=false" in header


def test_the_first_page_has_no_prev_link():
    header = pagination_link_header("/items", {}, limit=10, offset=0, total=5)
    assert 'rel="prev"' not in header
    assert 'rel="next"' not in header
