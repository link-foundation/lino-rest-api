"""
CRUD resource registration.

Turns a store object into the six routes the specification describes for a
collection and its items, including pagination ``Link`` headers (section 6.1),
entity tags and conditional requests (section 7).
"""

import inspect
from typing import Any
from urllib.parse import quote

from .codec import encode_for
from .collection import apply_collection_query, pagination_link_header
from .etag import compute_etag, evaluate_preconditions
from .media_type import LINO_CONTENT_TYPE
from .problem import LinoHttpError
from .request import LinoHttpRequest
from .response import LinoResult, created, no_content

#: Operations a resource can expose, in registration order.
RESOURCE_OPERATIONS = ("list", "create", "get", "update", "patch", "remove")


async def _resolve(value: Any) -> Any:
    """
    Await a store result when the store is asynchronous.

    Args:
        value: Value returned by a store method

    Returns:
        The resolved value
    """
    if inspect.isawaitable(value):
        return await value
    return value


def representation_etag(request: LinoHttpRequest, value: Any) -> str:
    """
    Entity tag of a value in the representation the client asked for.

    Entity tags are per representation, which is why the negotiated media type is
    part of the computation and why every response carries ``Vary: Accept``.

    Args:
        request: Request being served
        value: Value to tag

    Returns:
        Quoted entity tag
    """
    return compute_etag(encode_for(value, request.media_type or LINO_CONTENT_TYPE))


def _not_found(name: str, identifier: Any) -> LinoHttpError:
    """
    Build the 404 raised when an item does not exist.

    Args:
        name: Human readable resource name
        id: Identifier that was looked up

    Returns:
        Problem to raise
    """
    return LinoHttpError(404, f"{name} {identifier} does not exist")


def _require_body(request: LinoHttpRequest) -> Any:
    """
    Require a decoded request body.

    Args:
        request: Request being served

    Returns:
        The body

    Raises:
        LinoHttpError: 400 when the body is missing
    """
    if request.body is None:
        raise LinoHttpError(400, "A request body is required")
    return request.body


def _to_envelope(result: Any, query: Any) -> dict[str, Any]:
    """
    Normalise whatever a store's ``list`` returned into a collection envelope.

    Args:
        result: List of items, or an envelope
        query: Parsed collection query

    Returns:
        Collection envelope
    """
    if isinstance(result, list):
        return apply_collection_query(result, query)
    return result


def register_resource(
    app: Any,
    base_path: str,
    store: Any,
    *,
    id_param: str = "id",
    id_field: str | None = None,
    name: str | None = None,
    operations: list[str] | tuple[str, ...] = RESOURCE_OPERATIONS,
    require_precondition: bool = False,
    upsert: bool = False,
    **query_options: Any,
) -> Any:
    """
    Register the routes of a CRUD resource on an application.

    Args:
        app: :class:`lino_rest_api.app.LinoApp` to register on
        base_path: Collection path, for example ``/items``
        store: Store implementing ``list``, ``get``, ``create``, ``update``,
            ``patch`` and ``remove``
        id_param: Path parameter holding the identifier
        id_field: Field of an item holding the identifier
        name: Human readable name used in problem details
        operations: Subset of :data:`RESOURCE_OPERATIONS` to expose
        require_precondition: Demand ``If-Match`` on ``PUT``, ``PATCH`` and ``DELETE``
        upsert: Let ``PUT`` create a missing item
        **query_options: ``default_limit`` and ``max_limit`` for the collection

    Returns:
        The application, for chaining
    """
    field = id_field or getattr(store, "id_field", "id")
    resource_name = name or base_path.strip("/")
    item_path = f"{base_path}/:{id_param}"

    async def load_for_write(request: LinoHttpRequest) -> Any:
        """
        Read the current item and evaluate ``If-Match`` against it before mutating.

        Args:
            request: Request being served

        Returns:
            The current item, or None when absent
        """
        existing = await _resolve(store.get(request.param(id_param)))
        if existing is None:
            return None
        evaluate_preconditions(
            request.headers,
            request.method,
            representation_etag(request, existing),
            require_precondition=require_precondition,
        )
        return existing

    async def list_items(request: LinoHttpRequest) -> LinoResult:
        """
        Serve one page of the collection.

        Args:
            request: Request being served

        Returns:
            Collection envelope with pagination links
        """
        query = request.collection_query(**query_options)
        envelope = _to_envelope(await _resolve(store.list(query)), query)
        page = envelope["page"]
        link = pagination_link_header(
            request.path,
            request.query,
            limit=page["limit"],
            offset=page["offset"],
            total=page["total"],
        )
        return LinoResult(envelope, 200, {"Link": link} if link else {})

    async def create_item(request: LinoHttpRequest) -> LinoResult:
        """
        Create one item.

        Args:
            request: Request being served

        Returns:
            The created item with its ``Location``
        """
        item = await _resolve(store.create(_require_body(request)))
        identifier = item.get(field) if isinstance(item, dict) else None
        if identifier is None:
            return LinoResult(item, 201)
        return created(item, f"{base_path}/{quote(str(identifier))}")

    async def get_item(request: LinoHttpRequest) -> Any:
        """
        Read one item.

        Args:
            request: Request being served

        Returns:
            The item

        Raises:
            LinoHttpError: 404 when the item does not exist
        """
        item = await _resolve(store.get(request.param(id_param)))
        if item is None:
            raise _not_found(resource_name, request.param(id_param))
        return item

    async def update_item(request: LinoHttpRequest) -> Any:
        """
        Replace one item, optionally creating it.

        Args:
            request: Request being served

        Returns:
            The updated item

        Raises:
            LinoHttpError: 404 when the item does not exist and upserts are off
        """
        body = _require_body(request)
        existing = await load_for_write(request)
        if existing is None:
            if not upsert:
                raise _not_found(resource_name, request.param(id_param))
            item = await _resolve(
                store.create({**body, field: request.param(id_param)})
            )
            return created(item, f"{base_path}/{quote(str(item.get(field)))}")
        return await _resolve(store.update(request.param(id_param), body))

    async def patch_item(request: LinoHttpRequest) -> Any:
        """
        Merge changes into one item.

        Args:
            request: Request being served

        Returns:
            The updated item

        Raises:
            LinoHttpError: 404 when the item does not exist
        """
        body = _require_body(request)
        existing = await load_for_write(request)
        if existing is None:
            raise _not_found(resource_name, request.param(id_param))
        return await _resolve(store.patch(request.param(id_param), body))

    async def remove_item(request: LinoHttpRequest) -> LinoResult:
        """
        Delete one item.

        Args:
            request: Request being served

        Returns:
            An empty 204

        Raises:
            LinoHttpError: 404 when the item does not exist
        """
        existing = await load_for_write(request)
        if existing is None:
            raise _not_found(resource_name, request.param(id_param))
        await _resolve(store.remove(request.param(id_param)))
        return no_content()

    registrations = {
        "list": lambda: app.get(
            base_path, list_items, {"summary": f"List {resource_name}"}
        ),
        "create": lambda: app.post(
            base_path, create_item, {"summary": f"Create {resource_name}"}
        ),
        "get": lambda: app.get(
            item_path, get_item, {"summary": f"Read one {resource_name}"}
        ),
        "update": lambda: app.put(
            item_path, update_item, {"summary": f"Replace one {resource_name}"}
        ),
        "patch": lambda: app.patch(
            item_path, patch_item, {"summary": f"Merge changes into one {resource_name}"}
        ),
        "remove": lambda: app.delete(
            item_path, remove_item, {"summary": f"Delete one {resource_name}"}
        ),
    }

    for operation in RESOURCE_OPERATIONS:
        if operation in operations:
            registrations[operation]()

    return app
