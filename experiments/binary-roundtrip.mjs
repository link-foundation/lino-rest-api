// Small bounded probe of the exact typed AST, including unary containers.
import {
  encodeFor,
  decodeFrom,
  LINO_BINARY_CONTENT_TYPE as binary,
} from "../js/src/index.js";
import assert from "node:assert/strict";
for (const value of [
  null,
  true,
  false,
  "",
  "123",
  "Ю🙂",
  {},
  [],
  ["one"],
  { a: [[], {}, { b: ["x"] }] },
]) {
  assert.deepEqual(decodeFrom(encodeFor(value, binary), binary), value);
}
