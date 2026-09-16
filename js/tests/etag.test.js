/**
 * Tests for entity tags and conditional requests (specification §7).
 */

import { test, assert } from "test-anywhere";
import {
  computeETag,
  etagMatches,
  evaluatePreconditions,
  parseETagList,
} from "../src/etag.js";
import { LinoHttpError } from "../src/problem.js";
import { throws } from "./helpers.js";

test("an entity tag is a quoted hex sha-256 of the body", () => {
  const etag = computeETag("hello");
  assert.match(etag, /^"[0-9a-f]{64}"$/);
  assert.equal(etag, computeETag("hello"));
  assert.notEqual(etag, computeETag("hellp"));
});

test("an entity tag list is split on commas and weak prefixes dropped", () => {
  // This package only ever emits strong tags, so a weak reference to one of them
  // is treated as a reference to the tag itself.
  assert.deepEqual(parseETagList('"a", W/"b"'), ['"a"', '"b"']);
  assert.deepEqual(parseETagList(undefined), []);
});

test("a wildcard matches any entity tag", () => {
  assert.ok(etagMatches("*", '"a"'));
  assert.ok(etagMatches('"a", "b"', '"b"'));
  assert.ok(!etagMatches('"a"', '"b"'));
});

test("If-None-Match on a safe method yields 304", () => {
  const result = evaluatePreconditions(
    { "if-none-match": '"a"' },
    "GET",
    '"a"',
  );
  assert.equal(result.notModified, true);
});

test("a stale If-Match is a 412", () => {
  const error = throws(() =>
    evaluatePreconditions({ "if-match": '"old"' }, "PUT", '"new"'),
  );
  assert.ok(error instanceof LinoHttpError);
  assert.equal(error.status, 412);
});

test("a matching If-Match lets the request through", () => {
  const result = evaluatePreconditions({ "if-match": '"a"' }, "PUT", '"a"');
  assert.equal(result.notModified, false);
});

test("a missing required precondition is a 428", () => {
  const error = throws(() =>
    evaluatePreconditions({}, "DELETE", '"a"', { requirePrecondition: true }),
  );
  assert.ok(error instanceof LinoHttpError);
  assert.equal(error.status, 428);
});

test("If-None-Match on an unsafe method is a 412", () => {
  const error = throws(() =>
    evaluatePreconditions({ "if-none-match": "*" }, "PUT", '"a"'),
  );
  assert.ok(error instanceof LinoHttpError);
  assert.equal(error.status, 412);
});
