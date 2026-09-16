"""End-to-end smoke test of the Python ASGI stack against the httpx client."""

import asyncio
import sys

sys.path.insert(0, "/tmp/gh-issue-solver-1789536249913/python/src")

import httpx

from lino_rest_api import AsyncLinoClient, LinoHttpError, MemoryStore, create_lino_app


def build_app():
    app = create_lino_app(title="Items API", version="1.0.0")
    app.resource("/items", MemoryStore(items=[{"name": "first"}]), name="item")
    app.get("/health", lambda request: {"status": "ok"})
    app.get("/empty", lambda request: None)

    def boom(request):
        raise LinoHttpError(409, "Already exists")

    app.get("/boom", boom)
    return app


async def main():
    app = build_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        client = AsyncLinoClient("http://test", client=http)

        health = await client.get("/health")
        print("health", health.status, health.data, health.headers.get("content-type"))

        created = await client.post("/items", {"name": "second"})
        print("created", created.status, created.location, created.data)

        listing = await client.list("/items", {"limit": 1})
        print("list", listing)

        first = await client.get("/items/1")
        print("get", first.status, first.etag, first.data)

        cached = await client.get("/items/1", if_none_match=first.etag)
        print("304", cached.status, cached.data)

        updated = await client.patch("/items/1", {"done": True}, if_match=first.etag)
        print("patch", updated.status, updated.data)

        try:
            await client.patch("/items/1", {"done": False}, if_match=first.etag)
        except Exception as error:
            print("stale", getattr(error, "status", None))

        try:
            await client.get("/boom")
        except Exception as error:
            print("boom", getattr(error, "status", None), error, getattr(error, "problem", None))

        print("empty", (await client.get("/empty")).status)
        print("options", await client.options("/health"))
        head = await client.head("/health")
        print("head", head.status, head.data, head.etag)
        description = await client.describe()
        print("describe", description["info"], [r["path"] for r in description["routes"]])
        openapi = await client.get("/.well-known/openapi.json")
        print("openapi", openapi.status, openapi.headers.get("content-type"), list(openapi.data)[:4])
        print("delete", (await client.delete("/items/1")).status)
        try:
            await client.get("/items/1")
        except Exception as error:
            print("after delete", getattr(error, "status", None))

        raw = await http.get("/items", headers={"Accept": "application/xml"})
        print("406", raw.status_code, raw.headers.get("content-type"), raw.text[:120])
        raw = await http.post(
            "/items", headers={"Content-Type": "application/xml"}, content="<x/>"
        )
        print("415", raw.status_code)
        raw = await http.request("OPTIONS", "/items", headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
        })
        print("preflight", raw.status_code, dict(raw.headers))


asyncio.run(main())
