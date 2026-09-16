"""
Explicit response values.

A handler may return a plain value, which is sent as 200, or one of these results
when it needs to control the status code or the headers.
"""

from dataclasses import dataclass, field
from typing import Any

#: Marker distinguishing "no body" from an explicit ``None`` body.
EMPTY = ...


@dataclass
class LinoResult:
    """A handler result carrying a status code and headers alongside the value."""

    value: Any = EMPTY
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    etag: bool = True
    preconditions: bool | None = None
    require_precondition: bool = False
    media_type: str | None = None
    raw: bool = False


def ok(value: Any, headers: dict[str, str] | None = None) -> LinoResult:
    """
    A 200 OK carrying a value.

    Args:
        value: Value to encode
        headers: Response headers

    Returns:
        Handler result
    """
    return LinoResult(value, 200, dict(headers or {}))


def created(
    value: Any,
    location: str,
    headers: dict[str, str] | None = None,
) -> LinoResult:
    """
    A 201 Created carrying a value and a ``Location``.

    Args:
        value: Value to encode
        location: URI of the created resource
        headers: Additional response headers

    Returns:
        Handler result
    """
    return LinoResult(value, 201, {"Location": location, **(headers or {})})


def accepted(value: Any, headers: dict[str, str] | None = None) -> LinoResult:
    """
    A 202 Accepted carrying a value.

    Args:
        value: Value to encode
        headers: Response headers

    Returns:
        Handler result
    """
    return LinoResult(value, 202, dict(headers or {}))


def no_content(headers: dict[str, str] | None = None) -> LinoResult:
    """
    A 204 No Content.

    Args:
        headers: Response headers

    Returns:
        Handler result
    """
    return LinoResult(EMPTY, 204, dict(headers or {}))


def status(
    status_code: int,
    value: Any = EMPTY,
    headers: dict[str, str] | None = None,
) -> LinoResult:
    """
    A response with an explicit status code.

    Args:
        status_code: HTTP status code
        value: Value to encode
        headers: Response headers

    Returns:
        Handler result
    """
    return LinoResult(value, status_code, dict(headers or {}))


def raw_response(
    body: str,
    media_type: str,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> LinoResult:
    """
    A response whose body is already encoded, bypassing negotiation.

    Used for representations that are defined by their own media type, such as
    the OpenAPI document of specification section 9.

    Args:
        body: Encoded body
        media_type: Media type of the body
        status_code: HTTP status code
        headers: Response headers

    Returns:
        Handler result
    """
    return LinoResult(
        body,
        status_code,
        dict(headers or {}),
        media_type=media_type,
        raw=True,
    )
