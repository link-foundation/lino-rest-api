/**
 * Object encoder/decoder for Links Notation format.
 *
 * Vendored from https://github.com/link-foundation/link-notation-objects-codec
 * until the package is published to npm.
 */

import { Parser, Link } from "links-notation";

/**
 * Codec for encoding/decoding JavaScript objects to/from Links Notation.
 */
export class ObjectCodec {
  // Type identifiers
  static TYPE_NULL = "null";
  static TYPE_UNDEFINED = "undefined";
  static TYPE_BOOL = "bool";
  static TYPE_INT = "int";
  static TYPE_FLOAT = "float";
  static TYPE_STR = "str";
  static TYPE_ARRAY = "array";
  static TYPE_OBJECT = "object";
  static TYPE_REF = "ref";

  constructor() {
    this.parser = new Parser();
    // For tracking object identity during encoding
    this._encodeMemo = new Map();
    this._encodeCounter = 0;
    // For tracking references during decoding
    this._decodeMemo = new Map();
  }

  /**
   * Create a Link from string parts.
   * @param {...string} parts - String parts to include in the link
   * @returns {Link} Link object with parts as Link values
   */
  _makeLink(...parts) {
    // Each part becomes a Link with that id
    const values = parts.map((part) => new Link(part));
    return new Link(undefined, values);
  }

  /**
   * Encode a JavaScript object to Links Notation format.
   * @param {*} obj - The JavaScript object to encode
   * @returns {string} String representation in Links Notation format
   */
  encode(obj) {
    // Reset memo for each encode operation
    this._encodeMemo = new Map();
    this._encodeCounter = 0;

    const link = this._encodeValue(obj);
    // Use the Link's format method directly
    return link.format();
  }

  /**
   * Decode Links Notation format to a JavaScript object.
   * @param {string} notation - String in Links Notation format
   * @returns {*} Reconstructed JavaScript object
   */
  decode(notation) {
    // Reset memo for each decode operation
    this._decodeMemo = new Map();

    const links = this.parser.parse(notation);
    if (!links || links.length === 0) {
      return null;
    }

    return this._decodeLink(links[0]);
  }

  /**
   * Encode a value into a Link.
   * @param {*} obj - The value to encode
   * @param {Set} visited - Set of object references currently being processed (for cycle detection)
   * @returns {Link} Link object
   */
  _encodeValue(obj, visited = new Set()) {
    // Check if we've seen this object before (for circular references and shared objects)
    // Only track objects and arrays (mutable types)
    if (obj !== null && typeof obj === "object") {
      if (this._encodeMemo.has(obj)) {
        // Return a reference to the previously encoded object
        const refId = this._encodeMemo.get(obj);
        return this._makeLink(ObjectCodec.TYPE_REF, refId);
      }

      // For mutable objects, check if we're in a cycle
      if (visited.has(obj)) {
        // We're in a cycle, create a reference
        if (!this._encodeMemo.has(obj)) {
          // Assign an ID for this object
          const refId = `obj_${this._encodeCounter}`;
          this._encodeCounter += 1;
          this._encodeMemo.set(obj, refId);
        }
        const refId = this._encodeMemo.get(obj);
        return this._makeLink(ObjectCodec.TYPE_REF, refId);
      }

      // Add to visited set
      visited = new Set([...visited, obj]);

      // Assign an ID to this object
      const refId = `obj_${this._encodeCounter}`;
      this._encodeCounter += 1;
      this._encodeMemo.set(obj, refId);
    }

    // Encode based on type
    if (obj === null) {
      return this._makeLink(ObjectCodec.TYPE_NULL);
    }

    if (obj === undefined) {
      return this._makeLink(ObjectCodec.TYPE_UNDEFINED);
    }

    if (typeof obj === "boolean") {
      return this._makeLink(ObjectCodec.TYPE_BOOL, String(obj));
    }

    if (typeof obj === "number") {
      // Handle special float values
      if (Number.isNaN(obj)) {
        return this._makeLink(ObjectCodec.TYPE_FLOAT, "NaN");
      }
      if (!Number.isFinite(obj)) {
        if (obj > 0) {
          return this._makeLink(ObjectCodec.TYPE_FLOAT, "Infinity");
        } else {
          return this._makeLink(ObjectCodec.TYPE_FLOAT, "-Infinity");
        }
      }
      // Check if it's an integer
      if (Number.isInteger(obj)) {
        return this._makeLink(ObjectCodec.TYPE_INT, String(obj));
      }
      return this._makeLink(ObjectCodec.TYPE_FLOAT, String(obj));
    }

    if (typeof obj === "string") {
      // Encode strings as base64 to handle special characters, newlines, etc.
      const b64Encoded = Buffer.from(obj, "utf-8").toString("base64");
      return this._makeLink(ObjectCodec.TYPE_STR, b64Encoded);
    }

    if (Array.isArray(obj)) {
      const refId = this._encodeMemo.get(obj);
      // Encode as: (array ref_id item0 item1 item2 ...)
      const parts = [new Link(ObjectCodec.TYPE_ARRAY), new Link(refId)];
      for (const item of obj) {
        // Encode each item
        const itemLink = this._encodeValue(item, visited);
        parts.push(itemLink);
      }
      return new Link(undefined, parts);
    }

    if (typeof obj === "object") {
      const refId = this._encodeMemo.get(obj);
      // Encode as: (object ref_id (key0 value0) (key1 value1) ...)
      const parts = [new Link(ObjectCodec.TYPE_OBJECT), new Link(refId)];
      for (const [key, value] of Object.entries(obj)) {
        // Encode key and value
        const keyLink = this._encodeValue(key, visited);
        const valueLink = this._encodeValue(value, visited);
        // Create a pair link
        const pair = new Link(undefined, [keyLink, valueLink]);
        parts.push(pair);
      }
      return new Link(undefined, parts);
    }

    throw new TypeError(`Unsupported type: ${typeof obj}`);
  }

  /**
   * Decode a Link into a JavaScript value.
   * @param {Link} link - Link object to decode
   * @returns {*} Decoded JavaScript value
   */
  _decodeLink(link) {
    if (!link.values || link.values.length === 0) {
      // Empty link - this might be a simple id
      if (link.id) {
        return link.id;
      }
      return null;
    }

    // Get the type marker from the first value
    const firstValue = link.values[0];
    if (!firstValue || !firstValue.id) {
      // Not a type marker we recognize
      return null;
    }

    const typeMarker = firstValue.id;

    if (typeMarker === ObjectCodec.TYPE_NULL) {
      return null;
    }

    if (typeMarker === ObjectCodec.TYPE_UNDEFINED) {
      return undefined;
    }

    if (typeMarker === ObjectCodec.TYPE_BOOL) {
      if (link.values.length > 1) {
        const boolValue = link.values[1];
        if (boolValue && boolValue.id) {
          return boolValue.id === "true";
        }
      }
      return false;
    }

    if (typeMarker === ObjectCodec.TYPE_INT) {
      if (link.values.length > 1) {
        const intValue = link.values[1];
        if (intValue && intValue.id) {
          return parseInt(intValue.id, 10);
        }
      }
      return 0;
    }

    if (typeMarker === ObjectCodec.TYPE_FLOAT) {
      if (link.values.length > 1) {
        const floatValue = link.values[1];
        if (floatValue && floatValue.id) {
          const valueStr = floatValue.id;
          if (valueStr === "NaN") {
            return NaN;
          } else if (valueStr === "Infinity") {
            return Infinity;
          } else if (valueStr === "-Infinity") {
            return -Infinity;
          } else {
            return parseFloat(valueStr);
          }
        }
      }
      return 0.0;
    }

    if (typeMarker === ObjectCodec.TYPE_STR) {
      if (link.values.length > 1) {
        const strValue = link.values[1];
        if (strValue && strValue.id) {
          const b64Str = strValue.id;
          // Decode from base64
          try {
            return Buffer.from(b64Str, "base64").toString("utf-8");
          } catch (e) {
            // If decode fails, return the raw value
            return b64Str;
          }
        }
      }
      return "";
    }

    if (typeMarker === ObjectCodec.TYPE_REF) {
      // This is a reference to a previously decoded object
      if (link.values.length > 1) {
        const refValue = link.values[1];
        if (refValue && refValue.id) {
          const refId = refValue.id;
          if (this._decodeMemo.has(refId)) {
            return this._decodeMemo.get(refId);
          }
        }
      }
      throw new Error("Unknown reference in link");
    }

    if (typeMarker === ObjectCodec.TYPE_ARRAY) {
      if (link.values.length < 2) {
        return [];
      }

      const refValue = link.values[1];
      const refId = refValue && refValue.id ? refValue.id : null;

      // Create the array object first (to handle circular references)
      const result = [];
      if (refId) {
        this._decodeMemo.set(refId, result);
      }

      // Decode items
      for (let i = 2; i < link.values.length; i++) {
        const itemLink = link.values[i];
        const decodedItem = this._decodeLink(itemLink);
        result.push(decodedItem);
      }

      return result;
    }

    if (typeMarker === ObjectCodec.TYPE_OBJECT) {
      if (link.values.length < 2) {
        return {};
      }

      const refValue = link.values[1];
      const refId = refValue && refValue.id ? refValue.id : null;

      // Create the object first (to handle circular references)
      const result = {};
      if (refId) {
        this._decodeMemo.set(refId, result);
      }

      // Decode key-value pairs
      for (let i = 2; i < link.values.length; i++) {
        const pairLink = link.values[i];
        if (pairLink && pairLink.values && pairLink.values.length >= 2) {
          // This should be a link with 2 values: key and value
          const keyLink = pairLink.values[0];
          const valueLink = pairLink.values[1];

          const decodedKey = this._decodeLink(keyLink);
          const decodedValue = this._decodeLink(valueLink);

          result[decodedKey] = decodedValue;
        }
      }

      return result;
    }

    // Unknown type marker
    throw new Error(`Unknown type marker: ${typeMarker}`);
  }
}

// Convenience functions
const _defaultCodec = new ObjectCodec();

/**
 * Encode a JavaScript object to Links Notation format.
 * @param {*} obj - The JavaScript object to encode
 * @returns {string} String representation in Links Notation format
 */
export function encode(obj) {
  return _defaultCodec.encode(obj);
}

/**
 * Decode Links Notation format to a JavaScript object.
 * @param {string} notation - String in Links Notation format
 * @returns {*} Reconstructed JavaScript object
 */
export function decode(notation) {
  return _defaultCodec.decode(notation);
}
