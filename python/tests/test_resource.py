"""Tests for CRUD resources (specification sections 6 and 7)."""

from typing import Any

import httpx

from lino_rest_api import LINO_CONTENT_TYPE, LinoApp, MemoryStore, create_lino_app, decode, encode

from .helpers import Served, serve


def items_app(**options: Any) -> LinoApp:
    """
    Build an application exposing a seeded ``/items`` resource.

    Args:
        options: Resource options

    Returns:
        Application under test
    """
    app = create_lino_app(title="Items API", version="1.0.0")
    store = MemoryStore(
        [
            {"name": "charlie", "done": False},
            {"name": "alice", "done": True},
            {"name": "bob", "done": False},
        ]
    )
    app.resource("/items", store, name="item", **options)
    return app


async def send(
    api: Served,
    path: str,
    method: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """
    Send a Links Notation request body.

    Args:
        api: Served application
        path: Target path
        method: HTTP method
        body: Value to encode, or None for no body
        headers: Extra headers

    Returns:
        Raw response
    """
    return await api.raw(
        path,
        method,
        headers={"Content-Type": LINO_CONTENT_TYPE, **(headers or {})},
        content=None if body is None else encode(body),
    )


async def test_a_collection_is_served_in_the_envelope_of_the_specification():
    async with serve(items_app()) as api:
        envelope = decode((await api.raw("/items")).text)
        assert len(envelope["items"]) == 3
        assert envelope["page"] == {"limit": 20, "offset": 0, "total": 3, "count": 3}


async def test_a_collection_can_be_filtered_sorted_paginated_and_projected():
    async with serve(items_app()) as api:
        response = await api.raw("/items?done=false&sort=-name&limit=1&fields=name")
        envelope = decode(response.text)
        assert envelope["items"] == [{"name": "charlie"}]
        assert envelope["page"]["total"] == 2
        assert 'rel="next"' in response.headers["link"]


async def test_creating_an_item_answers_201_with_a_location():
    async with serve(items_app()) as api:
        response = await send(api, "/items", "POST", {"name": "dave"})
        assert response.status_code == 201
        assert response.headers["location"] == "/items/4"
        assert decode(response.text)["id"] == 4


async def test_creating_an_item_without_a_body_is_a_400():
    async with serve(items_app()) as api:
        assert (await send(api, "/items", "POST")).status_code == 400


async def test_reading_a_missing_item_is_a_404():
    async with serve(items_app()) as api:
        response = await api.raw("/items/99")
        assert response.status_code == 404
        assert decode(response.text)["title"] == "Not Found"


async def test_a_conditional_read_answers_304():
    async with serve(items_app()) as api:
        first = await api.raw("/items/1")
        second = await api.raw(
            "/items/1", headers={"If-None-Match": first.headers["etag"]}
        )
        assert second.status_code == 304
        assert second.text == ""


async def test_replacing_an_item_requires_a_matching_if_match():
    async with serve(items_app()) as api:
        etag = (await api.raw("/items/1")).headers["etag"]

        stale = await send(
            api, "/items/1", "PUT", {"name": "x"}, {"If-Match": '"stale"'}
        )
        assert stale.status_code == 412

        fresh = await send(api, "/items/1", "PUT", {"name": "x"}, {"If-Match": etag})
        assert fresh.status_code == 200
        assert decode(fresh.text) == {"name": "x", "id": 1}


async def test_a_merge_keeps_the_untouched_members():
    async with serve(items_app()) as api:
        response = await send(api, "/items/1", "PATCH", {"done": True})
        assert decode(response.text) == {"name": "charlie", "done": True, "id": 1}


async def test_deleting_an_item_answers_204_and_then_404():
    async with serve(items_app()) as api:
        assert (await api.raw("/items/1", "DELETE")).status_code == 204
        assert (await api.raw("/items/1")).status_code == 404
        assert (await api.raw("/items/1", "DELETE")).status_code == 404


async def test_require_precondition_demands_if_match_on_unsafe_methods():
    async with serve(items_app(require_precondition=True)) as api:
        response = await send(api, "/items/1", "PATCH", {"done": True})
        assert response.status_code == 428
        assert decode(response.text)["title"] == "Precondition Required"


async def test_upsert_lets_put_create_a_missing_item():
    async with serve(items_app(upsert=True)) as api:
        response = await send(api, "/items/42", "PUT", {"name": "new"})
        assert response.status_code == 201
        assert response.headers["location"] == "/items/42"


async def test_a_subset_of_the_operations_can_be_exposed():
    async with serve(items_app(operations=["list", "get"])) as api:
        options = await api.raw("/items", "OPTIONS")
        assert options.headers["allow"] == "GET, HEAD, OPTIONS"
        assert (await send(api, "/items", "POST", {"name": "x"})).status_code == 405


async def test_the_resource_name_appears_in_problem_details():
    async with serve(items_app()) as api:
        problem = decode((await api.raw("/items/99")).text)
        assert problem["detail"] == "item 99 does not exist"
