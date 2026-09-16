"""
Codec layer: every conversion between Python values and the wire.

All Links Notation work is delegated to ``lino-objects-codec``, which produces
byte-identical readable output in JavaScript, Python, Rust and C#. That project
is not published to PyPI, so its Python implementation is vendored (see
:mod:`lino_rest_api.vendor`); this module adapts it and adds the media-type
dispatch described in ``docs/spec/README.md`` section 2.
"""

import json
from typing import Any

from .media_type import (
    JSON_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    normalize_media_type,
)
from .vendor import decode as _decode_any
from .vendor import decode_line as _decode_line
from .vendor import encode as _encode_readable
from .vendor import encode_compact as _encode_compact
from .vendor import encode_line as _encode_line


def encode(value: Any) -> str:
    """
    Encode a value as readable, indented Links Notation.

    Args:
        value: Value to encode

    Returns:
        Readable Links Notation
    """
    return _encode_readable(value)


def decode(notation: str) -> Any:
    """
    Decode readable or compact Links Notation into a Python value.

    Args:
        notation: Links Notation document

    Returns:
        Decoded value
    """
    return _decode_any(notation)


def encode_single_line(value: Any) -> str:
    """
    Encode a value as single-line readable Links Notation.

    Args:
        value: Value to encode

    Returns:
        One line of readable Links Notation
    """
    return _encode_line(value)


def decode_single_line(notation: str) -> Any:
    """
    Decode one line of single-line readable Links Notation.

    Args:
        notation: One line of readable Links Notation

    Returns:
        Decoded value
    """
    return _decode_line(notation)


def encode_compact_notation(value: Any) -> str:
    """
    Encode a value as compact, type-tagged Links Notation.

    This is the only representation that preserves shared object identity and
    circular references.

    Args:
        value: Value to encode

    Returns:
        Compact Links Notation
    """
    return _encode_compact(value)


def encode_for(value: Any, media_type: str) -> str:
    """
    Encode a value for a concrete media type.

    Args:
        value: Value to encode
        media_type: One of the media types of the specification

    Returns:
        Encoded representation

    Raises:
        TypeError: When the media type is not a representation of this API
    """
    resolved = normalize_media_type(media_type)
    if resolved == LINO_CONTENT_TYPE:
        return encode(value)
    if resolved == LINO_LINE_CONTENT_TYPE:
        return encode_single_line(value)
    if resolved == LINO_COMPACT_CONTENT_TYPE:
        return encode_compact_notation(value)
    if resolved == JSON_CONTENT_TYPE:
        # The separators and the raw Unicode match ``JSON.stringify`` byte for
        # byte, so that the entity tag of a representation (section 7) is the
        # same whichever implementation of this specification serves it.
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    raise TypeError(f"Cannot encode to media type: {media_type}")


def decode_from(body: str, media_type: str) -> Any:
    """
    Decode a representation of a concrete media type.

    Args:
        body: Raw request or response body
        media_type: Media type the body was sent with

    Returns:
        Decoded value

    Raises:
        TypeError: When the media type is not a representation of this API
    """
    resolved = normalize_media_type(media_type)
    if resolved in (LINO_CONTENT_TYPE, LINO_COMPACT_CONTENT_TYPE):
        return decode(body)
    if resolved == LINO_LINE_CONTENT_TYPE:
        return decode_single_line(body)
    if resolved == JSON_CONTENT_TYPE:
        return json.loads(body)
    raise TypeError(f"Cannot decode media type: {media_type}")


#: Python-idiomatic aliases matching the names of the vendored codec.
encode_line = encode_single_line
decode_line = decode_single_line
encode_compact = encode_compact_notation
