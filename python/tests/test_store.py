"""Tests for the in-memory store."""

from lino_rest_api.query import parse_collection_query
from lino_rest_api.store import MemoryStore


def test_seeded_items_receive_sequential_identifiers():
    store = MemoryStore([{"name": "a"}, {"name": "b"}])
    assert store.get(1) == {"name": "a", "id": 1}
    assert store.get(2) == {"name": "b", "id": 2}


def test_an_identifier_from_a_path_is_normalised():
    store = MemoryStore([{"name": "a"}])
    assert store.get("1") == {"name": "a", "id": 1}
    assert store.normalize_id("abc") == "abc"


def test_a_provided_identifier_is_honoured_and_moves_the_counter():
    store = MemoryStore()
    store.create({"id": 10, "name": "ten"})
    assert store.create({"name": "next"})["id"] == 11


def test_update_replaces_and_patch_merges():
    store = MemoryStore([{"name": "a", "done": False}])
    assert store.update(1, {"name": "b"}) == {"name": "b", "id": 1}
    assert store.patch(1, {"done": True}) == {"name": "b", "done": True, "id": 1}
    assert store.update(99, {}) is None
    assert store.patch(99, {}) is None


def test_remove_reports_whether_anything_was_deleted():
    store = MemoryStore([{"name": "a"}])
    assert store.remove(1) is True
    assert store.remove(1) is False


def test_list_applies_a_collection_query():
    store = MemoryStore([{"name": "a", "done": True}, {"name": "b", "done": False}])
    envelope = store.list(parse_collection_query({"done": "true"}))
    assert envelope["page"]["total"] == 1
    assert envelope["items"][0]["name"] == "a"


def test_clear_empties_the_store():
    store = MemoryStore([{"name": "a"}])
    store.clear()
    assert store.items == {}
    assert store.create({"name": "b"})["id"] == 1


def test_a_custom_identifier_field_is_supported():
    store = MemoryStore(id_field="key")
    assert store.create({"name": "a"})["key"] == 1
