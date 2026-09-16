"""
Machine-readable service description (specification section 9).

The same route registry is rendered twice: once as the native Links Notation
description served at ``/.well-known/lino-api``, and once as an OpenAPI 3.1
document served at ``/.well-known/openapi.json`` so that existing tooling keeps
working against a Links Notation API.
"""

import re
from typing import Any

from .media_type import SUPPORTED_MEDIA_TYPES

#: Version of the description document this package emits.
LINO_API_DESCRIPTION_VERSION = "1.0"

LINO_SCHEMA = {
    "description": (
        "Links Notation document, see "
        "https://github.com/link-foundation/links-notation"
    ),
    "type": "string",
}


def service_description(
    info: dict[str, str],
    routes: list[dict[str, Any]],
    media_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build the native service description.

    Args:
        info: ``title`` and ``version`` of the service
        routes: Route descriptions
        media_types: Representations the service can produce

    Returns:
        Description ready to be encoded as Links Notation
    """
    return {
        "lino_api": LINO_API_DESCRIPTION_VERSION,
        "info": {"title": info["title"], "version": info["version"]},
        "media_types": list(
            SUPPORTED_MEDIA_TYPES if media_types is None else media_types
        ),
        "routes": routes,
    }


def to_openapi_path(path: str) -> str:
    """
    Convert a ``:parameter`` path to the OpenAPI template syntax.

    Args:
        path: Path pattern with ``:parameter`` segments

    Returns:
        Path template with ``{parameter}`` segments
    """
    return re.sub(r":([A-Za-z0-9_]+)", r"{\1}", path)


def path_parameters(path: str) -> list[str]:
    """
    Extract the path parameters of a path pattern.

    Args:
        path: Path pattern

    Returns:
        Parameter names
    """
    return re.findall(r":([A-Za-z0-9_]+)", path)


def openapi_document(
    info: dict[str, str],
    routes: list[dict[str, Any]],
    media_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build an OpenAPI 3.1 document describing the service.

    Every request and response body is declared for all negotiable media types, so
    that a generated client knows it may ask for ``text/lino``.

    Args:
        info: ``title`` and ``version`` of the service
        routes: Route descriptions
        media_types: Representations the service can produce

    Returns:
        OpenAPI 3.1 document
    """
    types = SUPPORTED_MEDIA_TYPES if media_types is None else media_types
    content = {media_type: {"schema": LINO_SCHEMA} for media_type in types}

    paths: dict[str, Any] = {}
    for route in routes:
        template = to_openapi_path(route["path"])
        parameters = [
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
            for name in path_parameters(route["path"])
        ]

        paths[template] = {}
        for method in route["methods"]:
            operation: dict[str, Any] = {
                "summary": route.get("summary") or f"{method} {route['path']}",
                "responses": {
                    "200": {"description": "Success", "content": content},
                    "default": {
                        "description": "RFC 9457 problem details in Links Notation",
                        "content": content,
                    },
                },
            }
            if parameters:
                operation["parameters"] = parameters
            if method in ("POST", "PUT", "PATCH"):
                operation["requestBody"] = {"required": True, "content": content}
            paths[template][method.lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {"title": info["title"], "version": info["version"]},
        "paths": paths,
    }
