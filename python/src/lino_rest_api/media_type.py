"""
Media types and content negotiation (specification section 2).

Negotiation follows RFC 9110 section 12.5.1: the ``Accept`` header is parsed into
ranges with quality values. Each representation takes the quality of its most
specific matching range; highest positive quality wins, then server preference.
"""

from dataclasses import dataclass

#: Readable, indented Links Notation. The default representation.
LINO_CONTENT_TYPE = "text/lino"

#: Readable Links Notation restricted to one line per value.
LINO_LINE_CONTENT_TYPE = "text/lino-line"

#: Type-tagged, base64 Links Notation that preserves object identity.
LINO_COMPACT_CONTENT_TYPE = "text/lino-compact"

#: Binary Links Notation carrying the typed compact object AST.
LINO_BINARY_CONTENT_TYPE = "application/lino-binary"

#: JSON fallback for clients that cannot speak Links Notation.
JSON_CONTENT_TYPE = "application/json"

#: Problem details served as Links Notation.
LINO_PROBLEM_CONTENT_TYPE = "application/problem+lino"

#: Media type of RFC 9457 problem details expressed as JSON.
JSON_PROBLEM_CONTENT_TYPE = "application/problem+json"

#: Problem-details media type to use for each representation.
PROBLEM_MEDIA_TYPES = {
    LINO_CONTENT_TYPE: LINO_PROBLEM_CONTENT_TYPE,
    JSON_CONTENT_TYPE: JSON_PROBLEM_CONTENT_TYPE,
}

#: Representation each problem-details media type is encoded as.
_PROBLEM_BASE_MEDIA_TYPES = {
    LINO_PROBLEM_CONTENT_TYPE: LINO_CONTENT_TYPE,
    JSON_PROBLEM_CONTENT_TYPE: JSON_CONTENT_TYPE,
}

#: Every representation a server produces, most preferred first.
SUPPORTED_MEDIA_TYPES = [
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    LINO_BINARY_CONTENT_TYPE,
]


@dataclass(frozen=True)
class AcceptRange:
    """One range of an ``Accept`` header."""

    type: str
    quality: float
    specificity: int


def with_charset(media_type: str) -> str:
    """
    Add ``charset=utf-8`` to a media type so that bytes are unambiguous.

    Args:
        media_type: Bare media type

    Returns:
        Media type with an explicit charset
    """
    return media_type if media_type == LINO_BINARY_CONTENT_TYPE else f"{media_type}; charset=utf-8"


def parse_content_type(header_value: str | None) -> str:
    """
    Strip parameters and normalise case, turning a header value into a media type.

    Args:
        header_value: Raw ``Content-Type`` header value

    Returns:
        Bare, lower-cased media type ("" when absent)
    """
    if not header_value:
        return ""
    return header_value.split(";")[0].strip().lower()


def parse_accept(header_value: str | None) -> list[AcceptRange]:
    """
    Parse an ``Accept`` header into ranges ordered by preference.

    Args:
        header_value: Raw ``Accept`` header value

    Returns:
        Ranges, most preferred first
    """
    if not header_value or not header_value.strip():
        return [AcceptRange("*/*", 1.0, 0)]

    ranges: list[tuple[int, AcceptRange]] = []
    for index, part in enumerate(header_value.split(",")):
        raw_type, *parameters = part.split(";")
        media_type = raw_type.strip().lower()
        if not media_type:
            continue

        quality = 1.0
        for parameter in parameters:
            name, _, value = parameter.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0

        if media_type == "*/*":
            specificity = 0
        elif media_type.endswith("/*"):
            specificity = 1
        else:
            specificity = 2

        ranges.append((index, AcceptRange(media_type, quality, specificity)))

    ranges.sort(key=lambda entry: (-entry[1].quality, -entry[1].specificity, entry[0]))
    return [entry[1] for entry in ranges]


def _range_matches(range_type: str, media_type: str) -> bool:
    """
    Test whether an ``Accept`` range matches a concrete media type.

    Args:
        range_type: Range from an ``Accept`` header
        media_type: Concrete media type

    Returns:
        True when the range covers the media type
    """
    if range_type in ("*/*", media_type):
        return True
    if range_type.endswith("/*"):
        return media_type.startswith(range_type[:-1])
    return False


def negotiate_media_type(
    accept_header: str | None,
    supported: list[str] | None = None,
) -> str | None:
    """
    Select the representation to produce for a request.

    Args:
        accept_header: Raw ``Accept`` header value
        supported: Representations the server can produce

    Returns:
        Selected media type, or None when none is acceptable
    """
    candidates = SUPPORTED_MEDIA_TYPES if supported is None else supported
    ranges = parse_accept(accept_header)
    selected = None
    best_quality = 0.0
    for media_type in candidates:
        matches = [r for r in ranges if _range_matches(r.type, media_type)]
        effective = max(matches, key=lambda r: r.specificity, default=None)
        if effective is not None and effective.quality > best_quality:
            selected = media_type
            best_quality = effective.quality
    return selected


def normalize_media_type(media_type: str) -> str:
    """
    Resolve a media type to the representation it is encoded as.

    Problem-details types carry the same syntax as their base representation, so
    they decode with the same codec.

    Args:
        media_type: Bare media type

    Returns:
        Representation media type
    """
    return _PROBLEM_BASE_MEDIA_TYPES.get(media_type, media_type)


def is_decodable_media_type(media_type: str) -> bool:
    """
    Test whether a request body media type can be decoded.

    Args:
        media_type: Bare media type of the request body

    Returns:
        True when the body can be decoded
    """
    return normalize_media_type(media_type) in SUPPORTED_MEDIA_TYPES


def problem_media_type(media_type: str) -> str:
    """
    Problem-details media type matching a representation.

    Args:
        media_type: Representation media type

    Returns:
        Media type to announce for problem details
    """
    return PROBLEM_MEDIA_TYPES.get(media_type, media_type)
