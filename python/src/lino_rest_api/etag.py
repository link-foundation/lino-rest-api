"""
Entity tags and conditional requests (specification section 7).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from .problem import LinoHttpError


@dataclass(frozen=True)
class PreconditionResult:
    """Outcome of evaluating the conditional headers of a request."""

    not_modified: bool


def compute_etag(body: str) -> str:
    """
    Compute the strong entity tag of an encoded representation.

    Args:
        body: Encoded representation

    Returns:
        Quoted hexadecimal SHA-256
    """
    digest = sha256(body.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def parse_etag_list(header_value: str | None) -> list[str]:
    """
    Split an ``If-Match`` or ``If-None-Match`` header into entity tags.

    Args:
        header_value: Raw header value

    Returns:
        Entity tags, with any weak prefix removed
    """
    if not header_value:
        return []
    tags = []
    for tag in header_value.split(","):
        cleaned = re.sub(r"^W/", "", tag.strip())
        if cleaned:
            tags.append(cleaned)
    return tags


def etag_matches(header_value: str | None, current_etag: str) -> bool:
    """
    Test whether an entity tag list matches the current tag.

    Args:
        header_value: Raw ``If-Match`` or ``If-None-Match`` value
        current_etag: Entity tag of the current representation

    Returns:
        True when the list matches
    """
    tags = parse_etag_list(header_value)
    return "*" in tags or current_etag in tags


def evaluate_preconditions(
    headers: Mapping[str, str],
    method: str,
    current_etag: str,
    *,
    require_precondition: bool = False,
) -> PreconditionResult:
    """
    Evaluate the conditional request headers of a request.

    Args:
        headers: Request headers, lower-cased names
        method: HTTP method
        current_etag: Entity tag of the current representation
        require_precondition: Demand ``If-Match`` on unsafe methods

    Returns:
        Whether the response should be 304

    Raises:
        LinoHttpError: 412 on a failed ``If-Match``, 428 when one is required
    """
    safe = method in ("GET", "HEAD")
    if_match = headers.get("if-match")
    if_none_match = headers.get("if-none-match")

    if not safe:
        if if_match is not None:
            if not etag_matches(if_match, current_etag):
                raise LinoHttpError(
                    412,
                    "The entity tag in If-Match does not match the current representation",
                )
        elif require_precondition:
            raise LinoHttpError(
                428,
                "This request requires an If-Match precondition",
            )

    if if_none_match is not None and etag_matches(if_none_match, current_etag):
        if safe:
            return PreconditionResult(True)
        raise LinoHttpError(
            412,
            "The entity tag in If-None-Match matches the current representation",
        )

    return PreconditionResult(False)
