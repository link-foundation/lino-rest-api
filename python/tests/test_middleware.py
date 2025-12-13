"""Tests for LINO middleware."""

import pytest
from lino_rest_api.vendor import encode, decode

from lino_rest_api.middleware import (
    LinoResponse,
    LINO_CONTENT_TYPE,
)


def test_lino_content_type():
    """Test that LINO content type is correct."""
    assert LINO_CONTENT_TYPE == "text/lino"


def test_encode_decode_simple_object():
    """Test encode/decode roundtrip for simple objects."""
    original = {"name": "test", "value": 42}
    encoded = encode(original)
    decoded = decode(encoded)

    assert decoded == original


def test_encode_decode_nested_object():
    """Test encode/decode roundtrip for nested objects."""
    original = {
        "user": {
            "name": "Alice",
            "age": 30,
        },
        "items": [1, 2, 3],
    }
    encoded = encode(original)
    decoded = decode(encoded)

    assert decoded == original


def test_encode_decode_special_values():
    """Test encode/decode roundtrip for special values."""
    original = {
        "null_value": None,
        "bool_true": True,
        "bool_false": False,
        "integer": 123,
        "float_val": 3.14,
        "string": "hello world",
        "array": [1, "two", True],
    }
    encoded = encode(original)
    decoded = decode(encoded)

    assert decoded == original


def test_lino_response_content_type():
    """Test LinoResponse uses correct content type."""
    response = LinoResponse(content={"test": "data"})

    assert response.media_type == LINO_CONTENT_TYPE


def test_lino_response_encodes_content():
    """Test LinoResponse properly encodes content."""
    data = {"message": "hello"}
    response = LinoResponse(content=data)

    # The body should be encoded LINO
    body = response.body.decode("utf-8")
    decoded = decode(body)

    assert decoded == data


def test_lino_response_status_code():
    """Test LinoResponse respects status code."""
    response = LinoResponse(content={"error": "not found"}, status_code=404)

    assert response.status_code == 404
