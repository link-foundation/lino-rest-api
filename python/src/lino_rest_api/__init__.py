"""
lino-rest-api — a REST API framework that speaks Links Notation instead of JSON.

The public surface follows the LINO REST API specification shipped in
``docs/spec/README.md``: content negotiation, problem details, collections,
conditional requests, CORS and a machine-readable service description.
"""

from typing import TYPE_CHECKING

from .app import (
    DESCRIPTION_PATH,
    HTTP_METHODS,
    OPENAPI_PATH,
    LinoApp,
    create_lino_app,
)
from .client import (
    DEFAULT_ACCEPT,
    AsyncLinoClient,
    LinoClient,
    LinoClientError,
    build_query_string,
    create_async_lino_client,
    create_lino_client,
    query_value,
)
from .codec import (
    decode,
    decode_from,
    decode_single_line,
    encode,
    encode_compact_notation,
    encode_for,
    encode_single_line,
)
from .collection import (
    apply_collection_query,
    collection_envelope,
    matches_filters,
    pagination_link_header,
    project_fields,
    sort_items,
)
from .cors import (
    DEFAULT_ALLOWED_HEADERS,
    DEFAULT_EXPOSED_HEADERS,
    cors_headers,
)
from .description import (
    LINO_API_DESCRIPTION_VERSION,
    info_object,
    openapi_document,
    path_parameters,
    service_description,
    to_openapi_path,
)
from .etag import (
    compute_etag,
    etag_matches,
    evaluate_preconditions,
    parse_etag_list,
)
from .media_type import (
    JSON_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_PROBLEM_CONTENT_TYPE,
    SUPPORTED_MEDIA_TYPES,
    is_decodable_media_type,
    negotiate_media_type,
    parse_accept,
    parse_content_type,
    with_charset,
)
from .middleware import (
    DEFAULT_MAX_BODY_BYTES,
    append_vary,
    build_problem_response,
    build_response,
    decode_request_body,
    negotiate_request,
)
from .problem import (
    PROBLEM_TYPE_BASE,
    LinoHttpError,
    problem_details,
    problem_slug,
    reason_phrase,
    to_http_error,
    validation_error,
)
from .query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    RESERVED_QUERY_PARAMETERS,
    parse_collection_query,
    parse_fields,
    parse_scalar,
    parse_sort,
)
from .request import LinoHttpRequest
from .resource import (
    RESOURCE_OPERATIONS,
    register_resource,
    representation_etag,
)
from .response import (
    EMPTY,
    LinoResult,
    accepted,
    created,
    no_content,
    ok,
    raw_response,
    status,
)
from .router import IMPLICIT_METHODS, RouteTable, compile_path_pattern
from .store import MemoryStore

__version__ = "0.2.0"

if TYPE_CHECKING:  # Resolved at runtime by __getattr__ below.
    from .fastapi_adapter import (
        LinoAPI,
        LinoAPIRoute,
        LinoRequest,
        LinoResponse,
        lino_request_handler,
    )

#: Names served from :mod:`lino_rest_api.fastapi_adapter` on first use, so that
#: the package imports without FastAPI installed (``pip install
#: lino-rest-api[fastapi]`` enables them).
_FASTAPI_ADAPTER_NAMES = frozenset(
    {"LinoAPI", "LinoAPIRoute", "LinoRequest", "LinoResponse", "lino_request_handler"}
)


def __getattr__(name: str):
    """
    Resolve the FastAPI adapter names on first use.

    Args:
        name: Attribute name

    Returns:
        The requested attribute

    Raises:
        AttributeError: When the name is not exported by this package
    """
    if name in _FASTAPI_ADAPTER_NAMES:
        from . import fastapi_adapter

        value = getattr(fastapi_adapter, name)
        # Bind it in the package, so that later lookups skip this function and
        # tools that read the module dictionary — pdoc, for one — find it.
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "DEFAULT_ACCEPT",
    "DEFAULT_ALLOWED_HEADERS",
    "DEFAULT_EXPOSED_HEADERS",
    "DEFAULT_LIMIT",
    "DEFAULT_MAX_BODY_BYTES",
    "DESCRIPTION_PATH",
    "EMPTY",
    "HTTP_METHODS",
    "IMPLICIT_METHODS",
    "JSON_CONTENT_TYPE",
    "LINO_API_DESCRIPTION_VERSION",
    "LINO_COMPACT_CONTENT_TYPE",
    "LINO_CONTENT_TYPE",
    "LINO_LINE_CONTENT_TYPE",
    "LINO_PROBLEM_CONTENT_TYPE",
    "MAX_LIMIT",
    "OPENAPI_PATH",
    "PROBLEM_TYPE_BASE",
    "RESERVED_QUERY_PARAMETERS",
    "RESOURCE_OPERATIONS",
    "SUPPORTED_MEDIA_TYPES",
    "AsyncLinoClient",
    "LinoAPI",
    "LinoAPIRoute",
    "LinoApp",
    "LinoClient",
    "LinoClientError",
    "LinoHttpError",
    "LinoHttpRequest",
    "LinoRequest",
    "LinoResponse",
    "LinoResult",
    "MemoryStore",
    "RouteTable",
    "accepted",
    "append_vary",
    "apply_collection_query",
    "build_problem_response",
    "build_query_string",
    "query_value",
    "build_response",
    "collection_envelope",
    "compile_path_pattern",
    "compute_etag",
    "cors_headers",
    "create_async_lino_client",
    "create_lino_app",
    "create_lino_client",
    "created",
    "decode",
    "decode_from",
    "decode_request_body",
    "decode_single_line",
    "encode",
    "encode_compact_notation",
    "encode_for",
    "encode_single_line",
    "etag_matches",
    "evaluate_preconditions",
    "is_decodable_media_type",
    "lino_request_handler",
    "matches_filters",
    "negotiate_media_type",
    "negotiate_request",
    "no_content",
    "ok",
    "info_object",
    "openapi_document",
    "pagination_link_header",
    "parse_accept",
    "parse_collection_query",
    "parse_content_type",
    "parse_etag_list",
    "parse_fields",
    "parse_scalar",
    "parse_sort",
    "path_parameters",
    "problem_details",
    "problem_slug",
    "project_fields",
    "raw_response",
    "reason_phrase",
    "register_resource",
    "representation_etag",
    "service_description",
    "sort_items",
    "status",
    "to_http_error",
    "to_openapi_path",
    "validation_error",
    "with_charset",
]
