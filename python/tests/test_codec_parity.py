"""
Cross-language parity of the vendored codec.

``lino-objects-codec`` is not on PyPI, so the Python package carries a copy of
its sources (see ``src/lino_rest_api/vendor/lino_objects_codec/VENDORED.md``).
These tests run the shared conformance fixtures published by that project, which
every implementation must encode to the same bytes, so the copy cannot drift
from the npm package the JavaScript side depends on without the suite failing.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from lino_rest_api.codec import (
    decode,
    decode_line,
    encode,
    encode_line,
)

FIXTURES = Path(__file__).parent / "fixtures" / "readable-format-cases.json"
LANGUAGE = "python"


def _materialise(encoded: dict[str, Any]) -> Any:
    """
    Turn one fixture value into the Python value it denotes.

    Args:
        encoded: Single key object naming the type of the value

    Returns:
        The Python value
    """
    (kind, payload), = encoded.items()
    if kind == "null":
        return None
    if kind in ("bool", "int", "str"):
        return payload
    if kind == "float":
        if isinstance(payload, str):
            return {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}[payload]
        return float(payload)
    if kind == "array":
        return [_materialise(item) for item in payload]
    if kind == "object":
        return {key: _materialise(value) for key, value in payload}
    raise AssertionError(f"Unknown fixture value kind: {kind}")


def _equal(left: Any, right: Any) -> bool:
    """
    Compare two decoded values, treating NaN as equal to itself.

    Args:
        left: First value
        right: Second value

    Returns:
        True when the values match
    """
    if isinstance(left, float) and isinstance(right, float):
        return left == right or (math.isnan(left) and math.isnan(right))
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(map(_equal, left, right))
    if isinstance(left, dict) and isinstance(right, dict):
        return list(left) == list(right) and all(_equal(left[key], right[key]) for key in left)
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


def _cases() -> list[Any]:
    """
    Load the fixture cases this implementation has to satisfy.

    Returns:
        Cases as pytest parameters
    """
    document = json.loads(FIXTURES.read_text(encoding="utf-8"))
    parameters = []
    for case in document["cases"]:
        skip = case.get("skip", {}).get(LANGUAGE)
        marks = [pytest.mark.skip(reason=skip)] if skip else []
        parameters.append(pytest.param(case, marks=marks, id=case["name"]))
    return parameters


@pytest.mark.parametrize("case", _cases())
def test_indented_encoding_is_byte_identical_across_languages(case: dict[str, Any]) -> None:
    """The indented form of every shared fixture matches the published bytes."""
    assert encode(_materialise(case["value"])) == case["text"]


@pytest.mark.parametrize("case", _cases())
def test_single_line_encoding_is_byte_identical_across_languages(case: dict[str, Any]) -> None:
    """The single line form of every shared fixture matches the published bytes."""
    assert encode_line(_materialise(case["value"])) == case["line"]


@pytest.mark.parametrize("case", _cases())
def test_both_forms_round_trip(case: dict[str, Any]) -> None:
    """Decoding either published form returns the original value."""
    value = _materialise(case["value"])
    assert _equal(decode(case["text"]), value)
    assert _equal(decode_line(case["line"]), value)
