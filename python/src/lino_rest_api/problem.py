"""
RFC 9457 problem details, expressed in Links Notation (specification section 5).
"""

import re
from typing import Any

#: Base URI every registered problem type is resolved against.
PROBLEM_TYPE_BASE = "https://link-foundation.github.io/lino-rest-api/errors/"

REASON_PHRASES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    409: "Conflict",
    410: "Gone",
    412: "Precondition Failed",
    413: "Content Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Content",
    428: "Precondition Required",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def reason_phrase(status: int) -> str:
    """
    Reason phrase of a status code, falling back to a generic class phrase.

    Args:
        status: HTTP status code

    Returns:
        Human readable reason phrase
    """
    if status in REASON_PHRASES:
        return REASON_PHRASES[status]
    return "Server Error" if status >= 500 else "Request Error"


def problem_slug(title: str) -> str:
    """
    Kebab-case slug used as the last segment of a problem type URI.

    Args:
        title: Problem title

    Returns:
        Slug
    """
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", title.lower()))


class LinoHttpError(Exception):
    """
    An HTTP error that carries problem details.

    Raising one of these from a handler produces a conforming error response; the
    client library raises the same shape when a server answers with 4xx or 5xx.
    """

    def __init__(
        self,
        status: int,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_uri: str | None = None,
        instance: str | None = None,
        headers: dict[str, str] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            status: HTTP status code
            detail: Human readable explanation of this occurrence
            title: Short, type-wide summary
            type_uri: Problem type URI
            instance: URI of this occurrence
            headers: Response headers to send with the error
            extensions: Extra problem members
        """
        resolved_title = title if title is not None else reason_phrase(status)
        super().__init__(detail if detail is not None else resolved_title)

        self.status = status
        self.title = resolved_title
        self.detail = detail
        self.type = (
            type_uri
            if type_uri is not None
            else f"{PROBLEM_TYPE_BASE}{problem_slug(resolved_title)}"
        )
        self.instance = instance
        self.headers = dict(headers or {})
        self.extensions = dict(extensions or {})

    @property
    def message(self) -> str:
        """Human readable message, the detail when present and the title otherwise."""
        return str(self)

    def to_problem(self, instance: str | None = None) -> dict[str, Any]:
        """
        Render the error as the problem details object of the specification.

        Args:
            instance: URI of this occurrence when not already set

        Returns:
            Problem details ready to be encoded
        """
        problem: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
        }
        if self.detail is not None:
            problem["detail"] = self.detail
        resolved_instance = self.instance if self.instance else instance
        if resolved_instance:
            problem["instance"] = resolved_instance
        problem.update(self.extensions)
        return problem


def problem_details(
    status: int,
    detail: str | None = None,
    **options: Any,
) -> dict[str, Any]:
    """
    Build problem details for a status code without raising.

    Args:
        status: HTTP status code
        detail: Human readable explanation
        **options: Additional problem members, see :class:`LinoHttpError`

    Returns:
        Problem details ready to be encoded
    """
    return LinoHttpError(status, detail, **options).to_problem(
        options.get("instance")
    )


def validation_error(
    errors: list[dict[str, str]],
    detail: str = "Request body failed validation",
) -> LinoHttpError:
    """
    A 422 carrying field-level validation failures.

    Args:
        errors: Field failures, each with a ``field`` and a ``message``
        detail: Human readable explanation

    Returns:
        Error ready to be raised
    """
    return LinoHttpError(
        422,
        detail,
        title="Unprocessable Content",
        type_uri=f"{PROBLEM_TYPE_BASE}validation-failed",
        extensions={"errors": errors},
    )


def to_http_error(error: BaseException) -> LinoHttpError:
    """
    Turn any raised exception into a :class:`LinoHttpError`.

    Errors that are already problem-shaped keep their status and details; anything
    else becomes a 500 whose detail is the original message.

    Args:
        error: Raised exception

    Returns:
        Normalised error
    """
    if isinstance(error, LinoHttpError):
        return error

    status = getattr(error, "status_code", getattr(error, "status", None))
    if isinstance(status, int) and status >= 400:
        detail = getattr(error, "detail", None) or str(error)
        return LinoHttpError(
            status,
            detail,
            headers=getattr(error, "headers", None),
        )
    return LinoHttpError(500, str(error) or type(error).__name__)
