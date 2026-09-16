/**
 * The conformance checklist of the specification (§11), one test per item.
 *
 * These tests drive a complete application over real HTTP, so they double as the
 * executable definition of "this implementation conforms".
 */

import { test, assert } from "test-anywhere";
import { createLinoApp } from "../src/app.js";
import { MemoryStore } from "../src/store.js";
import { decodeFrom, encodeFor, encodeSingleLine } from "../src/codec.js";
import {
  JSON_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
} from "../src/media-type.js";
import { withApp } from "./helpers.js";

/**
 * Build the application every conformance test runs against.
 *
 * @returns {object} A {@link LinoApp} with a seeded `/items` collection
 */
function buildApp() {
  const app = createLinoApp({
    title: "Conformance API",
    version: "1.0.0",
    cors: true,
  });
  const items = new MemoryStore();
  items.create({ name: "first", tag: "a", rank: 2 });
  items.create({ name: "second", tag: "b", rank: 1 });
  items.create({ name: "third", tag: "a", rank: 3 });
  app.resource("/items", items, { name: "item" });
  return app;
}

/**
 * Run a raw request against a live application.
 *
 * @param {string} base - Base URL
 * @param {string} path - Request path
 * @param {object} [init] - `fetch` init
 * @returns {Promise<Response>} The raw response
 */
function raw(base, path, init = {}) {
  return fetch(`${base}${path}`, init);
}

test("1. text/lino is decoded on requests and encoded on responses", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await raw(base, "/items", {
      method: "POST",
      headers: {
        "Content-Type": LINO_CONTENT_TYPE,
        Accept: LINO_CONTENT_TYPE,
      },
      body: encodeFor({ name: "fourth", tag: "c" }, LINO_CONTENT_TYPE),
    });

    assert.equal(response.status, 201);
    assert.ok(
      response.headers.get("content-type").startsWith(LINO_CONTENT_TYPE),
    );
    const created = decodeFrom(await response.text(), LINO_CONTENT_TYPE);
    assert.equal(created.name, "fourth");
    assert.equal(created.tag, "c");
  });
});

test("2. the single line and compact representations are negotiable", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const line = await raw(base, "/items/1", {
      headers: { Accept: LINO_LINE_CONTENT_TYPE },
    });
    assert.equal(
      line.headers.get("content-type").split(";")[0],
      LINO_LINE_CONTENT_TYPE,
    );
    const lineBody = await line.text();
    assert.ok(!lineBody.includes("\n"));
    assert.deepEqual(decodeFrom(lineBody, LINO_LINE_CONTENT_TYPE), {
      id: 1,
      name: "first",
      tag: "a",
      rank: 2,
    });

    const compact = await raw(base, "/items/1", {
      headers: { Accept: LINO_COMPACT_CONTENT_TYPE },
    });
    assert.equal(
      compact.headers.get("content-type").split(";")[0],
      LINO_COMPACT_CONTENT_TYPE,
    );
    assert.deepEqual(
      decodeFrom(await compact.text(), LINO_COMPACT_CONTENT_TYPE),
      { id: 1, name: "first", tag: "a", rank: 2 },
    );
  });
});

test("3. application/json remains available as a fallback", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await raw(base, "/items/1", {
      headers: { Accept: JSON_CONTENT_TYPE },
    });
    assert.equal(
      response.headers.get("content-type").split(";")[0],
      JSON_CONTENT_TYPE,
    );
    assert.deepEqual(await response.json(), {
      id: 1,
      name: "first",
      tag: "a",
      rank: 2,
    });

    const sent = await raw(base, "/items", {
      method: "POST",
      headers: { "Content-Type": JSON_CONTENT_TYPE, Accept: JSON_CONTENT_TYPE },
      body: JSON.stringify({ name: "json" }),
    });
    assert.equal(sent.status, 201);
    assert.equal((await sent.json()).name, "json");
  });
});

test("4. Accept quality values select a representation, 406 and Vary: Accept", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const negotiated = await raw(base, "/items/1", {
      headers: {
        Accept: `${JSON_CONTENT_TYPE};q=0.4, ${LINO_LINE_CONTENT_TYPE};q=0.9`,
      },
    });
    assert.equal(
      negotiated.headers.get("content-type").split(";")[0],
      LINO_LINE_CONTENT_TYPE,
    );
    assert.ok(
      negotiated.headers
        .get("vary")
        .toLowerCase()
        .split(",")
        .map((field) => field.trim())
        .includes("accept"),
    );

    const unacceptable = await raw(base, "/items/1", {
      headers: { Accept: "image/png" },
    });
    assert.equal(unacceptable.status, 406);
    const problem = decodeFrom(await unacceptable.text(), LINO_CONTENT_TYPE);
    assert.ok(problem.supported.includes(LINO_CONTENT_TYPE));
  });
});

test("5. an unsupported request media type is a 415", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await raw(base, "/items", {
      method: "POST",
      headers: { "Content-Type": "application/xml", Accept: LINO_CONTENT_TYPE },
      body: "<item/>",
    });
    assert.equal(response.status, 415);
    const problem = decodeFrom(await response.text(), LINO_CONTENT_TYPE);
    assert.equal(problem.status, 415);
    assert.ok(problem.supported.includes(LINO_CONTENT_TYPE));
  });
});

test("6. every method carries the semantics of section 4.1", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const created = await client.post("/items", { name: "sixth", tag: "z" });
    assert.equal(created.status, 201);
    assert.equal(created.location, `/items/${created.data.id}`);

    const read = await client.get(created.location);
    assert.deepEqual(read.data, created.data);

    const head = await client.head(created.location);
    assert.equal(head.status, 200);
    assert.equal(head.data, undefined);
    assert.equal(head.etag, read.etag);

    const replaced = await client.put(created.location, { name: "replaced" });
    assert.deepEqual(replaced.data, { id: created.data.id, name: "replaced" });

    const merged = await client.patch(created.location, { tag: "y" });
    assert.deepEqual(merged.data, {
      id: created.data.id,
      name: "replaced",
      tag: "y",
    });

    const removed = await client.delete(created.location);
    assert.equal(removed.status, 204);
    assert.equal(removed.data, undefined);
  });
});

test("7. HEAD, OPTIONS and 405 are automatic and carry Allow", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const head = await raw(base, "/items/1", { method: "HEAD" });
    assert.equal(head.status, 200);
    assert.equal(await head.text(), "");
    assert.ok(head.headers.get("etag"));

    const options = await raw(base, "/items/1", { method: "OPTIONS" });
    assert.equal(options.status, 204);
    assert.equal(
      options.headers.get("allow"),
      "DELETE, GET, HEAD, OPTIONS, PATCH, PUT",
    );

    const collectionOptions = await raw(base, "/items", { method: "OPTIONS" });
    assert.equal(
      collectionOptions.headers.get("allow"),
      "GET, HEAD, OPTIONS, POST",
    );

    const notAllowed = await raw(base, "/items/1", {
      method: "POST",
      headers: { "Content-Type": LINO_CONTENT_TYPE },
      body: encodeFor({}, LINO_CONTENT_TYPE),
    });
    assert.equal(notAllowed.status, 405);
    assert.equal(
      notAllowed.headers.get("allow"),
      "DELETE, GET, HEAD, OPTIONS, PATCH, PUT",
    );
  });
});

test("8. every error path answers with problem details in LINO", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const response = await raw(base, "/items/404", {
      headers: { Accept: LINO_CONTENT_TYPE },
    });
    assert.equal(response.status, 404);
    assert.equal(
      response.headers.get("content-type").split(";")[0],
      "application/problem+lino",
    );

    const problem = decodeFrom(await response.text(), LINO_CONTENT_TYPE);
    assert.equal(
      problem.type,
      "https://link-foundation.github.io/lino-rest-api/errors/not-found",
    );
    assert.equal(problem.title, "Not Found");
    assert.equal(problem.status, 404);
    assert.equal(problem.instance, "/items/404");
    assert.ok(problem.detail);

    const unknown = await raw(base, "/nothing/here");
    assert.equal(unknown.status, 404);
    assert.equal(
      unknown.headers.get("content-type").split(";")[0],
      "application/problem+lino",
    );
  });
});

test("9. collections paginate, filter, sort and project", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const page = await client.get("/items", { query: { limit: 2, offset: 1 } });
    assert.equal(page.data.items.length, 2);
    assert.deepEqual(page.data.page, {
      limit: 2,
      offset: 1,
      total: 3,
      count: 2,
    });
    const links = page.headers.get("link");
    assert.ok(links.includes('rel="first"'));
    assert.ok(links.includes('rel="prev"'));
    assert.ok(links.includes('rel="last"'));

    const filtered = await client.list("/items", { tag: "a" });
    assert.equal(filtered.page.total, 2);
    assert.ok(filtered.items.every((item) => item.tag === "a"));

    const sorted = await client.list("/items", { sort: "-rank" });
    assert.deepEqual(
      sorted.items.map((item) => item.rank),
      [3, 2, 1],
    );

    const sparse = await client.list("/items", { fields: "id,name", limit: 1 });
    assert.deepEqual(sparse.items, [{ id: 1, name: "first" }]);
  });
});

test("10. conditional requests answer 304, 412 and 428", async () => {
  await withApp(buildApp(), async ({ base, client }) => {
    const first = await client.get("/items/1");
    assert.ok(first.etag);

    const cached = await client.get("/items/1", { ifNoneMatch: first.etag });
    assert.equal(cached.status, 304);
    assert.equal(cached.data, undefined);

    const stale = await raw(base, "/items/1", {
      method: "PATCH",
      headers: {
        "Content-Type": LINO_CONTENT_TYPE,
        "If-Match": '"stale"',
      },
      body: encodeFor({ tag: "c" }, LINO_CONTENT_TYPE),
    });
    assert.equal(stale.status, 412);

    const fresh = await client.patch(
      "/items/1",
      { tag: "c" },
      { ifMatch: first.etag },
    );
    assert.equal(fresh.status, 200);
    assert.equal(fresh.data.tag, "c");
    assert.notEqual(fresh.etag, first.etag);

    const strict = createLinoApp({ title: "Strict", version: "1.0.0" });
    const store = new MemoryStore();
    store.create({ name: "guarded" });
    strict.resource("/guarded", store, { requirePrecondition: true });
    await withApp(strict, async ({ base: strictBase }) => {
      const missing = await raw(strictBase, "/guarded/1", { method: "DELETE" });
      assert.equal(missing.status, 428);
    });
  });
});

test("11. CORS preflight and actual requests are answered", async () => {
  await withApp(buildApp(), async ({ base }) => {
    const wildcard = await raw(base, "/items/1", {
      headers: { Origin: "https://example.com" },
    });
    assert.equal(wildcard.headers.get("access-control-allow-origin"), "*");
    assert.ok(
      wildcard.headers.get("access-control-expose-headers").includes("ETag"),
    );
  });

  const restricted = createLinoApp({
    title: "Restricted",
    version: "1.0.0",
    cors: { origin: ["https://example.com"] },
  });
  restricted.resource("/items", new MemoryStore());

  await withApp(restricted, async ({ base }) => {
    const preflight = await raw(base, "/items", {
      method: "OPTIONS",
      headers: {
        Origin: "https://example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
      },
    });
    assert.equal(preflight.status, 204);
    assert.equal(
      preflight.headers.get("access-control-allow-origin"),
      "https://example.com",
    );
    assert.ok(
      preflight.headers.get("access-control-allow-methods").includes("POST"),
    );
    assert.ok(
      preflight.headers
        .get("vary")
        .toLowerCase()
        .split(",")
        .map((field) => field.trim())
        .includes("origin"),
    );

    const rejected = await raw(base, "/items", {
      headers: { Origin: "https://elsewhere.example" },
    });
    assert.equal(rejected.headers.get("access-control-allow-origin"), null);
  });
});

test("12. the service description and the OpenAPI document are published", async () => {
  await withApp(buildApp(), async ({ base, client }) => {
    const description = await client.describe();
    assert.equal(description.lino_api, "1.0");
    assert.equal(description.info.title, "Conformance API");
    assert.ok(description.media_types.includes(LINO_CONTENT_TYPE));
    const items = description.routes.find((route) => route.path === "/items");
    assert.deepEqual(items.methods, ["GET", "HEAD", "OPTIONS", "POST"]);

    const openapi = await raw(base, "/.well-known/openapi.json");
    assert.equal(
      openapi.headers.get("content-type").split(";")[0],
      JSON_CONTENT_TYPE,
    );
    const document = await openapi.json();
    assert.equal(document.openapi, "3.1.0");
    assert.equal(document.info.title, "Conformance API");
    assert.ok(document.paths["/items/{id}"].get);
    assert.ok(
      document.paths["/items"].post.requestBody.content[LINO_CONTENT_TYPE],
    );
  });
});

test("13. the client library covers the surface of section 10", async () => {
  await withApp(buildApp(), async ({ client }) => {
    const created = await client.post("/items", { name: "client" });
    assert.equal(created.status, 201);

    const listed = await client.list("/items", { limit: 10 });
    assert.equal(listed.page.total, 4);

    const allowed = await client.options("/items");
    assert.deepEqual(allowed, ["GET", "HEAD", "OPTIONS", "POST"]);

    const problem = await client
      .get("/items/999")
      .then(() => undefined)
      .catch((error) => error);
    assert.equal(problem.status, 404);
    assert.equal(problem.problem.title, "Not Found");
    assert.equal(problem.message, problem.problem.detail);

    const encoded = encodeSingleLine({ ok: true });
    assert.equal(typeof encoded, "string");
  });
});
