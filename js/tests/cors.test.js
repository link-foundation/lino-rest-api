/**
 * Tests for cross-origin requests (specification §8).
 */

import { test, assert } from "test-anywhere";
import {
  DEFAULT_ALLOWED_HEADERS,
  DEFAULT_EXPOSED_HEADERS,
  corsHeaders,
} from "../src/cors.js";
import { appendVary } from "../src/headers.js";

test("Content-Type and Accept are allowed so browsers can negotiate LINO", () => {
  assert.ok(DEFAULT_ALLOWED_HEADERS.includes("Content-Type"));
  assert.ok(DEFAULT_ALLOWED_HEADERS.includes("Accept"));
  assert.ok(DEFAULT_ALLOWED_HEADERS.includes("If-Match"));
});

test("ETag and Link are exposed so clients can follow the protocol", () => {
  assert.ok(DEFAULT_EXPOSED_HEADERS.includes("ETag"));
  assert.ok(DEFAULT_EXPOSED_HEADERS.includes("Link"));
});

test("the default policy allows any origin", () => {
  const headers = corsHeaders({}, "https://example.com");
  assert.equal(headers["Access-Control-Allow-Origin"], "*");
  assert.ok(headers["Access-Control-Allow-Methods"].includes("PATCH"));
});

test("an allow list reflects the request origin", () => {
  const options = { origin: ["https://example.com"] };
  assert.equal(
    corsHeaders(options, "https://example.com")["Access-Control-Allow-Origin"],
    "https://example.com",
  );
  assert.deepEqual(corsHeaders(options, "https://evil.example"), {});
});

test("credentialed requests echo the origin", () => {
  const headers = corsHeaders({ credentials: true }, "https://example.com");
  assert.equal(headers["Access-Control-Allow-Origin"], "https://example.com");
  assert.equal(headers["Access-Control-Allow-Credentials"], "true");
});

test("appendVary keeps existing field names", () => {
  const stored = {};
  const res = {
    getHeader: (name) => stored[name],
    set: (name, value) => {
      stored[name] = value;
    },
  };
  appendVary(res, "Accept");
  appendVary(res, "Origin");
  appendVary(res, "accept");
  assert.equal(stored.Vary, "Accept, Origin");
});
