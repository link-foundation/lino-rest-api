/**
 * Tests for the codec layer (specification §2 and §3).
 */

import { test, assert } from "test-anywhere";
import {
  encode,
  decode,
  encodeSingleLine,
  decodeSingleLine,
  encodeCompactNotation,
  encodeFor,
  decodeFrom,
} from "../src/codec.js";
import {
  JSON_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
  LINO_PROBLEM_CONTENT_TYPE,
} from "../src/media-type.js";
import { throws } from "./helpers.js";

test("encode produces readable, indented Links Notation", () => {
  assert.equal(
    encode({ name: "Alice", age: 30 }),
    '(\n  name "Alice"\n  age 30\n)',
  );
});

test("encode renders nested structures with indentation", () => {
  assert.equal(
    encode({ user: { tags: ["a", "b"] } }),
    '(\n  user (\n    tags (\n      "a"\n      "b"\n    )\n  )\n)',
  );
});

test("decode is the inverse of encode", () => {
  const value = {
    name: "Alice",
    age: 30,
    active: true,
    missing: null,
    tags: ["developer", "nodejs"],
    nested: { deep: { value: 1.5 } },
  };
  assert.deepEqual(decode(encode(value)), value);
});

test("scalars round trip", () => {
  for (const value of [0, 1, -1, 1.5, "", "text", true, false, null]) {
    assert.deepEqual(decode(encode(value)), value);
  }
});

test("encodeSingleLine keeps the document on one line", () => {
  const line = encodeSingleLine({ a: 1, b: [2, 3] });
  assert.ok(!line.includes("\n"));
  assert.deepEqual(decodeSingleLine(line), { a: 1, b: [2, 3] });
});

test("the compact representation preserves shared references", () => {
  const shared = { id: 1 };
  const compact = encodeCompactNotation({ left: shared, right: shared });
  const decoded = decode(compact);
  assert.ok(decoded.left === decoded.right);
});

test("encodeFor dispatches on the media type", () => {
  const value = { a: 1 };
  assert.equal(encodeFor(value, LINO_CONTENT_TYPE), encode(value));
  assert.equal(
    encodeFor(value, LINO_LINE_CONTENT_TYPE),
    encodeSingleLine(value),
  );
  assert.equal(
    encodeFor(value, LINO_COMPACT_CONTENT_TYPE),
    encodeCompactNotation(value),
  );
  assert.equal(encodeFor(value, JSON_CONTENT_TYPE), '{"a":1}');
});

test("decodeFrom dispatches on the media type", () => {
  assert.deepEqual(decodeFrom("(\n  a 1\n)", LINO_CONTENT_TYPE), { a: 1 });
  assert.deepEqual(decodeFrom("(o: (a 1))", LINO_LINE_CONTENT_TYPE), { a: 1 });
  assert.deepEqual(decodeFrom('{"a":1}', JSON_CONTENT_TYPE), { a: 1 });
});

test("problem media types decode as their base representation", () => {
  assert.deepEqual(
    decodeFrom("(\n  status 404\n)", LINO_PROBLEM_CONTENT_TYPE),
    {
      status: 404,
    },
  );
});

test("encodeFor rejects an unknown media type", () => {
  const error = throws(() => encodeFor({}, "image/png"));
  assert.ok(error instanceof TypeError);
});
