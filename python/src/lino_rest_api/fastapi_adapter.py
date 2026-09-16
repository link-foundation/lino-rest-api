"""
FastAPI adapter for Links Notation.

Provides request body parsing and response formatting for FastAPI and Starlette
applications that want Links Notation instead of JSON without adopting
:class:`lino_rest_api.app.LinoApp`. Importing these names from
``lino_rest_api.middleware`` keeps working.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRoute

from .codec import decode, encode
from .media_type import LINO_CONTENT_TYPE


class LinoRequest:
    """
    Wrapper for parsing LINO-formatted request bodies.
    """

    def __init__(self, request: Request):
        """
        Initialize LinoRequest with a FastAPI request.

        Args:
            request: The FastAPI request object
        """
        self.request = request
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

        if LINO_CONTENT_TYPE in content_type:
            raw_body = await self.request.body()
            body_str = raw_body.decode("utf-8")

            if body_str.strip():
                self._body = decode(body_str)
            else:
                self._body = None
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
        encoded_content = encode(content) if content is not None else encode(None)

        super().__init__(
            content=encoded_content,
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
            @wraps(func)
            async def wrapper(request: Request) -> LinoResponse:
                result = await self._call_handler(func, request)
                return LinoResponse(content=result)

            self.app.get(path, **kwargs)(wrapper)
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
            @wraps(func)
            async def wrapper(request: Request) -> LinoResponse:
                result = await self._call_handler(func, request)
                return LinoResponse(content=result)

            self.app.post(path, **kwargs)(wrapper)
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
            @wraps(func)
            async def wrapper(request: Request) -> LinoResponse:
                result = await self._call_handler(func, request)
                return LinoResponse(content=result)

            self.app.put(path, **kwargs)(wrapper)
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
            @wraps(func)
            async def wrapper(request: Request) -> LinoResponse:
                result = await self._call_handler(func, request)
                return LinoResponse(content=result)

            self.app.delete(path, **kwargs)(wrapper)
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
            @wraps(func)
            async def wrapper(request: Request) -> LinoResponse:
                result = await self._call_handler(func, request)
                return LinoResponse(content=result)

            self.app.patch(path, **kwargs)(wrapper)
            return func

        return decorator

    async def _call_handler(self, func: Callable, request: Request) -> Any:
        """
        Call a handler function with appropriate arguments.

        Args:
            func: The handler function
            request: The FastAPI request

        Returns:
            Handler result
        """
        import inspect

        sig = inspect.signature(func)
        params = sig.parameters

        kwargs = {}

        for name, _param in params.items():
            if name == "request":
                kwargs["request"] = request
            elif name == "body":
                kwargs["body"] = await lino_request_handler(request)

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
