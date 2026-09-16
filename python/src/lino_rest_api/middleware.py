"""
The request and response halves of the specification, expressed as plain
functions: body decoding (section 2.1), content negotiation (section 2.1), entity
tags (section 7) and problem details (section 5).

:class:`lino_rest_api.app.LinoApp` is built from these helpers, and any other
framework can be wired to the same behaviour by calling them directly.

The FastAPI adapter (:class:`LinoRequest`, :class:`LinoResponse` and
:func:`lino_request_handler`) is re-exported here so that code written against
earlier releases keeps working. Those names are resolved on first use, so the
rest of this module works without FastAPI installed.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .codec import decode_from, encode_for
from .etag import compute_etag, evaluate_preconditions
from .media_type import (
    JSON_CONTENT_TYPE,
    JSON_PROBLEM_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_PROBLEM_CONTENT_TYPE,
    SUPPORTED_MEDIA_TYPES,
    is_decodable_media_type,
    negotiate_media_type,
    parse_content_type,
    problem_media_type,
    with_charset,
)
from .problem import LinoHttpError, to_http_error
from .response import EMPTY

__all__ = [
    "DEFAULT_MAX_BODY_BYTES",
    "JSON_CONTENT_TYPE",
    "JSON_PROBLEM_CONTENT_TYPE",
    "LINO_COMPACT_CONTENT_TYPE",
    "LINO_CONTENT_TYPE",
    "LINO_LINE_CONTENT_TYPE",
    "LINO_PROBLEM_CONTENT_TYPE",
    "LinoAPI",
    "LinoAPIRoute",
    "LinoRequest",
    "LinoResponse",
    "ResponseParts",
    "append_vary",
    "build_problem_response",
    "build_response",
    "decode_request_body",
    "lino_request_handler",
    "negotiate_request",
]

if TYPE_CHECKING:  # Resolved at runtime by __getattr__ below.
    from .fastapi_adapter import (
        LinoAPI,
        LinoAPIRoute,
        LinoRequest,
        LinoResponse,
        lino_request_handler,
    )

#: Names served from :mod:`lino_rest_api.fastapi_adapter` on first use.
_FASTAPI_ADAPTER_NAMES = frozenset(
    {"LinoAPI", "LinoAPIRoute", "LinoRequest", "LinoResponse", "lino_request_handler"}
)

#: Largest request body accepted by default, in bytes.
DEFAULT_MAX_BODY_BYTES = 1024 * 1024


def __getattr__(name: str) -> Any:
    """
    Resolve the FastAPI adapter names on first use.

    Args:
        name: Attribute name

    Returns:
        The requested attribute

    Raises:
        AttributeError: When the name is not exported by this module
    """
    if name in _FASTAPI_ADAPTER_NAMES:
        from . import fastapi_adapter

        return getattr(fastapi_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass
class ResponseParts:
    """A response ready to be written to the wire."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


def append_vary(headers: dict[str, str], field_name: str) -> None:
    """
    Add a field name to ``Vary`` without repeating it.

    Both content negotiation and CORS extend ``Vary``; a plain assignment from
    either of them would silently drop the other one's contribution.

    Args:
        headers: Response headers, modified in place
        field_name: Header field name to add
    """
    current = headers.get("Vary", "")
    existing = [entry.strip() for entry in current.split(",") if entry.strip()]
    if any(entry.lower() == field_name.lower() for entry in existing):
        return
    headers["Vary"] = ", ".join([*existing, field_name])


def negotiate_request(
    headers: Mapping[str, str],
    supported: list[str] | None = None,
) -> str:
    """
    Select the representation to produce for a request.

    Args:
        headers: Request headers, lower-cased names
        supported: Representations the server can produce

    Returns:
        Selected media type

    Raises:
        LinoHttpError: 406 when no supported representation is acceptable
    """
    candidates = SUPPORTED_MEDIA_TYPES if supported is None else supported
    accept = headers.get("accept")
    selected = negotiate_media_type(accept, candidates)
    if selected is None:
        raise LinoHttpError(
            406,
            f"No acceptable representation for Accept: {accept}",
            extensions={"supported": list(candidates)},
        )
    return selected


def decode_request_body(
    raw: bytes,
    content_type: str | None,
    *,
    max_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> tuple[Any, str | None]:
    """
    Decode a request body according to its ``Content-Type``.

    Args:
        raw: Raw request body
        content_type: Raw ``Content-Type`` header value
        max_bytes: Largest accepted body

    Returns:
        Decoded body (None when empty) and the media type it arrived in

    Raises:
        LinoHttpError: 413 when too large, 415 when unsupported, 400 when malformed
    """
    if len(raw) > max_bytes:
        raise LinoHttpError(
            413,
            f"Request body exceeds {max_bytes} bytes",
            headers={"Connection": "close"},
        )

    media_type = parse_content_type(content_type)
    if not media_type:
        return None, None

    if not is_decodable_media_type(media_type):
        raise LinoHttpError(
            415,
            f"Unsupported request media type: {media_type}",
            extensions={"supported": list(SUPPORTED_MEDIA_TYPES)},
        )

    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return None, media_type

    try:
        return decode_from(text, media_type), media_type
    except LinoHttpError:
        raise
    except Exception as error:
        raise LinoHttpError(
            400,
            f"Malformed {media_type} request body: {error}",
        ) from error


def build_response(
    value: Any,
    *,
    status: int = 200,
    media_type: str = LINO_CONTENT_TYPE,
    headers: dict[str, str] | None = None,
    request_headers: Mapping[str, str] | None = None,
    method: str = "GET",
    etag: bool = True,
    preconditions: bool | None = None,
    require_precondition: bool = False,
    raw: bool = False,
) -> ResponseParts:
    """
    Encode a value as the negotiated representation.

    Args:
        value: Value to encode, or :data:`lino_rest_api.response.EMPTY` for an
            empty body
        status: HTTP status code
        media_type: Negotiated representation
        headers: Extra response headers
        request_headers: Request headers, lower-cased names
        method: HTTP method of the request
        etag: Emit an ``ETag``
        preconditions: Evaluate conditional headers (default: safe methods only)
        require_precondition: Demand ``If-Match`` on unsafe methods
        raw: Send the value as the body verbatim instead of encoding it

    Returns:
        Response ready to be written

    Raises:
        LinoHttpError: 412 or 428 when a precondition fails
    """
    response_headers = dict(headers or {})
    append_vary(response_headers, "Accept")

    if status == 204 or value is EMPTY:
        return ResponseParts(204 if status == 200 else status, response_headers, "")

    body = str(value) if raw else encode_for(value, media_type)

    if etag:
        tag = compute_etag(body)
        response_headers["ETag"] = tag

        # Preconditions on unsafe methods have to be evaluated against the
        # *current* representation before the change is applied, which only the
        # route handler can do; here the body is already the new representation.
        safe = method in ("GET", "HEAD")
        evaluate = preconditions if preconditions is not None else safe
        if evaluate and evaluate_preconditions(
            request_headers or {},
            method,
            tag,
            require_precondition=require_precondition,
        ).not_modified:
            return ResponseParts(304, response_headers, "")

    response_headers["Content-Type"] = with_charset(media_type)
    return ResponseParts(status, response_headers, body)


def build_problem_response(
    error: BaseException,
    *,
    media_type: str = LINO_CONTENT_TYPE,
    instance: str | None = None,
    expose_traceback: bool = False,
) -> ResponseParts:
    """
    Render an exception as problem details (specification section 5).

    Args:
        error: Raised exception
        media_type: Negotiated representation
        instance: URI of this occurrence
        expose_traceback: Attach the traceback to 5xx problems

    Returns:
        Response ready to be written
    """
    http_error = to_http_error(error)
    if expose_traceback and http_error.status >= 500:
        import traceback

        http_error.extensions = {
            **http_error.extensions,
            "traceback": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }

    problem = http_error.to_problem(instance)
    headers = dict(http_error.headers)
    append_vary(headers, "Accept")
    headers["Content-Type"] = with_charset(problem_media_type(media_type))

    return ResponseParts(http_error.status, headers, encode_for(problem, media_type))
