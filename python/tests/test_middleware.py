"""Tests for the middleware layer (specification sections 2.1, 5 and 7)."""

import re

from lino_rest_api import (
    DEFAULT_MAX_BODY_BYTES,
    JSON_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    build_problem_response,
    build_response,
    create_lino_app,
    decode,
    decode_request_body,
    encode,
    encode_compact_notation,
    encode_for,
    encode_single_line,
    negotiate_request,
)

from .helpers import serve


def echo_app(**options):
    """
    Build an application that echoes whatever body it receives.

    Args:
        options: Application options

    Returns:
        Application under test
    """
    app = create_lino_app(**options)
    app.get("/value", lambda request: {"a": 1, "b": [2, 3]})
    app.post("/echo", lambda request: {"echoed": request.body})
    return app


def test_the_middleware_entry_points_are_functions():
    assert LINO_CONTENT_TYPE == "text/lino"
    assert callable(negotiate_request)
    assert callable(decode_request_body)
    assert callable(build_response)
    assert callable(build_problem_response)
    assert DEFAULT_MAX_BODY_BYTES == 1024 * 1024


async def test_accept_selects_the_response_representation():
    value = {"a": 1, "b": [2, 3]}
    cases = [
        (LINO_CONTENT_TYPE, encode(value)),
        (LINO_LINE_CONTENT_TYPE, encode_single_line(value)),
        (LINO_COMPACT_CONTENT_TYPE, encode_compact_notation(value)),
        (JSON_CONTENT_TYPE, encode_for(value, JSON_CONTENT_TYPE)),
    ]
    async with serve(echo_app()) as api:
        for accept, expected in cases:
            response = await api.raw("/value", headers={"Accept": accept})
            assert response.headers["content-type"] == f"{accept}; charset=utf-8"
            assert response.text == expected


async def test_an_unacceptable_accept_is_a_406_listing_what_is_supported():
    async with serve(echo_app()) as api:
        response = await api.raw("/value", headers={"Accept": "image/png"})
        assert response.status_code == 406
        assert LINO_CONTENT_TYPE in decode(response.text)["supported"]


async def test_the_supported_representations_can_be_narrowed():
    async with serve(echo_app(supported=[LINO_CONTENT_TYPE])) as api:
        response = await api.raw("/value", headers={"Accept": JSON_CONTENT_TYPE})
        assert response.status_code == 406
        assert decode(response.text)["supported"] == [LINO_CONTENT_TYPE]


async def test_content_type_selects_the_request_codec():
    body = {"name": "a"}
    cases = [
        (LINO_CONTENT_TYPE, encode(body)),
        (LINO_LINE_CONTENT_TYPE, encode_single_line(body)),
        (LINO_COMPACT_CONTENT_TYPE, encode_compact_notation(body)),
        (JSON_CONTENT_TYPE, encode_for(body, JSON_CONTENT_TYPE)),
    ]
    async with serve(echo_app()) as api:
        for content_type, encoded in cases:
            response = await api.raw(
                "/echo",
                "POST",
                headers={"Content-Type": content_type},
                content=encoded,
            )
            assert response.status_code == 200
            assert decode(response.text) == {"echoed": body}


async def test_an_unsupported_content_type_is_a_415():
    async with serve(echo_app()) as api:
        response = await api.raw(
            "/echo",
            "POST",
            headers={"Content-Type": "application/xml"},
            content="<a/>",
        )
        assert response.status_code == 415
        assert decode(response.text)["title"] == "Unsupported Media Type"


async def test_a_malformed_body_is_a_400():
    async with serve(echo_app()) as api:
        response = await api.raw(
            "/echo",
            "POST",
            headers={"Content-Type": JSON_CONTENT_TYPE},
            content="{not json",
        )
        assert response.status_code == 400


async def test_an_oversized_body_is_a_413():
    async with serve(echo_app(max_body_bytes=64)) as api:
        response = await api.raw(
            "/echo",
            "POST",
            headers={"Content-Type": LINO_CONTENT_TYPE},
            content=encode({"padding": "x" * 200}),
        )
        assert response.status_code == 413


async def test_an_empty_body_leaves_the_request_body_unset():
    async with serve(echo_app()) as api:
        response = await api.raw("/echo", "POST")
        assert decode(response.text) == {"echoed": None}


async def test_responses_carry_a_strong_entity_tag():
    async with serve(echo_app()) as api:
        response = await api.raw("/value")
        assert re.fullmatch(r'"[0-9a-f]{64}"', response.headers["etag"])


async def test_the_entity_tag_depends_on_the_representation():
    async with serve(echo_app()) as api:
        lino = await api.raw("/value", headers={"Accept": LINO_CONTENT_TYPE})
        json_response = await api.raw("/value", headers={"Accept": JSON_CONTENT_TYPE})
        assert lino.headers["etag"] != json_response.headers["etag"]


def test_negotiate_request_falls_back_to_links_notation():
    assert negotiate_request({}) == LINO_CONTENT_TYPE
    assert negotiate_request({"accept": "application/json"}) == JSON_CONTENT_TYPE


def test_decode_request_body_reports_the_media_type_it_used():
    value, media_type = decode_request_body(
        encode({"a": 1}).encode("utf-8"), "text/lino; charset=utf-8"
    )
    assert value == {"a": 1}
    assert media_type == LINO_CONTENT_TYPE
    assert decode_request_body(b"", None) == (None, None)


def test_build_response_encodes_and_tags_a_value():
    parts = build_response({"a": 1})
    assert parts.status == 200
    assert parts.headers["Content-Type"] == "text/lino; charset=utf-8"
    assert parts.headers["Vary"] == "Accept"
    assert re.fullmatch(r'"[0-9a-f]{64}"', parts.headers["ETag"])
    assert decode(parts.body) == {"a": 1}


def test_build_response_sends_a_raw_body_verbatim():
    parts = build_response("(a 1)", raw=True, etag=False)
    assert parts.body == "(a 1)"


def test_build_problem_response_renders_problem_details():
    parts = build_problem_response(ValueError("nope"), instance="/here")
    assert parts.status == 500
    assert parts.headers["Content-Type"] == "application/problem+lino; charset=utf-8"
    assert decode(parts.body)["instance"] == "/here"
