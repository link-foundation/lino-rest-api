"""
Run the code blocks of ``python/README.md`` so that the documentation cannot
drift away from the package: every snippet below is copied from the README.
"""

import asyncio
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "src"))

import uvicorn  # noqa: E402
from lino_rest_api import (  # noqa: E402
    LinoClientError,
    LinoHttpError,
    MemoryStore,
    create_async_lino_client,
    create_lino_app,
    create_lino_client,
    created,
    no_content,
    status,
)

# --- Quick start -----------------------------------------------------------
app = create_lino_app(title="Tasks API", version="1.0.0", cors=True)

tasks = MemoryStore()
tasks.create({"title": "Write the specification", "done": True})

app.resource("/tasks", tasks, name="task")

app.get("/health", lambda request: {"status": "ok"})

# --- Handlers --------------------------------------------------------------
app.post("/echo", lambda request: {"echoed": request.body})
app.post("/made", lambda request: created({"id": 7}, "/tasks/7"))
app.delete("/gone", lambda request: no_content())
app.get("/teapot", lambda request: status(418, {"short": True, "stout": True}))


@app.get("/guarded")
def guarded(request):
    raise LinoHttpError(403, "Not for you", title="Forbidden")


def serve() -> str:
    """Start the application on an ephemeral port and return its base URL."""
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.01)
    return f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"


base_url = serve()

# --- The client ------------------------------------------------------------
client = create_lino_client(base_url)

created_task = client.post("/tasks", {"title": "Ship it", "done": False})
assert created_task.status == 201, created_task.status
assert created_task.location == "/tasks/2", created_task.location
assert created_task.etag

page = client.list("/tasks", {"done": False, "sort": "-id", "limit": 10})
assert page["page"] == {"limit": 10, "offset": 0, "total": 1, "count": 1}, page["page"]

fresh = client.get("/tasks/2", if_none_match=created_task.etag)
assert fresh.status == 304 and fresh.data is None, fresh

try:
    client.get("/tasks/999")
    raise AssertionError("the missing task should have been a problem")
except LinoClientError as error:
    assert error.status == 404, error.status
    assert set(error.problem) >= {"type", "title", "status", "detail", "instance"}

# --- The curl example ------------------------------------------------------
raw = client.get("/tasks/1", headers={"Accept": "text/lino"})
expected = '(\n  title "Write the specification"\n  done true\n  id 1\n)'
assert raw.response.text == expected, repr(raw.response.text)

# --- The rest of the handler block -----------------------------------------
assert client.get("/health").data == {"status": "ok"}
assert client.post("/echo", {"a": 1}).data == {"echoed": {"a": 1}}
assert client.post("/made").status == 201
assert client.delete("/gone").status == 204
try:
    client.get("/teapot")
    raise AssertionError("418 should have been raised")
except LinoClientError as error:
    assert error.status == 418, error.status
try:
    client.get("/guarded")
    raise AssertionError("403 should have been raised")
except LinoClientError as error:
    assert error.status == 403 and error.problem["title"] == "Forbidden", error.problem

# --- Describing the service ------------------------------------------------
assert client.describe()["info"] == {"title": "Tasks API", "version": "1.0.0"}
assert app.openapi()["openapi"] == "3.1.0"
assert client.get("/.well-known/openapi.json").status == 200

client.close()


# --- The asynchronous client ------------------------------------------------
async def async_snippet() -> None:
    """The async block of the client section."""
    async with create_async_lino_client(base_url) as async_client:
        page = await async_client.list("/tasks", {"done": False})
        assert [task["title"] for task in page["items"]] == ["Ship it"], page


asyncio.run(async_snippet())

print("every README snippet runs")
