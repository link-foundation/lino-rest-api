"""
Links Notation REST client (specification section 10).

Built on ``httpx``, so the same code covers synchronous and asynchronous callers
and can talk to an in-process ASGI application in tests.
"""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from .codec import decode_from, encode_for
from .media_type import (
    JSON_CONTENT_TYPE,
    LINO_CONTENT_TYPE,
    is_decodable_media_type,
    parse_content_type,
    with_charset,
)

#: Default ``Accept`` sent by the client: Links Notation first, JSON as a fallback.
DEFAULT_ACCEPT = f"{LINO_CONTENT_TYPE}, {JSON_CONTENT_TYPE};q=0.5"

#: Path of the native service description (specification section 9).
DESCRIPTION_PATH = "/.well-known/lino-api"


class LinoClientError(Exception):
    """Error raised for any 4xx or 5xx, carrying the decoded problem details."""

    def __init__(
        self,
        status: int,
        problem: Any = None,
        response: httpx.Response | None = None,
    ) -> None:
        """
        Args:
            status: HTTP status code
            problem: Decoded problem details, when the body could be decoded
            response: The response that produced this error
        """
        detail = None
        if isinstance(problem, dict):
            detail = problem.get("detail") or problem.get("title")
        super().__init__(detail or f"Request failed with status {status}")
        self.status = status
        self.problem = problem
        self.response = response


@dataclass
class LinoResponse:
    """A decoded response."""

    status: int
    headers: httpx.Headers = field(default_factory=httpx.Headers)
    data: Any = None
    etag: str | None = None
    location: str | None = None
    response: httpx.Response | None = None


def query_value(value: Any) -> str:
    """
    Spell one query parameter value the way section 6.1 filters read it.

    ``str(False)`` is ``"False"``, which no filter matches; booleans travel as
    ``true`` and ``false``, exactly as they do from the JavaScript client.

    Args:
        value: Value of a query parameter

    Returns:
        Wire spelling of the value
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_query_string(query: dict[str, Any] | None) -> str:
    """
    Build a query string from a mapping, expanding list values.

    Args:
        query: Query parameters

    Returns:
        Query string including ``?``, or an empty string
    """
    if not query:
        return ""
    parameters: list[tuple[str, str]] = []
    for name, value in query.items():
        if value is None:
            continue
        values = value if isinstance(value, list | tuple) else [value]
        parameters.extend((name, query_value(entry)) for entry in values)
    encoded = urlencode(parameters)
    return f"?{encoded}" if encoded else ""


class _RequestBuilder:
    """Everything a client needs to turn a call into an HTTP request."""

    def __init__(
        self,
        base_url: str,
        *,
        accept: str = DEFAULT_ACCEPT,
        content_type: str = LINO_CONTENT_TYPE,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Args:
            base_url: Base URL of the service
            accept: ``Accept`` header sent with every request
            content_type: Representation used for request bodies
            headers: Headers sent with every request
        """
        self.base_url = str(base_url).rstrip("/")
        self.accept = accept
        self.content_type = content_type
        self.headers = dict(headers or {})

    def prepare(
        self,
        path: str,
        *,
        body: Any = None,
        send_body: bool = False,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        accept: str | None = None,
        if_match: str | None = None,
        if_none_match: str | None = None,
    ) -> tuple[str, dict[str, str], str | None]:
        """
        Build the URL, headers and encoded body of a request.

        Args:
            path: Path, appended to the base URL
            body: Value to encode as the request body
            send_body: Whether the body should be sent at all
            query: Query parameters
            headers: Extra request headers
            accept: Override the ``Accept`` header
            if_match: ``If-Match`` precondition
            if_none_match: ``If-None-Match`` precondition

        Returns:
            URL, request headers and encoded body
        """
        url = f"{self.base_url}{path}{build_query_string(query)}"
        request_headers = {
            "Accept": accept or self.accept,
            **self.headers,
            **(headers or {}),
        }
        if if_match:
            request_headers["If-Match"] = if_match
        if if_none_match:
            request_headers["If-None-Match"] = if_none_match

        content = None
        if send_body:
            content = encode_for(body, self.content_type)
            request_headers["Content-Type"] = with_charset(self.content_type)

        return url, request_headers, content

    def finish(self, response: httpx.Response, method: str) -> LinoResponse:
        """
        Decode a response and raise on 4xx and 5xx.

        Args:
            response: Raw response
            method: Request method

        Returns:
            Decoded response

        Raises:
            LinoClientError: For any 4xx or 5xx response
        """
        data = decode_response(response, method)
        if response.status_code >= 400:
            raise LinoClientError(response.status_code, data, response)
        return LinoResponse(
            status=response.status_code,
            headers=response.headers,
            data=data,
            etag=response.headers.get("etag"),
            location=response.headers.get("location"),
            response=response,
        )


def decode_response(response: httpx.Response, method: str) -> Any:
    """
    Decode a response body according to its own ``Content-Type`` (section 10).

    Args:
        response: Raw response
        method: Request method

    Returns:
        Decoded value, the raw text when it is not a known representation, or
        None when there is no body
    """
    if response.status_code in (204, 304) or method == "HEAD":
        return None

    text = response.text
    if text == "":
        return None

    media_type = parse_content_type(response.headers.get("content-type"))
    if not is_decodable_media_type(media_type):
        return text
    try:
        return decode_from(text, media_type)
    except Exception:
        return text


def allowed_methods(response: LinoResponse) -> list[str]:
    """
    Read the methods advertised in an ``Allow`` header.

    Args:
        response: Response of an ``OPTIONS`` request

    Returns:
        Methods listed in ``Allow``
    """
    allow = response.headers.get("allow", "")
    return [method.strip() for method in allow.split(",") if method.strip()]


class LinoClient(_RequestBuilder):
    """A synchronous client for a service that speaks Links Notation."""

    def __init__(
        self,
        base_url: str,
        *,
        accept: str = DEFAULT_ACCEPT,
        content_type: str = LINO_CONTENT_TYPE,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        **client_options: Any,
    ) -> None:
        """
        Args:
            base_url: Base URL of the service
            accept: ``Accept`` header sent with every request
            content_type: Representation used for request bodies
            headers: Headers sent with every request
            client: ``httpx`` client to use, created when omitted
            **client_options: Options forwarded to :class:`httpx.Client`
        """
        super().__init__(
            base_url, accept=accept, content_type=content_type, headers=headers
        )
        self._client = client or httpx.Client(**client_options)
        self._owns_client = client is None

    def __enter__(self) -> "LinoClient":
        """Enter a context manager that closes the underlying client."""
        return self

    def __exit__(self, *exception: Any) -> None:
        """Close the underlying client when it was created here."""
        self.close()

    def close(self) -> None:
        """Close the underlying ``httpx`` client when this client owns it."""
        if self._owns_client:
            self._client.close()

    def request(self, method: str, path: str, **options: Any) -> LinoResponse:
        """
        Perform a request and decode the response.

        Args:
            method: HTTP method
            path: Path, appended to the base URL
            **options: Request options, see :meth:`_RequestBuilder.prepare`

        Returns:
            Decoded response

        Raises:
            LinoClientError: For any 4xx or 5xx response
        """
        url, headers, content = self.prepare(path, **options)
        response = self._client.request(
            method, url, headers=headers, content=content
        )
        return self.finish(response, method)

    def get(self, path: str, **options: Any) -> LinoResponse:
        """
        ``GET`` a resource.

        Args:
            path: Path
            **options: Request options

        Returns:
            Decoded response
        """
        return self.request("GET", path, **options)

    def post(self, path: str, body: Any = None, **options: Any) -> LinoResponse:
        """
        ``POST`` to a collection.

        Args:
            path: Path
            body: Value to send
            **options: Request options

        Returns:
            Decoded response
        """
        return self.request("POST", path, body=body, send_body=True, **options)

    def put(self, path: str, body: Any = None, **options: Any) -> LinoResponse:
        """
        ``PUT`` a representation.

        Args:
            path: Path
            body: Value to send
            **options: Request options

        Returns:
            Decoded response
        """
        return self.request("PUT", path, body=body, send_body=True, **options)

    def patch(self, path: str, body: Any = None, **options: Any) -> LinoResponse:
        """
        ``PATCH`` a representation.

        Args:
            path: Path
            body: Value to send
            **options: Request options

        Returns:
            Decoded response
        """
        return self.request("PATCH", path, body=body, send_body=True, **options)

    def delete(self, path: str, **options: Any) -> LinoResponse:
        """
        ``DELETE`` a resource.

        Args:
            path: Path
            **options: Request options

        Returns:
            Decoded response
        """
        return self.request("DELETE", path, **options)

    def head(self, path: str, **options: Any) -> LinoResponse:
        """
        ``HEAD`` a resource.

        Args:
            path: Path
            **options: Request options

        Returns:
            Decoded response
        """
        return self.request("HEAD", path, **options)

    def options(self, path: str, **options: Any) -> list[str]:
        """
        ``OPTIONS`` a path, returning the advertised methods.

        Args:
            path: Path
            **options: Request options

        Returns:
            Methods listed in ``Allow``
        """
        return allowed_methods(self.request("OPTIONS", path, **options))

    def list(
        self, path: str, query: dict[str, Any] | None = None, **options: Any
    ) -> Any:
        """
        List a collection, returning the decoded envelope.

        Args:
            path: Collection path
            query: Collection query parameters
            **options: Request options

        Returns:
            Collection envelope
        """
        return self.request("GET", path, query=query, **options).data

    def describe(self) -> Any:
        """
        Fetch the service description of specification section 9.

        Returns:
            Description document
        """
        return self.get(DESCRIPTION_PATH).data


class AsyncLinoClient(_RequestBuilder):
    """An asynchronous client for a service that speaks Links Notation."""

    def __init__(
        self,
        base_url: str,
        *,
        accept: str = DEFAULT_ACCEPT,
        content_type: str = LINO_CONTENT_TYPE,
        headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
        **client_options: Any,
    ) -> None:
        """
        Args:
            base_url: Base URL of the service
            accept: ``Accept`` header sent with every request
            content_type: Representation used for request bodies
            headers: Headers sent with every request
            client: ``httpx`` client to use, created when omitted
            **client_options: Options forwarded to :class:`httpx.AsyncClient`
        """
        super().__init__(
            base_url, accept=accept, content_type=content_type, headers=headers
        )
        self._client = client or httpx.AsyncClient(**client_options)
        self._owns_client = client is None

    async def __aenter__(self) -> "AsyncLinoClient":
        """Enter a context manager that closes the underlying client."""
        return self

    async def __aexit__(self, *exception: Any) -> None:
        """Close the underlying client when it was created here."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying ``httpx`` client when this client owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def request(self, method: str, path: str, **options: Any) -> LinoResponse:
        """
        Perform a request and decode the response.

        Args:
            method: HTTP method
            path: Path, appended to the base URL
            **options: Request options, see :meth:`_RequestBuilder.prepare`

        Returns:
            Decoded response

        Raises:
            LinoClientError: For any 4xx or 5xx response
        """
        url, headers, content = self.prepare(path, **options)
        response = await self._client.request(
            method, url, headers=headers, content=content
        )
        return self.finish(response, method)

    async def get(self, path: str, **options: Any) -> LinoResponse:
        """
        ``GET`` a resource.

        Args:
            path: Path
            **options: Request options

        Returns:
            Decoded response
        """
        return await self.request("GET", path, **options)

    async def post(
        self, path: str, body: Any = None, **options: Any
    ) -> LinoResponse:
        """
        ``POST`` to a collection.

        Args:
            path: Path
            body: Value to send
            **options: Request options

        Returns:
            Decoded response
        """
        return await self.request("POST", path, body=body, send_body=True, **options)

    async def put(self, path: str, body: Any = None, **options: Any) -> LinoResponse:
        """
        ``PUT`` a representation.

        Args:
            path: Path
            body: Value to send
            **options: Request options

        Returns:
            Decoded response
        """
        return await self.request("PUT", path, body=body, send_body=True, **options)

    async def patch(
        self, path: str, body: Any = None, **options: Any
    ) -> LinoResponse:
        """
        ``PATCH`` a representation.

        Args:
            path: Path
            body: Value to send
            **options: Request options

        Returns:
            Decoded response
        """
        return await self.request("PATCH", path, body=body, send_body=True, **options)

    async def delete(self, path: str, **options: Any) -> LinoResponse:
        """
        ``DELETE`` a resource.

        Args:
            path: Path
            **options: Request options

        Returns:
            Decoded response
        """
        return await self.request("DELETE", path, **options)

    async def head(self, path: str, **options: Any) -> LinoResponse:
        """
        ``HEAD`` a resource.

        Args:
            path: Path
            **options: Request options

        Returns:
            Decoded response
        """
        return await self.request("HEAD", path, **options)

    async def options(self, path: str, **options: Any) -> list[str]:
        """
        ``OPTIONS`` a path, returning the advertised methods.

        Args:
            path: Path
            **options: Request options

        Returns:
            Methods listed in ``Allow``
        """
        return allowed_methods(await self.request("OPTIONS", path, **options))

    async def list(
        self, path: str, query: dict[str, Any] | None = None, **options: Any
    ) -> Any:
        """
        List a collection, returning the decoded envelope.

        Args:
            path: Collection path
            query: Collection query parameters
            **options: Request options

        Returns:
            Collection envelope
        """
        return (await self.request("GET", path, query=query, **options)).data

    async def describe(self) -> Any:
        """
        Fetch the service description of specification section 9.

        Returns:
            Description document
        """
        return (await self.get(DESCRIPTION_PATH)).data


def create_lino_client(base_url: str, **options: Any) -> LinoClient:
    """
    Create a synchronous client.

    Args:
        base_url: Base URL of the service
        **options: Client options, see :class:`LinoClient`

    Returns:
        New client
    """
    return LinoClient(base_url, **options)


def create_async_lino_client(base_url: str, **options: Any) -> AsyncLinoClient:
    """
    Create an asynchronous client.

    Args:
        base_url: Base URL of the service
        **options: Client options, see :class:`AsyncLinoClient`

    Returns:
        New client
    """
    return AsyncLinoClient(base_url, **options)
