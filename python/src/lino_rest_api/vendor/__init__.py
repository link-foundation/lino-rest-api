"""
Vendored dependencies for lino-rest-api.

This module contains vendored dependencies that are not yet available
on PyPI. They will be replaced with proper package imports once published.
"""

from .codec import ObjectCodec, decode, encode

__all__ = ["ObjectCodec", "encode", "decode"]
