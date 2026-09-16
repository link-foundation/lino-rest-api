"""Tests for the client (specification section 10)."""

import httpx
import pytest

from lino_rest_api import (
    DEFAULT_ACCEPT,
    JSON_CONTENT_TYPE,
    AsyncLinoClient,
    LinoApp,
    LinoClient,
    LinoClientError,
    LinoHttpError,
    MemoryStore,
    build_query_string,
    create_async_lino_client,
    create_lino_app,
    create_lino_client,
)

from .helpers import BASE_URL, serve


def build_app() -> LinoApp:
    """
    Build an application the client can talk to.

    Returns:
        Application under test
    """
    app = create_lino_app(title="Items API", version="1.0.0")
    app.resource("/items", MemoryStore([{"name": "first"}]), name="item")
    app.get("/health", lambda request: {"status": "ok"})
    app.get("/empty", lambda request: None)
    app.get("/boom", _boom)
    return app


def _boom(request):
    """Raise a problem-shaped error."""
    raise LinoHttpError(409, "Already exists")


def test_the_client_asks_for_links_notation_first():
    assert DEFAULT_ACCEPT == "text/lino, application/json;q=0.5"
    client = create_lino_client("http://example.com/")
    assert isinstance(client, LinoClient)
    assert client.base_url == "http://example.com"
    client.close()


def test_the_asynchronous_client_shares_the_same_surface():
    client = create_async_lino_client("http://example.com/")
    assert isinstance(client, AsyncLinoClient)
    for method in ("get", "post", "put", "patch", "delete", "head", "options", "list"):
        assert callable(getattr(client, method))


def test_query_strings_expand_list_values():
    assert build_query_string(None) == ""
    assert build_query_string({"a": 1, "b": [2, 3], "c": None}) == "?a=1&b=2&b=3"


async def test_the_client_encodes_requests_and_decodes_responses():
    async with serve(build_app()) as api:
        health = await api.client.get("/health")
        assert health.status == 200
        assert health.data == {"status": "ok"}

        created = await api.client.post("/items", {"name": "second"})
        assert created.status == 201
        assert created.location == "/items/2"
        assert created.data["name"] == "second"


async def test_a_4xx_raises_a_typed_error_carrying_the_problem_details():
    async with serve(build_app()) as api:
        with pytest.raises(LinoClientError) as raised:
            await api.client.get("/boom")
        assert raised.value.status == 409
        assert raised.value.problem["title"] == "Conflict"
        assert str(raised.value) == "Already exists"


async def test_204_is_the_absence_of_a_representation_not_none():
    async with serve(build_app()) as api:
        response = await api.client.get("/empty")
        assert response.status == 204
        assert response.data is None


async def test_the_client_honours_conditional_requests():
    async with serve(build_app()) as api:
        first = await api.client.get("/items/1")
        cached = await api.client.get("/items/1", if_none_match=first.etag)
        assert cached.status == 304
        assert cached.data is None

        updated = await api.client.patch("/items/1", {"done": True}, if_match=first.etag)
        assert updated.data["done"] is True

        with pytest.raises(LinoClientError) as raised:
            await api.client.patch("/items/1", {"done": False}, if_match=first.etag)
        assert raised.value.status == 412


async def test_the_client_can_list_a_collection():
    async with serve(build_app()) as api:
        envelope = await api.client.list("/items", {"limit": 1})
        assert len(envelope["items"]) == 1
        assert envelope["page"]["limit"] == 1


async def test_the_client_reads_the_advertised_methods():
    async with serve(build_app()) as api:
        assert await api.client.options("/health") == ["GET", "HEAD", "OPTIONS"]


async def test_head_yields_headers_without_a_body():
    async with serve(build_app()) as api:
        response = await api.client.head("/health")
        assert response.status == 200
        assert response.data is None
        assert response.etag


async def test_the_client_can_read_the_service_description():
    async with serve(build_app()) as api:
        description = await api.client.describe()
        assert description["info"]["title"] == "Items API"
        assert any(route["path"] == "/items" for route in description["routes"])


async def test_the_request_representation_can_be_switched_to_json():
    async with serve(
        build_app(), accept=JSON_CONTENT_TYPE, content_type=JSON_CONTENT_TYPE
    ) as api:
        created = await api.client.post("/items", {"name": "json"})
        assert created.status == 201
        assert (
            created.response.headers["content-type"] == "application/json; charset=utf-8"
        )


async def test_the_client_deletes_a_resource():
    async with serve(build_app()) as api:
        assert (await api.client.delete("/items/1")).status == 204
        with pytest.raises(LinoClientError) as raised:
            await api.client.get("/items/1")
        assert raised.value.status == 404


async def test_the_asynchronous_client_closes_the_client_it_created():
    app = build_app()
    transport = httpx.ASGITransport(app=app)
    async with AsyncLinoClient(BASE_URL, transport=transport) as client:
        assert (await client.get("/health")).data == {"status": "ok"}



def test_query_strings_spell_booleans_the_way_the_filters_read_them():
    # Python renders ``False`` as "False", which no filter of section 6.1 matches;
    # the wire spelling has to be the "false" the JavaScript client sends.
    assert build_query_string({"done": False, "ok": True}) == "?done=false&ok=true"


async def test_a_boolean_filter_is_sent_in_the_spelling_the_server_parses():
    app = create_lino_app()
    app.resource(
        "/items",
        MemoryStore([{"name": "open", "done": False}, {"name": "shut", "done": True}]),
    )
    async with serve(app) as api:
        envelope = await api.client.list("/items", {"done": False})
        assert [item["name"] for item in envelope["items"]] == ["open"]
