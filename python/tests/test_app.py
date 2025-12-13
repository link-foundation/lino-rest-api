"""Tests for LinoAPI."""

import pytest

from lino_rest_api.app import LinoAPI


def test_create_lino_api():
    """Test LinoAPI can be created."""
    api = LinoAPI()
    assert api is not None


def test_lino_api_has_method_decorators():
    """Test LinoAPI has HTTP method decorators."""
    api = LinoAPI()

    assert callable(api.get)
    assert callable(api.post)
    assert callable(api.put)
    assert callable(api.delete)
    assert callable(api.patch)


def test_lino_api_exposes_fastapi_app():
    """Test LinoAPI exposes underlying FastAPI app."""
    api = LinoAPI()
    fastapi_app = api.get_fastapi_app()

    assert fastapi_app is not None
    # FastAPI apps have routes attribute
    assert hasattr(fastapi_app, "routes")


def test_lino_api_custom_title():
    """Test LinoAPI accepts custom title."""
    api = LinoAPI(title="My Custom API")
    fastapi_app = api.get_fastapi_app()

    assert fastapi_app.title == "My Custom API"


def test_lino_api_register_get_endpoint():
    """Test LinoAPI can register GET endpoints."""
    api = LinoAPI()

    @api.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    fastapi_app = api.get_fastapi_app()
    routes = [route.path for route in fastapi_app.routes if hasattr(route, "path")]

    assert "/test" in routes
