"""
Collection query parsing (specification sections 6.2 - 6.4).

Turns the reserved query parameters (``limit``, ``offset``, ``sort``, ``fields``)
and the free-form field filters of a request URL into a structured query.
"""

from dataclasses import dataclass, field
from typing import Any

from .problem import LinoHttpError

#: Query parameters that are not field filters.
RESERVED_QUERY_PARAMETERS = ("limit", "offset", "sort", "fields")

#: Page size used when a request does not ask for one.
DEFAULT_LIMIT = 20

#: Largest page a server will serve, whatever the request asks for.
MAX_LIMIT = 100


@dataclass(frozen=True)
class SortKey:
    """One ordering key of a collection query."""

    field: str
    descending: bool


@dataclass
class CollectionQuery:
    """A parsed collection query."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0
    sort: list[SortKey] = field(default_factory=list)
    fields: list[str] | None = None
    filters: dict[str, Any] = field(default_factory=dict)


def parse_scalar(raw: str) -> Any:
    """
    Parse a filter value with the Links Notation scalar rules.

    ``?done=true`` filters on the boolean, ``?id=7`` on the integer, and anything
    else stays a string.

    Args:
        raw: Raw query parameter value

    Returns:
        Parsed scalar
    """
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw == "null":
        return None
    if raw == "":
        return raw
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_bounded_integer(
    raw: str | None,
    fallback: int,
    name: str,
    maximum: int | None = None,
) -> int:
    """
    Parse a bounded non-negative integer query parameter.

    Args:
        raw: Raw query parameter value
        fallback: Value used when the parameter is absent
        name: Parameter name, used in the error detail
        maximum: Largest accepted value

    Returns:
        Parsed value

    Raises:
        LinoHttpError: 400 when the value is not a non-negative integer
    """
    if raw is None or raw == "":
        return fallback
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise LinoHttpError(
            400,
            f'Query parameter "{name}" must be a non-negative integer',
        ) from error
    if value < 0:
        raise LinoHttpError(
            400,
            f'Query parameter "{name}" must be a non-negative integer',
        )
    return value if maximum is None else min(value, maximum)


def parse_sort(raw: str | None) -> list[SortKey]:
    """
    Parse a ``sort`` parameter into ordered sort keys.

    Args:
        raw: Raw ``sort`` value

    Returns:
        Sort keys
    """
    if not raw:
        return []
    keys = []
    for part in (entry.strip() for entry in raw.split(",")):
        if not part:
            continue
        if part.startswith("-"):
            keys.append(SortKey(part[1:], True))
        else:
            keys.append(SortKey(part, False))
    return keys


def parse_fields(raw: str | None) -> list[str] | None:
    """
    Parse a ``fields`` parameter into a sparse fieldset.

    Args:
        raw: Raw ``fields`` value

    Returns:
        Field names, or None when every field is requested
    """
    if not raw:
        return None
    fields = [part.strip() for part in raw.split(",") if part.strip()]
    return fields or None


def parse_collection_query(
    query: dict[str, Any] | None = None,
    *,
    default_limit: int = DEFAULT_LIMIT,
    max_limit: int = MAX_LIMIT,
) -> CollectionQuery:
    """
    Parse a full collection query from request query parameters.

    Repeated parameters are expected as lists, which is how a query string such
    as ``?tag=a&tag=b`` is read.

    Args:
        query: Request query parameters
        default_limit: Page size when unspecified
        max_limit: Largest accepted page size

    Returns:
        Parsed query
    """
    query = query or {}

    filters: dict[str, Any] = {}
    for name, value in query.items():
        if name in RESERVED_QUERY_PARAMETERS:
            continue
        if isinstance(value, list | tuple):
            filters[name] = [parse_scalar(entry) for entry in value]
        else:
            filters[name] = parse_scalar(value)

    def single(name: str) -> str | None:
        value = query.get(name)
        if isinstance(value, list | tuple):
            return value[-1] if value else None
        return value

    return CollectionQuery(
        limit=parse_bounded_integer(
            single("limit"), default_limit, "limit", max_limit
        ),
        offset=parse_bounded_integer(single("offset"), 0, "offset"),
        sort=parse_sort(single("sort")),
        fields=parse_fields(single("fields")),
        filters=filters,
    )
