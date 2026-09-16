/**
 * Tests for content negotiation (specification §2.1).
 */

import { test, assert } from "test-anywhere";
import {
  JSON_CONTENT_TYPE,
  JSON_PROBLEM_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
  LINO_PROBLEM_CONTENT_TYPE,
  SUPPORTED_MEDIA_TYPES,
  isDecodableMediaType,
  negotiateMediaType,
  normalizeMediaType,
  parseAccept,
  parseContentType,
  problemMediaType,
  withCharset,
} from "../src/media-type.js";

test("text/lino is the default representation", () => {
  assert.equal(SUPPORTED_MEDIA_TYPES[0], LINO_CONTENT_TYPE);
  assert.equal(negotiateMediaType(undefined), LINO_CONTENT_TYPE);
  assert.equal(negotiateMediaType(""), LINO_CONTENT_TYPE);
  assert.equal(negotiateMediaType("*/*"), LINO_CONTENT_TYPE);
});

test("parseContentType drops parameters and lower-cases", () => {
  assert.equal(parseContentType("Text/LINO; charset=utf-8"), LINO_CONTENT_TYPE);
  assert.equal(parseContentType(undefined), "");
});

test("parseAccept orders ranges by quality then specificity", () => {
  const ranges = parseAccept("text/*;q=0.5, application/json, text/lino;q=0.8");
  assert.deepEqual(
    ranges.map((range) => range.type),
    ["application/json", "text/lino", "text/*"],
  );
});

test("negotiation honours quality values", () => {
  assert.equal(
    negotiateMediaType("application/json, text/lino;q=0.9"),
    JSON_CONTENT_TYPE,
  );
  assert.equal(
    negotiateMediaType("application/json;q=0.2, text/lino;q=0.9"),
    LINO_CONTENT_TYPE,
  );
});

test("a subtype wildcard selects the first supported match", () => {
  assert.equal(negotiateMediaType("text/*"), LINO_CONTENT_TYPE);
  assert.equal(negotiateMediaType("application/*"), JSON_CONTENT_TYPE);
});

test("q=0 excludes a representation", () => {
  assert.equal(
    negotiateMediaType("text/lino;q=0, application/json"),
    JSON_CONTENT_TYPE,
  );
});

test("negotiation fails when nothing is acceptable", () => {
  assert.equal(negotiateMediaType("image/png"), null);
});

test("every representation of the specification is negotiable", () => {
  for (const mediaType of [
    LINO_CONTENT_TYPE,
    LINO_LINE_CONTENT_TYPE,
    LINO_COMPACT_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
  ]) {
    assert.equal(negotiateMediaType(mediaType), mediaType);
    assert.ok(isDecodableMediaType(mediaType));
  }
});

test("problem media types normalise to their representation", () => {
  assert.equal(
    normalizeMediaType(LINO_PROBLEM_CONTENT_TYPE),
    LINO_CONTENT_TYPE,
  );
  assert.equal(
    normalizeMediaType(JSON_PROBLEM_CONTENT_TYPE),
    JSON_CONTENT_TYPE,
  );
  assert.equal(problemMediaType(LINO_CONTENT_TYPE), LINO_PROBLEM_CONTENT_TYPE);
  assert.equal(problemMediaType(JSON_CONTENT_TYPE), JSON_PROBLEM_CONTENT_TYPE);
  assert.equal(problemMediaType("text/lino-line"), "text/lino-line");
});

test("withCharset appends utf-8", () => {
  assert.equal(withCharset(LINO_CONTENT_TYPE), "text/lino; charset=utf-8");
});

test("an unknown media type is not decodable", () => {
  assert.ok(!isDecodableMediaType("application/xml"));
});
