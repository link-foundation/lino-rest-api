"""
Collection envelope, in-memory query execution and RFC 8288 link headers
(specification section 6).
"""

from typing import Any
from urllib.parse import urlencode

from .query import CollectionQuery, SortKey


def matches_filters(item: Any, filters: dict[str, Any]) -> bool:
    """
    Test whether an item satisfies every filter.

    A filter whose value is a list matches when the item field equals any member,
    which is what repeated query parameters (``?tag=a&tag=b``) mean.

    Args:
        item: Candidate item
        filters: Field filters

    Returns:
        True when the item matches
    """
    for field_name, expected in filters.items():
        actual = item.get(field_name) if isinstance(item, dict) else None
        if isinstance(expected, list | tuple):
            if not any(candidate == actual for candidate in expected):
                return False
        elif actual != expected:
            return False
    return True


def _sort_key(value: Any) -> tuple[int, float, str]:
    """
    Build a sort key placing absent values first and ordering the rest totally.

    Numbers sort numerically among themselves; everything else sorts as text, so
    that values of mixed Links Notation types still have a stable order.

    Args:
        value: Value of the field being sorted on

    Returns:
        Tuple usable as a ``sorted`` key
    """
    if value is None:
        return (0, 0.0, "")
    if isinstance(value, bool):
        return (2, 0.0, str(value))
    if isinstance(value, int | float):
        return (1, float(value), "")
    return (2, 0.0, str(value))


def sort_items(items: list[Any], sort: list[SortKey] | None) -> list[Any]:
    """
    Sort items by the sort keys of a collection query.

    Args:
        items: Items to sort (not mutated)
        sort: Sort keys

    Returns:
        Sorted copy
    """
    sorted_items = list(items)
    if not sort:
        return sorted_items
    # Python's sort is stable, so applying the keys from least to most
    # significant yields the same order as a multi-key comparison.
    for key in reversed(sort):
        sorted_items.sort(
            key=lambda item, key=key: _sort_key(
                item.get(key.field) if isinstance(item, dict) else None
            ),
            reverse=key.descending,
        )
    return sorted_items


def project_fields(item: Any, fields: list[str] | None) -> Any:
    """
    Reduce an item to a sparse fieldset.

    Args:
        item: Item to project
        fields: Field names, or None for every field

    Returns:
        Projected item
    """
    if not fields:
        return item
    if not isinstance(item, dict):
        return item
    return {name: item[name] for name in fields if name in item}


def collection_envelope(
    items: list[Any],
    *,
    limit: int,
    offset: int,
    total: int,
) -> dict[str, Any]:
    """
    Wrap items in the collection envelope of the specification.

    Args:
        items: Items of this page
        limit: Page size
        offset: Index of the first item of this page
        total: Number of items matching the query

    Returns:
        Collection envelope
    """
    return {
        "items": items,
        "page": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "count": len(items),
        },
    }


def apply_collection_query(
    items: list[Any],
    query: CollectionQuery,
) -> dict[str, Any]:
    """
    Run a parsed collection query against an in-memory list.

    Args:
        items: Every item of the collection
        query: Query from :func:`lino_rest_api.query.parse_collection_query`

    Returns:
        Collection envelope
    """
    filtered = [item for item in items if matches_filters(item, query.filters)]
    ordered = sort_items(filtered, query.sort)
    page = ordered[query.offset : query.offset + query.limit]
    projected = [project_fields(item, query.fields) for item in page]

    return collection_envelope(
        projected,
        limit=query.limit,
        offset=query.offset,
        total=len(filtered),
    )


def pagination_link_header(
    path: str,
    query: dict[str, Any] | None,
    *,
    limit: int,
    offset: int,
    total: int,
) -> str:
    """
    Build the RFC 8288 ``Link`` header value for a paginated collection.

    Args:
        path: Request path without a query string
        query: Original query parameters
        limit: Page size
        offset: Index of the first item of this page
        total: Number of items matching the query

    Returns:
        ``Link`` header value ("" when there is nothing to link to)
    """
    if not limit:
        return ""

    def build(target_offset: int) -> str:
        parameters: list[tuple[str, str]] = []
        for name, value in (query or {}).items():
            if name in ("limit", "offset"):
                continue
            values = value if isinstance(value, list | tuple) else [value]
            parameters.extend((name, str(entry)) for entry in values)
        parameters.append(("limit", str(limit)))
        parameters.append(("offset", str(target_offset)))
        return f"{path}?{urlencode(parameters)}"

    last_offset = 0 if total == 0 else ((total - 1) // limit) * limit
    links = [f'<{build(0)}>; rel="first"']
    if offset > 0:
        links.append(f'<{build(max(0, offset - limit))}>; rel="prev"')
    if offset + limit < total:
        links.append(f'<{build(offset + limit)}>; rel="next"')
    links.append(f'<{build(last_offset)}>; rel="last"')

    return ", ".join(links)
