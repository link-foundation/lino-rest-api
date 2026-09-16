"""Tests for the application over ASGI."""

import pytest

from lino_rest_api import (
    LINO_CONTENT_TYPE,
    LinoApp,
    LinoHttpError,
    create_lino_app,
    created,
    decode,
    encode,
    no_content,
    raw_response,
    status,
)

from .helpers import content_type, serve


def build_app() -> LinoApp:
    """
    Build an application exercising the whole surface.

    Returns:
        Application under test
    """
    app = create_lino_app(title="Test API", version="2.0.0")
    app.get("/health", lambda request: {"status": "ok"}, {"summary": "Health check"})
    app.post("/echo", lambda request: created({"echoed": request.body}, "/echo/1"))
    app.put("/replace", lambda request: {"replaced": request.body})
    app.patch("/merge", lambda request: status(202, {"queued": request.body}))
    app.delete("/gone", lambda request: no_content())
    app.get("/boom", _boom)
    app.get("/crash", _crash)
    app.get("/raw", lambda request: raw_response(encode({"raw": True}), LINO_CONTENT_TYPE))
    return app


def _boom(request):
    """Raise a problem-shaped error."""
    raise LinoHttpError(409, "Already exists")


def _crash(request):
    """Raise an error that is not problem-shaped."""
    raise RuntimeError("unexpected")


def test_create_lino_app_returns_a_lino_app():
    app = create_lino_app()
    assert isinstance(app, LinoApp)
    for method in ("get", "post", "put", "patch", "delete", "route", "resource"):
        assert callable(getattr(app, method))
    assert callable(app)


def test_route_registration_is_chainable_and_rejects_unknown_methods():
    app = create_lino_app()
    assert app.get("/a", lambda request: {}) is app
    with pytest.raises(TypeError):
        app.route("TRACE", "/a", lambda request: {})


async def test_a_handler_return_value_is_encoded_as_links_notation():
    async with serve(build_app()) as api:
        response = await api.raw("/health")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/lino; charset=utf-8"
        assert response.headers["vary"] == "Accept"
        assert decode(response.text) == {"status": "ok"}


async def test_a_request_body_is_decoded_from_links_notation():
    async with serve(build_app()) as api:
        response = await api.raw(
            "/echo",
            "POST",
            headers={"Content-Type": LINO_CONTENT_TYPE},
            content=encode({"name": "Alice"}),
        )
        assert response.status_code == 201
        assert response.headers["location"] == "/echo/1"
        assert decode(response.text) == {"echoed": {"name": "Alice"}}


async def test_explicit_results_carry_their_status_code():
    async with serve(build_app()) as api:
        accepted = await api.raw(
            "/merge",
            "PATCH",
            headers={"Content-Type": LINO_CONTENT_TYPE},
            content=encode({"a": 1}),
        )
        assert accepted.status_code == 202

        deleted = await api.raw("/gone", "DELETE")
        assert deleted.status_code == 204
        assert deleted.text == ""


async def test_a_handler_may_encode_the_response_itself():
    async with serve(build_app()) as api:
        response = await api.raw("/raw")
        assert decode(response.text) == {"raw": True}


async def test_an_async_handler_is_awaited():
    app = create_lino_app()

    async def handler(request):
        return {"async": True}

    app.get("/async", handler)
    async with serve(app) as api:
        assert decode((await api.raw("/async")).text) == {"async": True}


async def test_a_handler_returning_nothing_answers_204():
    app = create_lino_app()
    app.get("/nothing", lambda request: None)
    async with serve(app) as api:
        response = await api.raw("/nothing")
        assert response.status_code == 204
        assert response.text == ""


async def test_a_raised_lino_http_error_becomes_problem_details():
    async with serve(build_app()) as api:
        response = await api.raw("/boom")
        assert response.status_code == 409
        assert (
            response.headers["content-type"]
            == "application/problem+lino; charset=utf-8"
        )
        problem = decode(response.text)
        assert problem["status"] == 409
        assert problem["title"] == "Conflict"
        assert problem["instance"] == "/boom"


async def test_an_unexpected_error_becomes_a_500_without_leaking_the_traceback():
    async with serve(build_app()) as api:
        response = await api.raw("/crash")
        assert response.status_code == 500
        problem = decode(response.text)
        assert problem["status"] == 500
        assert "traceback" not in problem


async def test_expose_traceback_attaches_the_traceback_to_5xx_problems():
    app = create_lino_app(expose_traceback=True)
    app.get("/crash", _crash)
    async with serve(app) as api:
        problem = decode((await api.raw("/crash")).text)
        assert "RuntimeError: unexpected" in problem["traceback"]


async def test_the_service_description_reflects_the_registered_routes():
    async with serve(build_app()) as api:
        description = decode((await api.raw("/.well-known/lino-api")).text)
        assert description["info"]["title"] == "Test API"
        assert description["info"]["version"] == "2.0.0"
        health = next(
            route for route in description["routes"] if route["path"] == "/health"
        )
        assert health["summary"] == "Health check"
        assert health["methods"] == ["GET", "HEAD", "OPTIONS"]


async def test_the_openapi_document_is_served_as_json():
    async with serve(build_app()) as api:
        response = await api.raw("/.well-known/openapi.json")
        assert response.headers["content-type"] == "application/json; charset=utf-8"
        document = response.json()
        assert document["openapi"] == "3.1.0"
        assert document["paths"]["/health"]["get"]


async def test_the_description_can_be_turned_off():
    app = create_lino_app(describe=False)
    app.get("/health", lambda request: {"status": "ok"})
    async with serve(app) as api:
        assert (await api.raw("/.well-known/lino-api")).status_code == 404


async def test_an_unknown_path_is_a_problem_shaped_404():
    async with serve(build_app()) as api:
        response = await api.raw("/nothing/here")
        assert response.status_code == 404
        assert content_type(response) == "application/problem+lino"


async def test_the_application_answers_the_asgi_lifespan_protocol():
    app = build_app()
    received = []

    async def receive():
        return (
            {"type": "lifespan.startup"}
            if not received
            else {"type": "lifespan.shutdown"}
        )

    async def send(message):
        received.append(message["type"])

    await app({"type": "lifespan"}, receive, send)
    assert received == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


async def test_an_unsupported_scope_type_is_refused():
    app = build_app()
    with pytest.raises(NotImplementedError):
        await app({"type": "websocket"}, None, None)
