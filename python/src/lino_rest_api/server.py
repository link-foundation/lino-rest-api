"""
Example server demonstrating lino-rest-api usage.

This server provides a simple REST API using Links Notation
instead of JSON for data exchange.
"""

from datetime import datetime
from typing import Any

from .app import LinoAPI
from .middleware import LinoResponse

# Create the LINO API
api = LinoAPI(
    title="LINO REST API Demo",
    description="Example REST API using Links Notation instead of JSON",
    version="0.1.0",
)

# In-memory data store for demo
items: dict[int, dict[str, Any]] = {}
next_id = 1


@api.get("/items")
def list_items():
    """List all items."""
    return {
        "items": list(items.values()),
        "count": len(items),
    }


@api.get("/items/{item_id}")
async def get_item(request):
    """Get item by ID."""
    item_id = int(request.path_params.get("item_id"))
    item = items.get(item_id)

    if not item:
        return LinoResponse(content={"error": "Item not found"}, status_code=404)

    return item


@api.post("/items")
async def create_item(body):
    """Create a new item."""
    global next_id

    item_id = next_id
    next_id += 1

    item = {
        "id": item_id,
        **(body or {}),
        "created_at": datetime.now().isoformat(),
    }

    items[item_id] = item

    return {"created": item}


@api.put("/items/{item_id}")
async def update_item(request, body):
    """Update an item."""
    item_id = int(request.path_params.get("item_id"))

    if item_id not in items:
        return LinoResponse(content={"error": "Item not found"}, status_code=404)

    item = {
        "id": item_id,
        **(body or {}),
        "updated_at": datetime.now().isoformat(),
    }

    items[item_id] = item

    return {"updated": item}


@api.delete("/items/{item_id}")
async def delete_item(request):
    """Delete an item."""
    item_id = int(request.path_params.get("item_id"))

    if item_id not in items:
        return LinoResponse(content={"error": "Item not found"}, status_code=404)

    del items[item_id]

    return {"deleted": item_id}


@api.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    }


# Get the FastAPI app for uvicorn
app = api.get_fastapi_app()


if __name__ == "__main__":
    import uvicorn

    print("Starting LINO REST API server...")
    print("Try: curl -H 'Content-Type: text/lino' http://localhost:8000/health")
    uvicorn.run(app, host="0.0.0.0", port=8000)
