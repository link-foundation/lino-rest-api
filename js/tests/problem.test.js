/**
 * Tests for problem details (specification §5).
 */

import { test, assert } from "test-anywhere";
import {
  LinoHttpError,
  PROBLEM_TYPE_BASE,
  problemDetails,
  problemSlug,
  reasonPhrase,
  toHttpError,
  validationError,
} from "../src/problem.js";

test("reason phrases follow RFC 9110", () => {
  assert.equal(reasonPhrase(404), "Not Found");
  assert.equal(reasonPhrase(428), "Precondition Required");
  assert.equal(reasonPhrase(599), "Server Error");
  assert.equal(reasonPhrase(499), "Request Error");
});

test("problem slugs are the kebab-case reason phrase", () => {
  assert.equal(problemSlug("Not Found"), "not-found");
  assert.equal(problemSlug("Unsupported Media Type"), "unsupported-media-type");
});

test("problemDetails carries type, title and status", () => {
  const problem = problemDetails(404, "Item 42 does not exist", {
    instance: "/items/42",
  });
  assert.equal(problem.type, `${PROBLEM_TYPE_BASE}not-found`);
  assert.equal(problem.title, "Not Found");
  assert.equal(problem.status, 404);
  assert.equal(problem.detail, "Item 42 does not exist");
  assert.equal(problem.instance, "/items/42");
});

test("LinoHttpError renders itself as problem details", () => {
  const error = new LinoHttpError(409, "Already exists", {
    extensions: { conflictingId: 7 },
  });
  const problem = error.toProblem("/items");
  assert.equal(problem.status, 409);
  assert.equal(problem.title, "Conflict");
  assert.equal(problem.instance, "/items");
  assert.equal(problem.conflictingId, 7);
});

test("validationError lists field failures", () => {
  const error = validationError([{ field: "name", message: "is required" }]);
  const problem = error.toProblem("/items");
  assert.equal(problem.status, 422);
  assert.equal(problem.type, `${PROBLEM_TYPE_BASE}validation-failed`);
  assert.deepEqual(problem.errors, [{ field: "name", message: "is required" }]);
});

test("an arbitrary thrown value becomes a 500", () => {
  const error = toHttpError(new Error("boom"));
  assert.ok(error instanceof LinoHttpError);
  assert.equal(error.status, 500);
});

test("a LinoHttpError passes through toHttpError unchanged", () => {
  const original = new LinoHttpError(400, "bad");
  assert.ok(toHttpError(original) === original);
});

test("an error carrying a status is honoured", () => {
  const error = toHttpError(Object.assign(new Error("nope"), { status: 403 }));
  assert.equal(error.status, 403);
  assert.equal(error.detail, "nope");
});
