"""
A complete Links Notation REST service and a client that talks to it.

Run with ``python examples/basic_usage.py`` from the ``python`` directory. The
script starts a server on an ephemeral port, drives every part of the protocol
through the client and prints the wire representations, so the output doubles as
a protocol tour.
"""

import asyncio
import threading
import time

import httpx
import uvicorn

from lino_rest_api import (
    LINO_CONTENT_TYPE,
    AsyncLinoClient,
    LinoClientError,
    MemoryStore,
    create_lino_app,
    encode,
)

app = create_lino_app(
    title="Tasks API",
    version="1.0.0",
    description="A task list served as Links Notation instead of JSON",
    cors=True,
)

tasks = MemoryStore()
tasks.create({"title": "Write the specification", "done": True, "priority": 1})
tasks.create({"title": "Implement the server", "done": False, "priority": 2})
tasks.create({"title": "Implement the client", "done": False, "priority": 3})

# One call registers list, create, get, replace, merge and delete, together with
# automatic HEAD, automatic OPTIONS, 405, entity tags and problem details.
app.resource("/tasks", tasks, name="task")

app.get("/health", lambda request: {"status": "ok"}, {"summary": "Liveness probe"})


def section(title: str) -> None:
    """
    Print a labelled section.

    Args:
        title: Section title
    """
    print(f"\n=== {title} ===")


async def tour(base: str) -> None:
    """
    Drive the running service through every part of the protocol.

    Args:
        base: Base URL of the running service
    """
    async with AsyncLinoClient(base) as client:
        section("The service describes itself")
        print(encode(await client.describe()))

        section("Create a task")
        created = await client.post(
            "/tasks",
            {"title": "Ship the release", "done": False, "priority": 4},
        )
        print(f"status   {created.status}")
        print(f"location {created.location}")
        print(f"etag     {created.etag}")
        print(encode(created.data))

        section("List, filter, sort and paginate")
        page = await client.list(
            "/tasks", {"done": False, "sort": "-priority", "limit": 2}
        )
        print(encode(page))

        section("The raw wire format")
        async with httpx.AsyncClient() as http:
            raw = await http.get(
                f"{base}/tasks/1", headers={"Accept": LINO_CONTENT_TYPE}
            )
        print(f"content-type {raw.headers['content-type']}")
        print(raw.text)

        section("Conditional requests")
        current = await client.get("/tasks/1")
        cached = await client.get("/tasks/1", if_none_match=current.etag)
        print(f"unchanged    {cached.status} (nothing was transferred)")

        updated = await client.patch("/tasks/1", {"done": False}, if_match=current.etag)
        print(f"updated      {updated.status} with a new etag {updated.etag}")

        try:
            await client.patch("/tasks/1", {"done": True}, if_match=current.etag)
        except LinoClientError as error:
            print(f"lost update  {error.status} {error}")

        section("Errors are problem details, in Links Notation")
        try:
            await client.get("/tasks/999")
        except LinoClientError as error:
            print(encode(error.problem))

        section("Allowed methods")
        print(f"/tasks     {', '.join(await client.options('/tasks'))}")
        print(f"/tasks/1   {', '.join(await client.options('/tasks/1'))}")

        section("Delete")
        print(f"status {(await client.delete(created.location)).status}")


def main() -> None:
    """Start the service on an ephemeral port and run the tour against it."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        while not server.started:
            time.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        asyncio.run(tour(f"http://127.0.0.1:{port}"))
    finally:
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == "__main__":
    main()
