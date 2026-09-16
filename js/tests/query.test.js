/**
 * Tests for collection query parsing (specification §6).
 */

import { test, assert } from "test-anywhere";
import {
  DEFAULT_LIMIT,
  MAX_LIMIT,
  parseCollectionQuery,
  parseFields,
  parseScalar,
  parseSort,
} from "../src/query.js";
import { LinoHttpError } from "../src/problem.js";
import { throws } from "./helpers.js";

test("scalars in the query string are typed", () => {
  assert.equal(parseScalar("42"), 42);
  assert.equal(parseScalar("1.5"), 1.5);
  assert.equal(parseScalar("true"), true);
  assert.equal(parseScalar("false"), false);
  assert.equal(parseScalar("null"), null);
  assert.equal(parseScalar("text"), "text");
  assert.equal(parseScalar(""), "");
});

test("sort accepts a comma separated list with descending prefixes", () => {
  assert.deepEqual(parseSort("-created,name"), [
    { field: "created", descending: true },
    { field: "name", descending: false },
  ]);
  assert.deepEqual(parseSort(undefined), []);
});

test("fields is null when absent and a list when present", () => {
  assert.equal(parseFields(undefined), null);
  assert.deepEqual(parseFields("id,name"), ["id", "name"]);
});

test("defaults apply when the query is empty", () => {
  const query = parseCollectionQuery({});
  assert.equal(query.limit, DEFAULT_LIMIT);
  assert.equal(query.offset, 0);
  assert.deepEqual(query.sort, []);
  assert.equal(query.fields, null);
  assert.deepEqual(query.filters, {});
});

test("non reserved parameters become filters", () => {
  const query = parseCollectionQuery({
    limit: "5",
    offset: "10",
    sort: "-name",
    fields: "id",
    done: "true",
    tag: ["a", "b"],
  });
  assert.equal(query.limit, 5);
  assert.equal(query.offset, 10);
  assert.deepEqual(query.filters, { done: true, tag: ["a", "b"] });
});

test("limit is clamped to the maximum", () => {
  assert.equal(
    parseCollectionQuery({ limit: String(MAX_LIMIT + 50) }).limit,
    MAX_LIMIT,
  );
});

test("a malformed limit is a 400", () => {
  const badLimit = throws(() => parseCollectionQuery({ limit: "abc" }));
  assert.ok(badLimit instanceof LinoHttpError);
  assert.equal(badLimit.status, 400);

  const badOffset = throws(() => parseCollectionQuery({ offset: "-1" }));
  assert.ok(badOffset instanceof LinoHttpError);
  assert.equal(badOffset.status, 400);
});
