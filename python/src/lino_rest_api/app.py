"""
LinoAPI - FastAPI application wrapper with LINO support.

Provides a convenient way to create FastAPI applications that
communicate using Links Notation format by default.
"""

from functools import wraps
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute

from .middleware import LinoResponse, lino_request_handler


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
