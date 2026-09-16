"""
The request object handlers receive.

It is intentionally small: the method, the path, the decoded body, the negotiated
representation and the parsed query. Everything else stays reachable through the
raw ASGI ``scope``.
"""

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote

from .query import CollectionQuery, parse_collection_query


@dataclass
class LinoHttpRequest:
    """One HTTP request, decoded according to the specification."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    query_string: str = ""
    body: Any = None
    media_type: str = ""
    request_media_type: str | None = None
    scope: dict[str, Any] = field(default_factory=dict)
    app: Any = None

    @property
    def query(self) -> dict[str, Any]:
        """
        Query parameters, with repeated parameters collected into lists.

        Returns:
            Parsed query parameters
        """
        parsed = parse_qs(self.query_string, keep_blank_values=True)
        return {
            name: values[0] if len(values) == 1 else values
            for name, values in parsed.items()
        }

    def header(self, name: str) -> str | None:
        """
        Read a request header.

        Args:
            name: Header name, case insensitive

        Returns:
            Header value, or None when absent
        """
        return self.headers.get(name.lower())

    def param(self, name: str) -> str | None:
        """
        Read a path parameter, percent-decoded.

        Args:
            name: Parameter name

        Returns:
            Parameter value, or None when the route does not declare it
        """
        value = self.params.get(name)
        return None if value is None else unquote(value)

    def collection_query(self, **options: Any) -> CollectionQuery:
        """
        Parse the query string as a collection query (specification section 6).

        Args:
            **options: Overrides for ``default_limit`` and ``max_limit``

        Returns:
            Parsed collection query
        """
        defaults = getattr(self.app, "query_defaults", {})
        return parse_collection_query(self.query, **{**defaults, **options})
