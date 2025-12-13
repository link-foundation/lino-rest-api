"""
lino-rest-api - REST API framework using Links Notation instead of JSON.

This module provides middleware and utilities for FastAPI to handle
requests and responses in Links Notation (LINO) format.
"""

from .app import LinoAPI
from .middleware import (
    LINO_CONTENT_TYPE,
    LinoRequest,
    LinoResponse,
    lino_request_handler,
)

__version__ = "0.1.0"
__all__ = [
    "LinoAPI",
    "LinoRequest",
    "LinoResponse",
    "lino_request_handler",
    "LINO_CONTENT_TYPE",
]
