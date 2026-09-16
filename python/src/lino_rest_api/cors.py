"""
Cross-origin resource sharing (specification section 8).
"""

from typing import Any

#: Headers a browser must be allowed to send to negotiate Links Notation.
DEFAULT_ALLOWED_HEADERS = [
    "Content-Type",
    "Accept",
    "Authorization",
    "If-Match",
    "If-None-Match",
]

#: Headers a browser must be allowed to read to follow the protocol.
DEFAULT_EXPOSED_HEADERS = ["ETag", "Link", "Location", "Allow"]

DEFAULT_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]


def cors_headers(
    options: dict[str, Any] | bool | None = None,
    request_origin: str | None = None,
) -> dict[str, str]:
    """
    Build the CORS response headers for a request.

    Args:
        options: Policy with ``origin``, ``methods``, ``allowed_headers``,
            ``exposed_headers``, ``credentials`` and ``max_age`` members; True
            selects the permissive default policy
        request_origin: ``Origin`` header of the request

    Returns:
        Response headers ({} when the origin is not allowed)
    """
    policy: dict[str, Any] = {} if options in (None, True, False) else dict(options)

    origin = policy.get("origin", "*")
    methods = policy.get("methods", DEFAULT_METHODS)
    allowed_headers = policy.get("allowed_headers", DEFAULT_ALLOWED_HEADERS)
    exposed_headers = policy.get("exposed_headers", DEFAULT_EXPOSED_HEADERS)
    credentials = policy.get("credentials", False)
    max_age = policy.get("max_age", 600)

    allowed_origins = origin if isinstance(origin, list | tuple) else [origin]
    allow_origin = None
    if "*" in allowed_origins:
        allow_origin = request_origin if credentials and request_origin else "*"
    elif request_origin and request_origin in allowed_origins:
        allow_origin = request_origin

    if not allow_origin:
        return {}

    headers = {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Methods": ", ".join(methods),
        "Access-Control-Allow-Headers": ", ".join(allowed_headers),
        "Access-Control-Expose-Headers": ", ".join(exposed_headers),
        "Access-Control-Max-Age": str(max_age),
    }
    if credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers
