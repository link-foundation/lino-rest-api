"""
Demonstration server.

Serves a full CRUD resource plus a health endpoint, entirely in Links Notation.
Start it with ``python -m lino_rest_api.server`` and explore it with curl:

.. code-block:: sh

    curl -H 'Accept: text/lino' http://localhost:8000/.well-known/lino-api
    curl -H 'Content-Type: text/lino' --data-binary $'(\\n  name "first"\\n)' \\
      http://localhost:8000/items
"""

import os

from .app import create_lino_app
from .request import LinoHttpRequest
from .store import MemoryStore

#: The store backing the ``/items`` resource.
items = MemoryStore(
    [
        {"name": "first", "done": False},
        {"name": "second", "done": True},
    ]
)

#: The ASGI application, ready for ``uvicorn lino_rest_api.server:app``.
app = create_lino_app(
    title="Items API",
    description="A demonstration service that speaks Links Notation instead of JSON",
    version="1.0.0",
    cors=True,
)

app.resource("/items", items, name="item")


def health(request: LinoHttpRequest) -> dict[str, object]:
    """
    Report that the service is alive.

    Args:
        request: Request being served

    Returns:
        Liveness payload
    """
    return {"status": "ok", "items": len(items.items)}


app.get("/health", health, {"summary": "Health check"})


def main() -> None:
    """Run the demonstration server."""
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print(f"LINO REST API server running on port {port}")
    print(f'Try: curl -H "Accept: text/lino" http://localhost:{port}/health')
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
