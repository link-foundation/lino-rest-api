/**
 * Tests for the route registry (specification §4.1 and §9).
 */

import { test, assert } from "test-anywhere";
import { RouteTable, compilePathPattern } from "../src/router.js";

test("path patterns match parameters and tolerate a trailing slash", () => {
  const matcher = compilePathPattern("/items/:id");
  assert.ok(matcher.test("/items/42"));
  assert.ok(matcher.test("/items/42/"));
  assert.ok(!matcher.test("/items"));
  assert.ok(!matcher.test("/items/42/tags"));
});

test("a dot in a path is matched literally", () => {
  const matcher = compilePathPattern("/.well-known/openapi.json");
  assert.ok(matcher.test("/.well-known/openapi.json"));
  assert.ok(!matcher.test("/.well-known/openapiXjson"));
});

test("OPTIONS is always allowed and HEAD follows GET", () => {
  const routes = new RouteTable();
  routes.register("GET", "/items");
  routes.register("POST", "/items");
  assert.deepEqual(routes.allowedMethods("/items"), [
    "GET",
    "HEAD",
    "OPTIONS",
    "POST",
  ]);
});

test("a path without GET does not advertise HEAD", () => {
  const routes = new RouteTable();
  routes.register("POST", "/jobs");
  assert.deepEqual(routes.allowedMethods("/jobs"), ["OPTIONS", "POST"]);
});

test("an unknown path has no allowed methods", () => {
  assert.equal(new RouteTable().allowedMethods("/missing"), null);
});

test("the registry renders the routes of a service description", () => {
  const routes = new RouteTable();
  routes.register("GET", "/items", { summary: "List items" });
  routes.register("GET", "/health");
  assert.deepEqual(routes.describe(), [
    { path: "/health", methods: ["GET", "HEAD", "OPTIONS"] },
    {
      path: "/items",
      methods: ["GET", "HEAD", "OPTIONS"],
      summary: "List items",
    },
  ]);
});
