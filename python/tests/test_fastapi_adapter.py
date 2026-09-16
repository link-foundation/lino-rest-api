"""
Tests for the FastAPI adapter kept for backwards compatibility.

These cover the surface earlier releases exposed (``LinoAPI`` and
``LinoResponse``), which is now a thin adapter over the standalone
implementation.
"""

from lino_rest_api.app import LinoAPI
from lino_rest_api.middleware import LINO_CONTENT_TYPE, LinoResponse
from lino_rest_api.vendor import decode, encode


def test_create_lino_api():
    api = LinoAPI()
    assert api is not None


def test_lino_api_has_method_decorators():
    api = LinoAPI()
    assert callable(api.get)
    assert callable(api.post)
    assert callable(api.put)
    assert callable(api.delete)
    assert callable(api.patch)


def test_lino_api_exposes_fastapi_app():
    api = LinoAPI()
    fastapi_app = api.get_fastapi_app()
    assert fastapi_app is not None
    # FastAPI apps have routes attribute
    assert hasattr(fastapi_app, "routes")


def test_lino_api_custom_title():
    api = LinoAPI(title="My Custom API")
    fastapi_app = api.get_fastapi_app()
    assert fastapi_app.title == "My Custom API"


def test_lino_api_register_get_endpoint():
    api = LinoAPI()

    @api.get("/test")
    def test_endpoint():
        return {"status": "ok"}

    fastapi_app = api.get_fastapi_app()
    routes = [route.path for route in fastapi_app.routes if hasattr(route, "path")]
    assert "/test" in routes


def test_lino_content_type():
    assert LINO_CONTENT_TYPE == "text/lino"


def test_encode_decode_simple_object():
    original = {"name": "test", "value": 42}
    assert decode(encode(original)) == original


def test_encode_decode_nested_object():
    original = {
        "user": {
            "name": "Alice",
            "age": 30,
        },
        "items": [1, 2, 3],
    }
    assert decode(encode(original)) == original


def test_encode_decode_special_values():
    original = {
        "null_value": None,
        "bool_true": True,
        "bool_false": False,
        "integer": 123,
        "float_val": 3.14,
        "string": "hello world",
        "array": [1, "two", True],
    }
    assert decode(encode(original)) == original


def test_lino_response_content_type():
    response = LinoResponse(content={"test": "data"})
    assert response.media_type == LINO_CONTENT_TYPE


def test_lino_response_encodes_content():
    data = {"message": "hello"}
    response = LinoResponse(content=data)
    assert decode(response.body.decode("utf-8")) == data


def test_lino_response_status_code():
    response = LinoResponse(content={"error": "not found"}, status_code=404)
    assert response.status_code == 404
