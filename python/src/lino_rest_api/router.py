"""
Route registry backing automatic ``HEAD``, automatic ``OPTIONS``, ``405 Method Not
Allowed`` and the service description (specification sections 4.1 and 9).

Path patterns use the ``:parameter`` syntax of the JavaScript implementation, so
the same route table can be described identically in both languages.
"""

import re
from dataclasses import dataclass, field
from re import Pattern
from typing import Any

#: Methods that never need to be registered explicitly.
IMPLICIT_METHODS = ("HEAD", "OPTIONS")


def compile_path_pattern(pattern: str) -> Pattern[str]:
    """
    Compile a path pattern into a matcher that also captures path parameters.

    Supports ``:parameter`` segments and a trailing ``*`` wildcard.

    Args:
        pattern: Path pattern

    Returns:
        Matcher anchored to the whole path
    """
    segments = []
    for segment in pattern.split("/"):
        if segment.startswith(":"):
            segments.append(f"(?P<{segment[1:]}>[^/]+)")
        elif segment.startswith("*"):
            segments.append(".*")
        else:
            segments.append(re.escape(segment))
    return re.compile(f"^{'/'.join(segments)}/?$")


@dataclass
class RouteEntry:
    """Every method registered on one path pattern."""

    pattern: str
    matcher: Pattern[str]
    methods: dict[str, dict[str, Any]] = field(default_factory=dict)


class RouteTable:
    """The set of routes registered on an application."""

    def __init__(self) -> None:
        self.routes: dict[str, RouteEntry] = {}

    def register(
        self,
        method: str,
        pattern: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """
        Register a method on a path.

        Args:
            method: HTTP method
            pattern: Path pattern
            meta: Description metadata for specification section 9
        """
        entry = self.routes.get(pattern)
        if entry is None:
            entry = RouteEntry(pattern, compile_path_pattern(pattern))
            self.routes[pattern] = entry
        entry.methods[method.upper()] = dict(meta or {})

    def find(self, pathname: str) -> RouteEntry | None:
        """
        Find the route entry owning a concrete path.

        Args:
            pathname: Request path

        Returns:
            Route entry, or None when unowned
        """
        match = self.match(pathname)
        return match[0] if match else None

    def match(self, pathname: str) -> tuple[RouteEntry, dict[str, str]] | None:
        """
        Find the route entry owning a path together with its path parameters.

        Args:
            pathname: Request path

        Returns:
            Entry and captured parameters, or None when unowned
        """
        for entry in self.routes.values():
            matched = entry.matcher.match(pathname)
            if matched:
                return entry, matched.groupdict()
        return None

    def allowed_methods(self, pathname: str) -> list[str] | None:
        """
        List the methods allowed on a concrete path.

        ``OPTIONS`` is always allowed, and ``HEAD`` is allowed wherever ``GET`` is.

        Args:
            pathname: Request path

        Returns:
            Allowed methods, or None when the path is unowned
        """
        entry = self.find(pathname)
        if entry is None:
            return None
        methods = set(entry.methods)
        if "GET" in methods:
            methods.add("HEAD")
        methods.add("OPTIONS")
        return sorted(methods)

    def describe(self) -> list[dict[str, Any]]:
        """
        Render the registry as the ``routes`` member of a service description.

        Returns:
            Route descriptions, ordered by path
        """
        descriptions = []
        for entry in self.routes.values():
            summary = next(
                (
                    meta["summary"]
                    for meta in entry.methods.values()
                    if meta.get("summary")
                ),
                None,
            )
            description: dict[str, Any] = {
                "path": entry.pattern,
                "methods": self.allowed_methods(entry.pattern) or [],
            }
            if summary:
                description["summary"] = summary
            descriptions.append(description)
        return sorted(descriptions, key=lambda entry: entry["path"])
