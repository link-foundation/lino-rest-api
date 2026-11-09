"""
FastAPI adapter for Links Notation.

Provides request body parsing and response formatting for FastAPI and Starlette
applications that want Links Notation instead of JSON without adopting
:class:`lino_rest_api.app.LinoApp`. Importing these names from
``lino_rest_api.middleware`` keeps working.
"""

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute

from .codec import encode_for
from .media_type import LINO_CONTENT_TYPE, is_decodable_media_type, parse_content_type
from .middleware import (
    DEFAULT_MAX_BODY_BYTES,
    build_problem_response,
    decode_request_body,
    negotiate_request,
)
from .problem import LinoHttpError


class LinoRequest:
    """
    Wrapper for parsing LINO-formatted request bodies.
    """

    def __init__(self, request: Request, *, max_bytes: int = DEFAULT_MAX_BODY_BYTES,
                 supported: list[str] | None = None):
        """
        Initialize LinoRequest with a FastAPI request.

        Args:
            request: The FastAPI request object
        """
        self.request = request
        self.max_bytes = max_bytes
        self.supported = supported
        self._body: Any | None = None
        self._parsed = False

    async def body(self) -> Any:
        """
        Parse and return the request body as a Python object.

        Returns:
            Decoded Python object from LINO body
        """
        if self._parsed:
            return self._body

        content_type = self.request.headers.get("content-type", "")

        if is_decodable_media_type(parse_content_type(content_type)):
            chunks = bytearray()
            async for chunk in self.request.stream():
                chunks.extend(chunk)
                if len(chunks) > self.max_bytes:
                    raise LinoHttpError(413, "Request body too large")
            self._body, _ = decode_request_body(
                bytes(chunks), content_type, max_bytes=self.max_bytes, supported=self.supported
            )
        else:
            # Fall back to treating as plain text
            raw_body = await self.request.body()
            self._body = raw_body.decode("utf-8") if raw_body else None

        self._parsed = True
        return self._body


class LinoResponse(PlainTextResponse):
    """
    Response class for LINO-formatted responses.
    """

    media_type = LINO_CONTENT_TYPE

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict | None = None,
        **kwargs,
    ):
        """
        Create a LINO-formatted response.

        Args:
            content: Python object to encode as LINO
            status_code: HTTP status code
            headers: Optional response headers
            **kwargs: Additional arguments for PlainTextResponse
        """
        # Encode the content as LINO
        media_type = kwargs.pop("media_type", self.media_type)
        encoded_content = encode_for(content, media_type)

        super().__init__(
            content=encoded_content,
            media_type=media_type,
            status_code=status_code,
            headers=headers,
            **kwargs,
        )


async def lino_request_handler(request: Request) -> Any:
    """
    Parse a LINO-formatted request body.

    This is a dependency function for FastAPI endpoints.

    Args:
        request: The FastAPI request

    Returns:
        Decoded Python object from the request body
    """
    lino_request = LinoRequest(request)
    return await lino_request.body()


class LinoAPIRoute(APIRoute):
    """
    Custom APIRoute that automatically uses LINO for responses.
    """

    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def lino_handler(request: Request) -> LinoResponse:
            response = await original_handler(request)

            # If it's already a LinoResponse, return as-is
            if isinstance(response, LinoResponse):
                return response

            # If it's a regular Response, check if we should convert
            if hasattr(response, "body"):
                # Already has body, return as-is
                return response

            # Convert to LinoResponse
            return LinoResponse(content=response)

        return lino_handler


def _request_endpoint(func: Callable, wrapper: Callable) -> Callable:
    # Keep the user's endpoint metadata, but let FastAPI inject the wrapper's
    # Request rather than interpreting the user's `body` as a query parameter.
    request_signature = inspect.signature(wrapper)
    wraps(func)(wrapper)
    wrapper.__signature__ = request_signature
    return wrapper


class LinoAPI:
    """
    LinoAPI class - wraps FastAPI with LINO support.

    Automatically encodes responses as LINO and provides
    helpers for parsing LINO request bodies.
    """

    def __init__(
        self,
        title: str = "LINO REST API",
        description: str = "REST API using Links Notation",
        version: str = "0.1.0",
        supported: list[str] | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        **kwargs,
    ):
        """
        Create a new LinoAPI instance.

        Args:
            title: API title
            description: API description
            version: API version
            **kwargs: Additional FastAPI arguments
        """
        self.supported = supported
        self.max_body_bytes = max_body_bytes
        self.app = FastAPI(
            title=title,
            description=description,
            version=version,
            **kwargs,
        )

    def get(self, path: str, **kwargs):
        """
        Decorator for GET endpoints.

        Args:
            path: Route path
            **kwargs: Additional route arguments
        """

        def decorator(func: Callable) -> Callable:
            async def wrapper(request: Request) -> LinoResponse:
                return await self._dispatch(func, request)

            self.app.get(path, **kwargs)(_request_endpoint(func, wrapper))
            return func

        return decorator

    def post(self, path: str, **kwargs):
        """
        Decorator for POST endpoints.

        Args:
            path: Route path
            **kwargs: Additional route arguments
        """

        def decorator(func: Callable) -> Callable:
            async def wrapper(request: Request) -> LinoResponse:
                return await self._dispatch(func, request)

            self.app.post(path, **kwargs)(_request_endpoint(func, wrapper))
            return func

        return decorator

    def put(self, path: str, **kwargs):
        """
        Decorator for PUT endpoints.

        Args:
            path: Route path
            **kwargs: Additional route arguments
        """

        def decorator(func: Callable) -> Callable:
            async def wrapper(request: Request) -> LinoResponse:
                return await self._dispatch(func, request)

            self.app.put(path, **kwargs)(_request_endpoint(func, wrapper))
            return func

        return decorator

    def delete(self, path: str, **kwargs):
        """
        Decorator for DELETE endpoints.

        Args:
            path: Route path
            **kwargs: Additional route arguments
        """

        def decorator(func: Callable) -> Callable:
            async def wrapper(request: Request) -> LinoResponse:
                return await self._dispatch(func, request)

            self.app.delete(path, **kwargs)(_request_endpoint(func, wrapper))
            return func

        return decorator

    def patch(self, path: str, **kwargs):
        """
        Decorator for PATCH endpoints.

        Args:
            path: Route path
            **kwargs: Additional route arguments
        """

        def decorator(func: Callable) -> Callable:
            async def wrapper(request: Request) -> LinoResponse:
                return await self._dispatch(func, request)

            self.app.patch(path, **kwargs)(_request_endpoint(func, wrapper))
            return func

        return decorator

    async def _dispatch(self, func: Callable, request: Request):
        """Negotiate and render decorated routes, including binary problems."""
        media_type = LINO_CONTENT_TYPE
        try:
            media_type = negotiate_request(request.headers, self.supported)
            result = await self._call_handler(func, request)
            return LinoResponse(result, media_type=media_type, headers={"Vary": "Accept"})
        except LinoHttpError as error:
            parts = build_problem_response(error, media_type=media_type, instance=request.url.path)
            return PlainTextResponse(parts.body, status_code=parts.status, headers=parts.headers)

    async def _call_handler(self, func: Callable, request: Request) -> Any:
        """
        Call a handler function with appropriate arguments.

        Args:
            func: The handler function
            request: The FastAPI request

        Returns:
            Handler result
        """
        sig = inspect.signature(func)
        params = sig.parameters

        kwargs = {}

        for name, _param in params.items():
            if name == "request":
                kwargs["request"] = request
            elif name == "body":
                kwargs["body"] = await LinoRequest(
                    request, max_bytes=self.max_body_bytes, supported=self.supported
                ).body()

        # Check if the function is a coroutine
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)

    def get_fastapi_app(self) -> FastAPI:
        """
        Get the underlying FastAPI app.

        Returns:
            FastAPI application instance
        """
        return self.app
