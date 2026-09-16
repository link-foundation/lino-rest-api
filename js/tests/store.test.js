/**
 * Tests for the in-memory store.
 */

import { test, assert } from "test-anywhere";
import { MemoryStore } from "../src/store.js";
import { parseCollectionQuery } from "../src/query.js";

test("seeded items receive sequential identifiers", () => {
  const store = new MemoryStore({ items: [{ name: "a" }, { name: "b" }] });
  assert.deepEqual(store.get(1), { name: "a", id: 1 });
  assert.deepEqual(store.get(2), { name: "b", id: 2 });
});

test("an identifier from a path is normalised", () => {
  const store = new MemoryStore({ items: [{ name: "a" }] });
  assert.deepEqual(store.get("1"), { name: "a", id: 1 });
  assert.equal(store.normalizeId("abc"), "abc");
});

test("a provided identifier is honoured and moves the counter", () => {
  const store = new MemoryStore();
  store.create({ id: 10, name: "ten" });
  assert.equal(store.create({ name: "next" }).id, 11);
});

test("update replaces and patch merges", () => {
  const store = new MemoryStore({ items: [{ name: "a", done: false }] });
  assert.deepEqual(store.update(1, { name: "b" }), { name: "b", id: 1 });
  assert.deepEqual(store.patch(1, { done: true }), {
    name: "b",
    done: true,
    id: 1,
  });
  assert.equal(store.update(99, {}), undefined);
  assert.equal(store.patch(99, {}), undefined);
});

test("remove reports whether anything was deleted", () => {
  const store = new MemoryStore({ items: [{ name: "a" }] });
  assert.equal(store.remove(1), true);
  assert.equal(store.remove(1), false);
});

test("list applies a collection query", () => {
  const store = new MemoryStore({
    items: [
      { name: "a", done: true },
      { name: "b", done: false },
    ],
  });
  const envelope = store.list(parseCollectionQuery({ done: "true" }));
  assert.equal(envelope.page.total, 1);
  assert.equal(envelope.items[0].name, "a");
});

test("clear empties the store", () => {
  const store = new MemoryStore({ items: [{ name: "a" }] });
  store.clear();
  assert.equal(store.items.size, 0);
  assert.equal(store.create({ name: "b" }).id, 1);
});

test("a custom identifier field is supported", () => {
  const store = new MemoryStore({ idField: "key" });
  assert.equal(store.create({ name: "a" }).key, 1);
});
