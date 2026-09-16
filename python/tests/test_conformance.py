"""
The conformance checklist of the specification (section 11), one test per item.

These tests drive a complete application over HTTP, so they double as the
executable definition of "this implementation conforms".
"""

from lino_rest_api import (
    JSON_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LinoApp,
    LinoClientError,
    MemoryStore,
    create_lino_app,
    decode_from,
    encode_for,
    encode_single_line,
)

from .helpers import content_type, serve, vary_fields

#: The first item of the seeded collection, as stored.
FIRST_ITEM = {"id": 1, "name": "first", "tag": "a", "rank": 2}


def build_app() -> LinoApp:
    """
    Build the application every conformance test runs against.

    Returns:
        An application with a seeded ``/items`` collection
    """
    app = create_lino_app(title="Conformance API", version="1.0.0", cors=True)
    items = MemoryStore()
    items.create({"name": "first", "tag": "a", "rank": 2})
    items.create({"name": "second", "tag": "b", "rank": 1})
    items.create({"name": "third", "tag": "a", "rank": 3})
    app.resource("/items", items, name="item")
    return app


async def test_1_text_lino_is_decoded_on_requests_and_encoded_on_responses():
    async with serve(build_app()) as api:
        response = await api.raw(
            "/items",
            "POST",
            headers={
                "Content-Type": LINO_CONTENT_TYPE,
                "Accept": LINO_CONTENT_TYPE,
            },
            content=encode_for({"name": "fourth", "tag": "c"}, LINO_CONTENT_TYPE),
        )

        assert response.status_code == 201
        assert response.headers["content-type"].startswith(LINO_CONTENT_TYPE)
        created = decode_from(response.text, LINO_CONTENT_TYPE)
        assert created["name"] == "fourth"
        assert created["tag"] == "c"


async def test_2_the_single_line_and_compact_representations_are_negotiable():
    async with serve(build_app()) as api:
        line = await api.raw("/items/1", headers={"Accept": LINO_LINE_CONTENT_TYPE})
        assert content_type(line) == LINO_LINE_CONTENT_TYPE
        assert "\n" not in line.text
        assert decode_from(line.text, LINO_LINE_CONTENT_TYPE) == FIRST_ITEM

        compact = await api.raw(
            "/items/1", headers={"Accept": LINO_COMPACT_CONTENT_TYPE}
        )
        assert content_type(compact) == LINO_COMPACT_CONTENT_TYPE
        assert decode_from(compact.text, LINO_COMPACT_CONTENT_TYPE) == FIRST_ITEM


async def test_3_application_json_remains_available_as_a_fallback():
    async with serve(build_app()) as api:
        response = await api.raw("/items/1", headers={"Accept": JSON_CONTENT_TYPE})
        assert content_type(response) == JSON_CONTENT_TYPE
        assert response.json() == FIRST_ITEM

        sent = await api.raw(
            "/items",
            "POST",
            headers={"Content-Type": JSON_CONTENT_TYPE, "Accept": JSON_CONTENT_TYPE},
            content='{"name":"json"}',
        )
        assert sent.status_code == 201
        assert sent.json()["name"] == "json"


async def test_4_accept_quality_values_select_a_representation_406_and_vary_accept():
    async with serve(build_app()) as api:
        negotiated = await api.raw(
            "/items/1",
            headers={
                "Accept": f"{JSON_CONTENT_TYPE};q=0.4, {LINO_LINE_CONTENT_TYPE};q=0.9"
            },
        )
        assert content_type(negotiated) == LINO_LINE_CONTENT_TYPE
        assert "accept" in vary_fields(negotiated)

        unacceptable = await api.raw("/items/1", headers={"Accept": "image/png"})
        assert unacceptable.status_code == 406
        problem = decode_from(unacceptable.text, LINO_CONTENT_TYPE)
        assert LINO_CONTENT_TYPE in problem["supported"]


async def test_5_an_unsupported_request_media_type_is_a_415():
    async with serve(build_app()) as api:
        response = await api.raw(
            "/items",
            "POST",
            headers={"Content-Type": "application/xml", "Accept": LINO_CONTENT_TYPE},
            content="<item/>",
        )
        assert response.status_code == 415
        problem = decode_from(response.text, LINO_CONTENT_TYPE)
        assert problem["status"] == 415
        assert LINO_CONTENT_TYPE in problem["supported"]


async def test_6_every_method_carries_the_semantics_of_section_4_1():
    async with serve(build_app()) as api:
        client = api.client
        created = await client.post("/items", {"name": "sixth", "tag": "z"})
        assert created.status == 201
        assert created.location == f"/items/{created.data['id']}"

        read = await client.get(created.location)
        assert read.data == created.data

        head = await client.head(created.location)
        assert head.status == 200
        assert head.data is None
        assert head.etag == read.etag

        replaced = await client.put(created.location, {"name": "replaced"})
        assert replaced.data == {"id": created.data["id"], "name": "replaced"}

        merged = await client.patch(created.location, {"tag": "y"})
        assert merged.data == {
            "id": created.data["id"],
            "name": "replaced",
            "tag": "y",
        }

        removed = await client.delete(created.location)
        assert removed.status == 204
        assert removed.data is None


async def test_7_head_options_and_405_are_automatic_and_carry_allow():
    item_methods = "DELETE, GET, HEAD, OPTIONS, PATCH, PUT"
    async with serve(build_app()) as api:
        head = await api.raw("/items/1", "HEAD")
        assert head.status_code == 200
        assert head.text == ""
        assert head.headers["etag"]

        options = await api.raw("/items/1", "OPTIONS")
        assert options.status_code == 204
        assert options.headers["allow"] == item_methods

        collection_options = await api.raw("/items", "OPTIONS")
        assert collection_options.headers["allow"] == "GET, HEAD, OPTIONS, POST"

        not_allowed = await api.raw(
            "/items/1",
            "POST",
            headers={"Content-Type": LINO_CONTENT_TYPE},
            content=encode_for({}, LINO_CONTENT_TYPE),
        )
        assert not_allowed.status_code == 405
        assert not_allowed.headers["allow"] == item_methods


async def test_8_every_error_path_answers_with_problem_details_in_lino():
    async with serve(build_app()) as api:
        response = await api.raw("/items/404", headers={"Accept": LINO_CONTENT_TYPE})
        assert response.status_code == 404
        assert content_type(response) == "application/problem+lino"

        problem = decode_from(response.text, LINO_CONTENT_TYPE)
        assert (
            problem["type"]
            == "https://link-foundation.github.io/lino-rest-api/errors/not-found"
        )
        assert problem["title"] == "Not Found"
        assert problem["status"] == 404
        assert problem["instance"] == "/items/404"
        assert problem["detail"]

        unknown = await api.raw("/nothing/here")
        assert unknown.status_code == 404
        assert content_type(unknown) == "application/problem+lino"


async def test_9_collections_paginate_filter_sort_and_project():
    async with serve(build_app()) as api:
        client = api.client
        page = await client.get("/items", query={"limit": 2, "offset": 1})
        assert len(page.data["items"]) == 2
        assert page.data["page"] == {"limit": 2, "offset": 1, "total": 3, "count": 2}
        links = page.headers["link"]
        assert 'rel="first"' in links
        assert 'rel="prev"' in links
        assert 'rel="last"' in links

        filtered = await client.list("/items", {"tag": "a"})
        assert filtered["page"]["total"] == 2
        assert all(item["tag"] == "a" for item in filtered["items"])

        sorted_items = await client.list("/items", {"sort": "-rank"})
        assert [item["rank"] for item in sorted_items["items"]] == [3, 2, 1]

        sparse = await client.list("/items", {"fields": "id,name", "limit": 1})
        assert sparse["items"] == [{"id": 1, "name": "first"}]


async def test_10_conditional_requests_answer_304_412_and_428():
    async with serve(build_app()) as api:
        client = api.client
        first = await client.get("/items/1")
        assert first.etag

        cached = await client.get("/items/1", if_none_match=first.etag)
        assert cached.status == 304
        assert cached.data is None

        stale = await api.raw(
            "/items/1",
            "PATCH",
            headers={"Content-Type": LINO_CONTENT_TYPE, "If-Match": '"stale"'},
            content=encode_for({"tag": "c"}, LINO_CONTENT_TYPE),
        )
        assert stale.status_code == 412

        fresh = await client.patch("/items/1", {"tag": "c"}, if_match=first.etag)
        assert fresh.status == 200
        assert fresh.data["tag"] == "c"
        assert fresh.etag != first.etag

    strict = create_lino_app(title="Strict", version="1.0.0")
    store = MemoryStore()
    store.create({"name": "guarded"})
    strict.resource("/guarded", store, require_precondition=True)
    async with serve(strict) as strict_api:
        missing = await strict_api.raw("/guarded/1", "DELETE")
        assert missing.status_code == 428


async def test_11_cors_preflight_and_actual_requests_are_answered():
    async with serve(build_app()) as api:
        wildcard = await api.raw("/items/1", headers={"Origin": "https://example.com"})
        assert wildcard.headers["access-control-allow-origin"] == "*"
        assert "ETag" in wildcard.headers["access-control-expose-headers"]

    restricted = create_lino_app(
        title="Restricted",
        version="1.0.0",
        cors={"origin": ["https://example.com"]},
    )
    restricted.resource("/items", MemoryStore())

    async with serve(restricted) as api:
        preflight = await api.raw(
            "/items",
            "OPTIONS",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert preflight.status_code == 204
        assert (
            preflight.headers["access-control-allow-origin"] == "https://example.com"
        )
        assert "POST" in preflight.headers["access-control-allow-methods"]
        assert "origin" in vary_fields(preflight)

        rejected = await api.raw(
            "/items", headers={"Origin": "https://elsewhere.example"}
        )
        assert "access-control-allow-origin" not in rejected.headers


async def test_12_the_service_description_and_the_openapi_document_are_published():
    async with serve(build_app()) as api:
        description = await api.client.describe()
        assert description["lino_api"] == "1.0"
        assert description["info"]["title"] == "Conformance API"
        assert LINO_CONTENT_TYPE in description["media_types"]
        items = next(
            route for route in description["routes"] if route["path"] == "/items"
        )
        assert items["methods"] == ["GET", "HEAD", "OPTIONS", "POST"]

        openapi = await api.raw("/.well-known/openapi.json")
        assert content_type(openapi) == JSON_CONTENT_TYPE
        document = openapi.json()
        assert document["openapi"] == "3.1.0"
        assert document["info"]["title"] == "Conformance API"
        assert document["paths"]["/items/{id}"]["get"]
        assert document["paths"]["/items"]["post"]["requestBody"]["content"][
            LINO_CONTENT_TYPE
        ]


async def test_13_the_client_library_covers_the_surface_of_section_10():
    async with serve(build_app()) as api:
        client = api.client
        created = await client.post("/items", {"name": "client"})
        assert created.status == 201

        listed = await client.list("/items", {"limit": 10})
        assert listed["page"]["total"] == 4

        assert await client.options("/items") == ["GET", "HEAD", "OPTIONS", "POST"]

        try:
            await client.get("/items/999")
            raise AssertionError("expected a 404")
        except LinoClientError as error:
            assert error.status == 404
            assert error.problem["title"] == "Not Found"
            assert str(error) == error.problem["detail"]

        assert isinstance(encode_single_line({"ok": True}), str)
