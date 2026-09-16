/**
 * Tests for collection processing (specification §6).
 */

import { test, assert } from "test-anywhere";
import {
  applyCollectionQuery,
  collectionEnvelope,
  matchesFilters,
  paginationLinkHeader,
  projectFields,
  sortItems,
} from "../src/collection.js";
import { parseCollectionQuery } from "../src/query.js";

const items = [
  { id: 1, name: "charlie", done: false, score: 3 },
  { id: 2, name: "alice", done: true, score: 1 },
  { id: 3, name: "bob", done: false, score: 2 },
];

test("filters compare equal values", () => {
  assert.ok(matchesFilters(items[0], { done: false }));
  assert.ok(!matchesFilters(items[0], { done: true }));
});

test("a list filter behaves like an any-of match", () => {
  assert.ok(matchesFilters(items[0], { name: ["alice", "charlie"] }));
  assert.ok(!matchesFilters(items[0], { name: ["alice", "bob"] }));
});

test("sorting supports several keys and directions", () => {
  assert.deepEqual(
    sortItems(items, [
      { field: "done", descending: false },
      { field: "name", descending: true },
    ]).map((item) => item.id),
    [1, 3, 2],
  );
});

test("sparse fieldsets keep only the requested members", () => {
  assert.deepEqual(projectFields(items[0], ["id", "name"]), {
    id: 1,
    name: "charlie",
  });
  assert.deepEqual(projectFields(items[0], null), items[0]);
});

test("the envelope reports the page and the total", () => {
  const envelope = collectionEnvelope([items[0]], {
    limit: 1,
    offset: 2,
    total: 3,
  });
  assert.deepEqual(envelope.page, { limit: 1, offset: 2, total: 3, count: 1 });
});

test("a query filters, sorts, paginates and projects", () => {
  const envelope = applyCollectionQuery(
    items,
    parseCollectionQuery({
      done: "false",
      sort: "name",
      limit: "1",
      fields: "name",
    }),
  );
  assert.deepEqual(envelope.items, [{ name: "bob" }]);
  assert.deepEqual(envelope.page, { limit: 1, offset: 0, total: 2, count: 1 });
});

test("Link carries first, prev, next and last", () => {
  const header = paginationLinkHeader(
    "/items",
    { done: "false" },
    {
      limit: 10,
      offset: 10,
      total: 35,
    },
  );
  assert.ok(header.includes('rel="first"'));
  assert.ok(
    header.includes('offset=0>; rel="first"') || header.includes("offset=0"),
  );
  assert.ok(header.includes('rel="prev"'));
  assert.ok(header.includes('rel="next"'));
  assert.ok(header.includes("offset=30"));
  assert.ok(header.includes("done=false"));
});

test("the first page has no prev link", () => {
  const header = paginationLinkHeader(
    "/items",
    {},
    { limit: 10, offset: 0, total: 5 },
  );
  assert.ok(!header.includes('rel="prev"'));
  assert.ok(!header.includes('rel="next"'));
});
