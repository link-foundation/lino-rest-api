/**
 * Tests for the client (specification §10).
 */

import { test, assert } from "test-anywhere";
import { createLinoApp } from "../src/app.js";
import {
  DEFAULT_ACCEPT,
  LinoClient,
  LinoClientError,
  buildQueryString,
  createLinoClient,
} from "../src/client.js";
import { MemoryStore } from "../src/store.js";
import { LinoHttpError } from "../src/problem.js";
import { rejects, throws, withApp } from "./helpers.js";

/**
 * Build an application the client can talk to.
 *
 * @returns {object} Application under test
 */
function buildApp() {
  const app = createLinoApp({ title: "Items API", version: "1.0.0" });
  app.resource("/items", new MemoryStore({ items: [{ name: "first" }] }), {
    name: "item",
  });
  app.get("/health", () => ({ status: "ok" }));
  app.get("/empty", () => undefined);
  app.get("/boom", () => {
    throw new LinoHttpError(409, "Already exists");
  });
  return app;
}

test("the client asks for Links Notation first", () => {
  assert.equal(DEFAULT_ACCEPT, "text/lino, application/json;q=0.5");
  const client = createLinoClient("http://example.com/");
  assert.ok(client instanceof LinoClient);
  assert.equal(client.baseUrl, "http://example.com");
});

test("query strings expand list values", () => {
  assert.equal(buildQueryString(undefined), "");
  assert.equal(
    buildQueryString({ a: 1, b: [2, 3], c: undefined }),
    "?a=1&b=2&b=3",
  );
});

test("a client without fetch is rejected", () => {
  const error = throws(
    () => new LinoClient("http://example.com", { fetch: "not a function" }),
  );
  assert.ok(error instanceof TypeError);
});

test("the client encodes requests and decodes responses", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const health = await client.get("/health");
    assert.equal(health.status, 200);
    assert.deepEqual(health.data, { status: "ok" });

    const created = await client.post("/items", { name: "second" });
    assert.equal(created.status, 201);
    assert.equal(created.location, "/items/2");
    assert.equal(created.data.name, "second");
  });
});

test("a 4xx raises a typed error carrying the problem details", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const error = await rejects(() => client.get("/boom"));
    assert.ok(error instanceof LinoClientError);
    assert.equal(error.status, 409);
    assert.equal(error.problem.title, "Conflict");
    assert.equal(error.message, "Already exists");
  });
});

test("204 is the absence of a representation, not null", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const response = await client.get("/empty");
    assert.equal(response.status, 204);
    assert.equal(response.data, undefined);
  });
});

test("the client honours conditional requests", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const first = await client.get("/items/1");
    const cached = await client.get("/items/1", { ifNoneMatch: first.etag });
    assert.equal(cached.status, 304);
    assert.equal(cached.data, undefined);

    const updated = await client.patch(
      "/items/1",
      { done: true },
      {
        ifMatch: first.etag,
      },
    );
    assert.equal(updated.data.done, true);

    const stale = await rejects(() =>
      client.patch("/items/1", { done: false }, { ifMatch: first.etag }),
    );
    assert.equal(stale.status, 412);
  });
});

test("the client can list a collection", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const envelope = await client.list("/items", { limit: 1 });
    assert.equal(envelope.items.length, 1);
    assert.equal(envelope.page.limit, 1);
  });
});

test("the client reads the advertised methods", async () => {
  await withApp(buildApp(), async ({ client }) => {
    assert.deepEqual(await client.options("/health"), [
      "GET",
      "HEAD",
      "OPTIONS",
    ]);
  });
});

test("HEAD yields headers without a body", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const response = await client.head("/health");
    assert.equal(response.status, 200);
    assert.equal(response.data, undefined);
    assert.ok(response.etag);
  });
});

test("the client can read the service description", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const description = await client.describe();
    assert.equal(description.info.title, "Items API");
    assert.ok(description.routes.some((route) => route.path === "/items"));
  });
});

test("the request representation can be switched to JSON", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const client = createLinoClient(base, {
      accept: "application/json",
      contentType: "application/json",
    });
    const created = await client.post("/items", { name: "json" });
    assert.equal(created.status, 201);
    assert.equal(
      created.response.headers.get("content-type"),
      "application/json; charset=utf-8",
    );
  });
});

test("the client deletes a resource", async () => {
  await withApp(buildApp(), async ({ client }) => {
    assert.equal((await client.delete("/items/1")).status, 204);
    assert.equal((await rejects(() => client.get("/items/1"))).status, 404);
  });
});
