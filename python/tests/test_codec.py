"""Tests for the codec layer (specification sections 2 and 3)."""

import pytest

from lino_rest_api.codec import (
    decode,
    decode_from,
    decode_single_line,
    encode,
    encode_compact_notation,
    encode_for,
    encode_single_line,
)
from lino_rest_api.media_type import (
    JSON_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_PROBLEM_CONTENT_TYPE,
)


def test_encode_produces_readable_indented_links_notation():
    assert encode({"name": "Alice", "age": 30}) == '(\n  name "Alice"\n  age 30\n)'


def test_encode_renders_nested_structures_with_indentation():
    assert (
        encode({"user": {"tags": ["a", "b"]}})
        == '(\n  user (\n    tags (\n      "a"\n      "b"\n    )\n  )\n)'
    )


def test_decode_is_the_inverse_of_encode():
    value = {
        "name": "Alice",
        "age": 30,
        "active": True,
        "missing": None,
        "tags": ["developer", "python"],
        "nested": {"deep": {"value": 1.5}},
    }
    assert decode(encode(value)) == value


@pytest.mark.parametrize(
    "value", [0, 1, -1, 1.5, "", "text", True, False, None]
)
def test_scalars_round_trip(value):
    assert decode(encode(value)) == value


def test_encode_single_line_keeps_the_document_on_one_line():
    line = encode_single_line({"a": 1, "b": [2, 3]})
    assert "\n" not in line
    assert decode_single_line(line) == {"a": 1, "b": [2, 3]}


def test_the_compact_representation_preserves_shared_references():
    shared = {"id": 1}
    compact = encode_compact_notation({"left": shared, "right": shared})
    decoded = decode(compact)
    assert decoded["left"] == decoded["right"] == {"id": 1}


def test_encode_for_dispatches_on_the_media_type():
    value = {"a": 1}
    assert encode_for(value, LINO_CONTENT_TYPE) == encode(value)
    assert encode_for(value, LINO_LINE_CONTENT_TYPE) == encode_single_line(value)
    assert encode_for(value, LINO_COMPACT_CONTENT_TYPE) == encode_compact_notation(value)
    assert encode_for(value, JSON_CONTENT_TYPE) == '{"a":1}'


def test_decode_from_dispatches_on_the_media_type():
    assert decode_from("(\n  a 1\n)", LINO_CONTENT_TYPE) == {"a": 1}
    assert decode_from("(o: (a 1))", LINO_LINE_CONTENT_TYPE) == {"a": 1}
    assert decode_from('{"a":1}', JSON_CONTENT_TYPE) == {"a": 1}


def test_problem_media_types_decode_as_their_base_representation():
    assert decode_from("(\n  status 404\n)", LINO_PROBLEM_CONTENT_TYPE) == {
        "status": 404
    }


def test_encode_for_rejects_an_unknown_media_type():
    with pytest.raises(TypeError):
        encode_for({}, "image/png")
