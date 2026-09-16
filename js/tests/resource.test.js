/**
 * Tests for CRUD resources (specification §6 and §7).
 */

import { test, assert } from "test-anywhere";
import { createLinoApp } from "../src/app.js";
import { decode, encode } from "../src/codec.js";
import { MemoryStore } from "../src/store.js";
import { withApp } from "./helpers.js";

/**
 * Build an application exposing a seeded `/items` resource.
 *
 * @param {object} [options] - Resource options
 * @returns {object} Application under test
 */
function itemsApp(options = {}) {
  const app = createLinoApp({ title: "Items API", version: "1.0.0" });
  const store = new MemoryStore({
    items: [
      { name: "charlie", done: false },
      { name: "alice", done: true },
      { name: "bob", done: false },
    ],
  });
  app.resource("/items", store, { name: "item", ...options });
  return app;
}

/**
 * Send a Links Notation request body.
 *
 * @param {string} url - Target URL
 * @param {string} method - HTTP method
 * @param {*} body - Value to encode
 * @param {object} [headers] - Extra headers
 * @returns {Promise<Response>} Raw response
 */
function send(url, method, body, headers = {}) {
  return fetch(url, {
    method,
    headers: { "Content-Type": "text/lino", ...headers },
    body: body === undefined ? undefined : encode(body),
  });
}

test("a collection is served in the envelope of the specification", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const envelope = decode(await (await fetch(`${base}/items`)).text());
    assert.equal(envelope.items.length, 3);
    assert.deepEqual(envelope.page, {
      limit: 20,
      offset: 0,
      total: 3,
      count: 3,
    });
  });
});

test("a collection can be filtered, sorted, paginated and projected", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const response = await fetch(
      `${base}/items?done=false&sort=-name&limit=1&fields=name`,
    );
    const envelope = decode(await response.text());
    assert.deepEqual(envelope.items, [{ name: "charlie" }]);
    assert.equal(envelope.page.total, 2);
    assert.ok(response.headers.get("link").includes('rel="next"'));
  });
});

test("creating an item answers 201 with a Location", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const response = await send(`${base}/items`, "POST", { name: "dave" });
    assert.equal(response.status, 201);
    assert.equal(response.headers.get("location"), "/items/4");
    assert.equal(decode(await response.text()).id, 4);
  });
});

test("creating an item without a body is a 400", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    assert.equal((await send(`${base}/items`, "POST")).status, 400);
  });
});

test("reading a missing item is a 404", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const response = await fetch(`${base}/items/99`);
    assert.equal(response.status, 404);
    assert.equal(decode(await response.text()).title, "Not Found");
  });
});

test("a conditional read answers 304", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const first = await fetch(`${base}/items/1`);
    const etag = first.headers.get("etag");
    const second = await fetch(`${base}/items/1`, {
      headers: { "If-None-Match": etag },
    });
    assert.equal(second.status, 304);
    assert.equal(await second.text(), "");
  });
});

test("replacing an item requires a matching If-Match", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const etag = (await fetch(`${base}/items/1`)).headers.get("etag");

    const stale = await send(
      `${base}/items/1`,
      "PUT",
      { name: "x" },
      {
        "If-Match": '"stale"',
      },
    );
    assert.equal(stale.status, 412);

    const fresh = await send(
      `${base}/items/1`,
      "PUT",
      { name: "x" },
      {
        "If-Match": etag,
      },
    );
    assert.equal(fresh.status, 200);
    assert.deepEqual(decode(await fresh.text()), { name: "x", id: 1 });
  });
});

test("a merge keeps the untouched members", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    const response = await send(`${base}/items/1`, "PATCH", { done: true });
    assert.deepEqual(decode(await response.text()), {
      name: "charlie",
      done: true,
      id: 1,
    });
  });
});

test("deleting an item answers 204 and then 404", async () => {
  await withApp(itemsApp(), async ({ base }) => {
    assert.equal(
      (await fetch(`${base}/items/1`, { method: "DELETE" })).status,
      204,
    );
    assert.equal((await fetch(`${base}/items/1`)).status, 404);
    assert.equal(
      (await fetch(`${base}/items/1`, { method: "DELETE" })).status,
      404,
    );
  });
});

test("requirePrecondition demands If-Match on unsafe methods", async () => {
  await withApp(itemsApp({ requirePrecondition: true }), async ({ base }) => {
    const response = await send(`${base}/items/1`, "PATCH", { done: true });
    assert.equal(response.status, 428);
    assert.equal(decode(await response.text()).title, "Precondition Required");
  });
});

test("upsert lets PUT create a missing item", async () => {
  await withApp(itemsApp({ upsert: true }), async ({ base }) => {
    const response = await send(`${base}/items/42`, "PUT", { name: "new" });
    assert.equal(response.status, 201);
    assert.equal(response.headers.get("location"), "/items/42");
  });
});

test("a subset of the operations can be exposed", async () => {
  await withApp(itemsApp({ operations: ["list", "get"] }), async ({ base }) => {
    const options = await fetch(`${base}/items`, { method: "OPTIONS" });
    assert.equal(options.headers.get("allow"), "GET, HEAD, OPTIONS");
    assert.equal(
      (await send(`${base}/items`, "POST", { name: "x" })).status,
      405,
    );
  });
});
