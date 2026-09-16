"""
In-memory resource store.

Implements the store interface :meth:`lino_rest_api.app.LinoApp.resource` expects,
so that a working CRUD API is one call away in examples, tests and prototypes.
"""

from typing import Any

from .collection import apply_collection_query
from .query import CollectionQuery


class MemoryStore:
    """A resource store backed by a dictionary."""

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        *,
        id_field: str = "id",
    ) -> None:
        """
        Args:
            items: Items to seed the store with
            id_field: Name of the identifier field
        """
        self.id_field = id_field
        self.items: dict[Any, dict[str, Any]] = {}
        self.next_id = 1
        for item in items or []:
            self.create(item)

    def normalize_id(self, identifier: Any) -> Any:
        """
        Normalise an identifier so that ``"1"`` from a path matches the stored 1.

        Args:
            identifier: Raw identifier

        Returns:
            Normalised identifier
        """
        if isinstance(identifier, str) and identifier:
            try:
                return int(identifier)
            except ValueError:
                return identifier
        return identifier

    def list(self, query: CollectionQuery) -> dict[str, Any]:
        """
        Run a collection query against the store.

        Args:
            query: Query from :func:`lino_rest_api.query.parse_collection_query`

        Returns:
            Collection envelope
        """
        return apply_collection_query(list(self.items.values()), query)

    def get(self, identifier: Any) -> dict[str, Any] | None:
        """
        Read one item.

        Args:
            identifier: Identifier

        Returns:
            Item, or None when absent
        """
        return self.items.get(self.normalize_id(identifier))

    def create(self, body: dict[str, Any] | None) -> dict[str, Any]:
        """
        Create an item, assigning an identifier when the body does not carry one.

        Args:
            body: Item body

        Returns:
            Created item
        """
        body = body or {}
        provided = body.get(self.id_field)
        if provided is None:
            identifier = self.next_id
            self.next_id += 1
        else:
            identifier = self.normalize_id(provided)
        numeric = isinstance(identifier, int) and not isinstance(identifier, bool)
        if numeric and identifier >= self.next_id:
            self.next_id = identifier + 1
        item = {**body, self.id_field: identifier}
        self.items[identifier] = item
        return item

    def update(self, identifier: Any, body: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        Replace an item.

        Args:
            identifier: Identifier
            body: Replacement body

        Returns:
            Updated item, or None when absent
        """
        key = self.normalize_id(identifier)
        if key not in self.items:
            return None
        item = {**(body or {}), self.id_field: key}
        self.items[key] = item
        return item

    def patch(self, identifier: Any, body: dict[str, Any] | None) -> dict[str, Any] | None:
        """
        Merge changes into an item.

        Args:
            identifier: Identifier
            body: Partial body

        Returns:
            Updated item, or None when absent
        """
        key = self.normalize_id(identifier)
        existing = self.items.get(key)
        if existing is None:
            return None
        item = {**existing, **(body or {}), self.id_field: key}
        self.items[key] = item
        return item

    def remove(self, identifier: Any) -> bool:
        """
        Delete an item.

        Args:
            identifier: Identifier

        Returns:
            True when an item was deleted
        """
        return self.items.pop(self.normalize_id(identifier), None) is not None

    def clear(self) -> None:
        """Remove every item."""
        self.items.clear()
        self.next_id = 1
