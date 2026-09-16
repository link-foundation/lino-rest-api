/**
 * Codec layer: every conversion between host values and the wire.
 *
 * All Links Notation work is delegated to `lino-objects-codec`, which produces
 * byte-identical readable output in JavaScript, Python, Rust and C#. This module
 * only adapts that library's named-options API to the positional API this package
 * has always exposed, and adds the media-type dispatch described in
 * `docs/spec/README.md` §2.
 */

import {
  encode as encodeReadable,
  encodeLine,
  encodeCompact,
  decode as decodeAny,
  decodeLine,
  CircularReferenceError,
} from "lino-objects-codec";

import {
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  JSON_CONTENT_TYPE,
  normalizeMediaType,
} from "./media-type.js";

/**
 * Encode a value as readable, indented Links Notation.
 *
 * @param {*} value - Value to encode
 * @returns {string} Readable Links Notation
 */
export function encode(value) {
  return encodeReadable({ obj: value });
}

/**
 * Decode readable or compact Links Notation into a JavaScript value.
 *
 * @param {string} notation - Links Notation document
 * @returns {*} Decoded value
 */
export function decode(notation) {
  return decodeAny({ notation });
}

/**
 * Encode a value as single-line readable Links Notation.
 *
 * @param {*} value - Value to encode
 * @returns {string} One line of readable Links Notation
 */
export function encodeSingleLine(value) {
  return encodeLine({ obj: value });
}

/**
 * Decode one line of single-line readable Links Notation.
 *
 * @param {string} notation - One line of readable Links Notation
 * @returns {*} Decoded value
 */
export function decodeSingleLine(notation) {
  return decodeLine({ notation });
}

/**
 * Encode a value as compact, type-tagged Links Notation.
 *
 * This is the only representation that preserves shared object identity and
 * circular references.
 *
 * @param {*} value - Value to encode
 * @returns {string} Compact Links Notation
 */
export function encodeCompactNotation(value) {
  return encodeCompact({ obj: value });
}

/**
 * Encode a value for a concrete media type.
 *
 * @param {*} value - Value to encode
 * @param {string} mediaType - One of the media types of the specification
 * @returns {string} Encoded representation
 * @throws {TypeError} When the media type is not a representation of this API
 */
export function encodeFor(value, mediaType) {
  switch (normalizeMediaType(mediaType)) {
    case LINO_CONTENT_TYPE:
      return encode(value);
    case LINO_LINE_CONTENT_TYPE:
      return encodeSingleLine(value);
    case LINO_COMPACT_CONTENT_TYPE:
      return encodeCompactNotation(value);
    case JSON_CONTENT_TYPE:
      return JSON.stringify(value === undefined ? null : value);
    default:
      throw new TypeError(`Cannot encode to media type: ${mediaType}`);
  }
}

/**
 * Decode a representation of a concrete media type.
 *
 * @param {string} body - Raw request or response body
 * @param {string} mediaType - Media type the body was sent with
 * @returns {*} Decoded value
 * @throws {TypeError} When the media type is not a representation of this API
 */
export function decodeFrom(body, mediaType) {
  switch (normalizeMediaType(mediaType)) {
    case LINO_CONTENT_TYPE:
    case LINO_COMPACT_CONTENT_TYPE:
      return decode(body);
    case LINO_LINE_CONTENT_TYPE:
      return decodeSingleLine(body);
    case JSON_CONTENT_TYPE:
      return JSON.parse(body);
    default:
      throw new TypeError(`Cannot decode media type: ${mediaType}`);
  }
}

export { CircularReferenceError };
