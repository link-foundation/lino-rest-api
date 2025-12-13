/**
 * Tests for LinoApp.
 */

import { test, assert } from "test-anywhere";
import { createLinoApp, LinoApp } from "../src/app.js";

test("createLinoApp should return a LinoApp instance", () => {
  const app = createLinoApp();
  assert.ok(app instanceof LinoApp);
});

test("LinoApp should have HTTP method helpers", () => {
  const app = createLinoApp();

  assert.equal(typeof app.get, "function");
  assert.equal(typeof app.post, "function");
  assert.equal(typeof app.put, "function");
  assert.equal(typeof app.delete, "function");
  assert.equal(typeof app.patch, "function");
});

test("LinoApp should have use method", () => {
  const app = createLinoApp();
  assert.equal(typeof app.use, "function");
});

test("LinoApp should have listen method", () => {
  const app = createLinoApp();
  assert.equal(typeof app.listen, "function");
});

test("LinoApp should expose underlying Express app", () => {
  const app = createLinoApp();
  const expressApp = app.getExpressApp();

  assert.ok(expressApp);
  assert.equal(typeof expressApp.get, "function");
  assert.equal(typeof expressApp.post, "function");
});
