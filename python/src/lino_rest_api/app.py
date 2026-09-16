"""
The Links Notation REST API application.

An ASGI application implementing the behaviour the specification requires:
content negotiation, Links Notation bodies, problem details, automatic ``HEAD``,
automatic ``OPTIONS``, ``405 Method Not Allowed`` with ``Allow``, and a
machine-readable service description.

Being a plain ASGI application, it runs under uvicorn, hypercorn or any other
ASGI server, and it can be mounted inside a FastAPI or Starlette application.

:class:`LinoAPI`, the FastAPI wrapper of earlier releases, is re-exported here so
that ``from lino_rest_api.app import LinoAPI`` keeps working; it is resolved on
first use, so this module works without FastAPI installed.
"""

import inspect
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from .codec import decode, encode
from .cors import cors_headers
from .description import openapi_document, service_description
from .media_type import JSON_CONTENT_TYPE, LINO_CONTENT_TYPE
from .middleware import (
    DEFAULT_MAX_BODY_BYTES,
    ResponseParts,
    append_vary,
    build_problem_response,
    build_response,
    decode_request_body,
    negotiate_request,
)
from .problem import LinoHttpError
from .request import LinoHttpRequest
from .resource import register_resource
from .response import EMPTY, LinoResult, raw_response
from .router import RouteTable

__all__ = [
    "DESCRIPTION_PATH",
    "HTTP_METHODS",
    "OPENAPI_PATH",
    "LinoAPI",
    "LinoAPIRoute",
    "LinoApp",
    "create_lino_app",
    "decode",
    "encode",
    "LINO_CONTENT_TYPE",
]

#: Methods a handler can be registered for.
if TYPE_CHECKING:  # Resolved at runtime by __getattr__ below.
    from .fastapi_adapter import LinoAPI, LinoAPIRoute

#: Names served from :mod:`lino_rest_api.fastapi_adapter` on first use.
_FASTAPI_ADAPTER_NAMES = frozenset({"LinoAPI", "LinoAPIRoute"})


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


HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

#: Where the native service description lives (specification section 9).
DESCRIPTION_PATH = "/.well-known/lino-api"

#: Where the generated OpenAPI 3.1 document lives (specification section 9).
OPENAPI_PATH = "/.well-known/openapi.json"

Handler = Callable[[LinoHttpRequest], Any | Awaitable[Any]]


class LinoApp:
    """An ASGI application that speaks Links Notation."""

    def __init__(
        self,
        *,
        title: str = "LINO REST API",
        version: str = "1.0.0",
        description: str | None = None,
        cors: bool | dict[str, Any] | None = None,
        describe: bool = True,
        supported: list[str] | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        expose_traceback: bool = False,
        default_limit: int | None = None,
        max_limit: int | None = None,
    ) -> None:
        """
        Args:
            title: Service title used in the description
            version: Service version used in the description
            description: Prose description of the service
            cors: Enable CORS, optionally with a policy
            describe: Serve the service description
            supported: Representations the server may produce
            max_body_bytes: Largest accepted request body
            expose_traceback: Attach tracebacks to 5xx problems
            default_limit: Default collection page size
            max_limit: Largest collection page size
        """
        self.info: dict[str, str] = {"title": title, "version": version}
        if description:
            self.info["description"] = description
        self.cors = cors
        self.supported = supported
        self.max_body_bytes = max_body_bytes
        self.expose_traceback = expose_traceback
        self.routes = RouteTable()
        self.handlers: dict[tuple[str, str], Handler] = {}

        self.query_defaults: dict[str, int] = {}
        if default_limit is not None:
            self.query_defaults["default_limit"] = default_limit
        if max_limit is not None:
            self.query_defaults["max_limit"] = max_limit

        if describe:
            self._register_description()

    # Registration -----------------------------------------------------------

    def route(
        self,
        method: str,
        path: str,
        handler: Handler,
        meta: dict[str, Any] | None = None,
    ) -> "LinoApp":
        """
        Register a handler for a method and path.

        Args:
            method: HTTP method
            path: Path pattern, with ``:parameter`` segments
            handler: Route handler taking a :class:`LinoHttpRequest`
            meta: Description metadata, for example ``summary``

        Returns:
            This application, for chaining

        Raises:
            TypeError: When the method is not one of :data:`HTTP_METHODS`
        """
        normalized = method.upper()
        if normalized not in HTTP_METHODS:
            raise TypeError(f"Unsupported HTTP method: {method}")
        self.routes.register(normalized, path, meta)
        self.handlers[(normalized, path)] = handler
        return self

    def get(
        self, path: str, handler: Handler, meta: dict[str, Any] | None = None
    ) -> "LinoApp":
        """
        Register a ``GET`` handler.

        Args:
            path: Path pattern
            handler: Route handler
            meta: Description metadata

        Returns:
            This application, for chaining
        """
        return self.route("GET", path, handler, meta)

    def post(
        self, path: str, handler: Handler, meta: dict[str, Any] | None = None
    ) -> "LinoApp":
        """
        Register a ``POST`` handler.

        Args:
            path: Path pattern
            handler: Route handler
            meta: Description metadata

        Returns:
            This application, for chaining
        """
        return self.route("POST", path, handler, meta)

    def put(
        self, path: str, handler: Handler, meta: dict[str, Any] | None = None
    ) -> "LinoApp":
        """
        Register a ``PUT`` handler.

        Args:
            path: Path pattern
            handler: Route handler
            meta: Description metadata

        Returns:
            This application, for chaining
        """
        return self.route("PUT", path, handler, meta)

    def patch(
        self, path: str, handler: Handler, meta: dict[str, Any] | None = None
    ) -> "LinoApp":
        """
        Register a ``PATCH`` handler.

        Args:
            path: Path pattern
            handler: Route handler
            meta: Description metadata

        Returns:
            This application, for chaining
        """
        return self.route("PATCH", path, handler, meta)

    def delete(
        self, path: str, handler: Handler, meta: dict[str, Any] | None = None
    ) -> "LinoApp":
        """
        Register a ``DELETE`` handler.

        Args:
            path: Path pattern
            handler: Route handler
            meta: Description metadata

        Returns:
            This application, for chaining
        """
        return self.route("DELETE", path, handler, meta)

    def resource(self, path: str, store: Any, **options: Any) -> "LinoApp":
        """
        Register a CRUD resource, see :func:`lino_rest_api.resource.register_resource`.

        Args:
            path: Collection path
            store: Resource store
            **options: Resource options

        Returns:
            This application, for chaining
        """
        return register_resource(
            self, path, store, **{**self.query_defaults, **options}
        )

    def _register_description(self) -> None:
        """Register the service description routes of specification section 9."""
        self.get(
            DESCRIPTION_PATH,
            lambda request: self.describe(),
            {"summary": "Service description"},
        )
        self.get(
            OPENAPI_PATH,
            lambda request: raw_response(
                json.dumps(self.openapi(), indent=2) + "\n",
                JSON_CONTENT_TYPE,
            ),
            {"summary": "OpenAPI 3.1 description"},
        )

    # Description ------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """
        The native service description of specification section 9.

        Returns:
            Description document
        """
        return service_description(self.info, self.routes.describe(), self.supported)

    def openapi(self) -> dict[str, Any]:
        """
        The OpenAPI 3.1 rendering of the service description.

        Returns:
            OpenAPI document
        """
        return openapi_document(self.info, self.routes.describe(), self.supported)

    # Request handling -------------------------------------------------------

    async def handle(self, request: LinoHttpRequest) -> ResponseParts:
        """
        Run one decoded request through routing and the handler.

        Args:
            request: Decoded request

        Returns:
            Response ready to be written

        Raises:
            LinoHttpError: 404, 405 and anything a handler raises
        """
        matched = self.routes.match(request.path)
        if matched is None:
            raise LinoHttpError(404, f"No resource at {request.path}")

        entry, params = matched
        request.params = params
        allowed = self.routes.allowed_methods(request.path) or []

        method = request.method
        # HEAD is served by the GET handler with the body dropped, and OPTIONS is
        # answered from the route table unless a handler claims it.
        lookup = "GET" if method == "HEAD" and "GET" in entry.methods else method

        if method == "OPTIONS" and "OPTIONS" not in entry.methods:
            return ResponseParts(204, {"Allow": ", ".join(allowed)}, "")

        if lookup not in entry.methods:
            raise LinoHttpError(
                405,
                f"{method} is not allowed on {request.path}",
                headers={"Allow": ", ".join(allowed)},
            )

        handler = self.handlers[(lookup, entry.pattern)]
        result = handler(request)
        if inspect.isawaitable(result):
            result = await result

        if isinstance(result, LinoResult):
            return build_response(
                result.value,
                status=result.status,
                media_type=result.media_type or request.media_type,
                headers=result.headers,
                request_headers=request.headers,
                method=method,
                etag=result.etag,
                preconditions=result.preconditions,
                require_precondition=result.require_precondition,
                raw=result.raw,
            )

        if result is None:
            return build_response(
                EMPTY,
                status=204,
                media_type=request.media_type,
                request_headers=request.headers,
                method=method,
            )

        return build_response(
            result,
            media_type=request.media_type,
            request_headers=request.headers,
            method=method,
        )

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        """
        ASGI entry point.

        Args:
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] != "http":
            raise NotImplementedError(f"Unsupported scope type: {scope['type']}")

        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers", [])
        }
        method = scope["method"].upper()
        path = scope.get("path", "/")
        query_string = scope.get("query_string", b"").decode("latin-1")

        request = LinoHttpRequest(
            method=method,
            path=path,
            headers=headers,
            query_string=query_string,
            scope=scope,
            app=self,
        )

        extra_headers = self._cors_headers(headers)
        preflight = (
            method == "OPTIONS" and "access-control-request-method" in headers
        )

        media_type = LINO_CONTENT_TYPE
        try:
            if preflight and extra_headers:
                parts = ResponseParts(204, {}, "")
            else:
                media_type = negotiate_request(headers, self.supported)
                request.media_type = media_type
                raw = await self._read_body(receive)
                body, request_media_type = decode_request_body(
                    raw,
                    headers.get("content-type"),
                    max_bytes=self.max_body_bytes,
                )
                request.body = body
                request.request_media_type = request_media_type
                parts = await self.handle(request)
        except Exception as error:  # noqa: BLE001 - every error becomes a problem
            instance = path if not query_string else f"{path}?{query_string}"
            parts = build_problem_response(
                error,
                media_type=media_type,
                instance=instance,
                expose_traceback=self.expose_traceback,
            )

        parts.headers.update(
            {
                name: value
                for name, value in extra_headers.items()
                if name not in parts.headers
            }
        )
        if extra_headers.get("Access-Control-Allow-Origin", "*") != "*":
            append_vary(parts.headers, "Origin")

        await self._send(send, parts, head=method == "HEAD")

    async def _lifespan(self, receive: Callable, send: Callable) -> None:
        """
        Answer the ASGI lifespan protocol so that servers can start and stop.

        Args:
            receive: ASGI receive callable
            send: ASGI send callable
        """
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    def _cors_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """
        Build the CORS response headers for a request.

        Args:
            headers: Request headers, lower-cased names

        Returns:
            Response headers ({} when CORS is disabled or the origin is refused)
        """
        if not self.cors:
            return {}
        return cors_headers(self.cors, headers.get("origin"))

    async def _read_body(self, receive: Callable) -> bytes:
        """
        Read the whole request body, refusing oversized payloads early.

        Args:
            receive: ASGI receive callable

        Returns:
            Raw request body

        Raises:
            LinoHttpError: 413 when the body exceeds the configured limit
        """
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            if size > self.max_body_bytes:
                raise LinoHttpError(
                    413,
                    f"Request body exceeds {self.max_body_bytes} bytes",
                    headers={"Connection": "close"},
                )
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    async def _send(
        self, send: Callable, parts: ResponseParts, *, head: bool = False
    ) -> None:
        """
        Write a response to the wire.

        Args:
            send: ASGI send callable
            parts: Response to write
            head: Drop the body, as ``HEAD`` requires
        """
        body = parts.body.encode("utf-8")
        headers = [
            (name.encode("latin-1"), value.encode("latin-1"))
            for name, value in parts.headers.items()
        ]
        if parts.status not in (204, 304):
            headers.append((b"content-length", str(len(body)).encode("latin-1")))

        await send(
            {
                "type": "http.response.start",
                "status": parts.status,
                "headers": headers,
            }
        )
        await send(
            {"type": "http.response.body", "body": b"" if head else body}
        )


def create_lino_app(**options: Any) -> LinoApp:
    """
    Create a new application.

    Args:
        **options: Application options, see :class:`LinoApp`

    Returns:
        New application
    """
    return LinoApp(**options)
