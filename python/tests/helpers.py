"""
Shared helpers for the HTTP level tests.

The JavaScript suite starts a server on an ephemeral port; here applications are
driven in process through :class:`httpx.ASGITransport`, which speaks the same
ASGI protocol a real server does without the cost of a socket. One suite,
``test_server.py``, does run a real server, so both paths stay covered.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from lino_rest_api import AsyncLinoClient

#: Host used by the in-process transport.
BASE_URL = "http://testserver"


@dataclass
class Served:
    """A live application together with a raw and a Links Notation client."""

    base: str
    http: httpx.AsyncClient
    client: AsyncLinoClient

    async def raw(self, path: str, method: str = "GET", **options: Any) -> httpx.Response:
        """
        Send a request without any Links Notation handling.

        Args:
            path: Request path
            method: HTTP method
            **options: Options forwarded to ``httpx``

        Returns:
            Raw response
        """
        return await self.http.request(method, f"{self.base}{path}", **options)


@asynccontextmanager
async def serve(app: Any, **client_options: Any) -> AsyncIterator[Served]:
    """
    Run an application in process and hand out clients for it.

    Args:
        app: ASGI application to serve
        **client_options: Options for the :class:`AsyncLinoClient`

    Yields:
        Handle carrying the base URL and the clients
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport) as http:
        client = AsyncLinoClient(BASE_URL, client=http, **client_options)
        yield Served(BASE_URL, http, client)


def content_type(response: httpx.Response) -> str:
    """
    The bare media type of a response, without its parameters.

    Args:
        response: Response to inspect

    Returns:
        Media type, "" when the response carries none
    """
    return response.headers.get("content-type", "").split(";")[0].strip()


def vary_fields(response: httpx.Response) -> list[str]:
    """
    The field names listed in ``Vary``, lower-cased.

    Args:
        response: Response to inspect

    Returns:
        Field names
    """
    raw = response.headers.get("vary", "")
    return [field.strip().lower() for field in raw.split(",") if field.strip()]
