"""
FastAPI middleware for Links Notation (LINO) format.

Provides request body parsing and response formatting using LINO
instead of JSON.
"""

from typing import Any

from fastapi import Request
from fastapi.responses import PlainTextResponse

from .vendor import decode, encode

# Content type for Links Notation format
LINO_CONTENT_TYPE = "text/lino"


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
