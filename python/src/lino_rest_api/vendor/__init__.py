"""
Vendored dependencies.

``lino-objects-codec`` is published to npm and to crates.io but not to PyPI, so
:mod:`lino_rest_api.vendor.lino_objects_codec` holds a verbatim copy of its
Python implementation. See ``lino_objects_codec/VENDORED.md`` for the pinned
upstream commit, and ``scripts/sync-vendored-codec.mjs`` for how to refresh it.
"""

from .lino_objects_codec import (
    ObjectCodec,
    decode,
    decode_compact,
    decode_line,
    encode,
    encode_compact,
    encode_line,
    is_compact_notation,
)

__all__ = [
    "ObjectCodec",
    "encode",
    "encode_line",
    "encode_compact",
    "decode",
    "decode_line",
    "decode_compact",
    "is_compact_notation",
]
