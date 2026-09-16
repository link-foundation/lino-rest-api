/**
 * Tests for the middleware layer (specification §2.1, §5 and §7).
 */

import { test, assert } from "test-anywhere";
import { createLinoApp } from "../src/app.js";
import { decode, encode, encodeSingleLine } from "../src/codec.js";
import {
  DEFAULT_MAX_BODY_BYTES,
  LINO_CONTENT_TYPE,
  linoBodyParser,
  linoMiddleware,
  linoNegotiation,
  linoResponse,
} from "../src/middleware.js";
import { withApp } from "./helpers.js";

/**
 * An application that echoes whatever body it receives.
 *
 * @param {object} [options] - Application options
 * @returns {object} Application under test
 */
function echoApp(options = {}) {
  const app = createLinoApp(options);
  app.get("/value", () => ({ a: 1, b: [2, 3] }));
  app.post("/echo", (req) => ({ echoed: req.body ?? null }));
  return app;
}

test("the middleware entry points are functions", () => {
  assert.equal(LINO_CONTENT_TYPE, "text/lino");
  assert.equal(typeof linoMiddleware, "function");
  assert.equal(typeof linoBodyParser, "function");
  assert.equal(typeof linoNegotiation, "function");
  assert.equal(typeof linoResponse, "function");
  assert.equal(DEFAULT_MAX_BODY_BYTES, 1024 * 1024);
});

test("Accept selects the response representation", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const cases = [
      ["text/lino", encode({ a: 1, b: [2, 3] })],
      ["text/lino-line", encodeSingleLine({ a: 1, b: [2, 3] })],
      ["application/json", JSON.stringify({ a: 1, b: [2, 3] })],
    ];
    for (const [accept, expected] of cases) {
      const response = await fetch(`${base}/value`, {
        headers: { Accept: accept },
      });
      assert.equal(
        response.headers.get("content-type"),
        `${accept}; charset=utf-8`,
      );
      assert.equal(await response.text(), expected);
    }
  });
});

test("an unacceptable Accept is a 406 listing what is supported", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const response = await fetch(`${base}/value`, {
      headers: { Accept: "image/png" },
    });
    assert.equal(response.status, 406);
    const problem = decode(await response.text());
    assert.ok(problem.supported.includes("text/lino"));
  });
});

test("Content-Type selects the request codec", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const cases = [
      ["text/lino", encode({ name: "a" })],
      ["text/lino-line", encodeSingleLine({ name: "a" })],
      ["application/json", JSON.stringify({ name: "a" })],
    ];
    for (const [contentType, body] of cases) {
      const response = await fetch(`${base}/echo`, {
        method: "POST",
        headers: { "Content-Type": contentType },
        body,
      });
      assert.equal(response.status, 200);
      assert.deepEqual(decode(await response.text()), {
        echoed: { name: "a" },
      });
    }
  });
});

test("an unsupported Content-Type is a 415", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const response = await fetch(`${base}/echo`, {
      method: "POST",
      headers: { "Content-Type": "application/xml" },
      body: "<a/>",
    });
    assert.equal(response.status, 415);
    assert.equal(decode(await response.text()).title, "Unsupported Media Type");
  });
});

test("a malformed body is a 400", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const response = await fetch(`${base}/echo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{not json",
    });
    assert.equal(response.status, 400);
  });
});

test("an oversized body is a 413", async () => {
  await withApp(echoApp({ maxBodyBytes: 64 }), async ({ base }) => {
    const response = await fetch(`${base}/echo`, {
      method: "POST",
      headers: { "Content-Type": "text/lino" },
      body: encode({ padding: "x".repeat(200) }),
    });
    assert.equal(response.status, 413);
  });
});

test("an empty body leaves req.body undefined", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const response = await fetch(`${base}/echo`, { method: "POST" });
    assert.deepEqual(decode(await response.text()), { echoed: null });
  });
});

test("responses carry a strong entity tag", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const response = await fetch(`${base}/value`);
    assert.match(response.headers.get("etag"), /^"[0-9a-f]{64}"$/);
  });
});

test("the entity tag depends on the representation", async () => {
  await withApp(echoApp(), async ({ base }) => {
    const lino = await fetch(`${base}/value`, {
      headers: { Accept: "text/lino" },
    });
    const json = await fetch(`${base}/value`, {
      headers: { Accept: "application/json" },
    });
    assert.notEqual(lino.headers.get("etag"), json.headers.get("etag"));
  });
});
