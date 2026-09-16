/**
 * Entity tags and conditional requests (specification §7).
 */

import { createHash } from "node:crypto";
import { LinoHttpError } from "./problem.js";

/**
 * Compute the strong entity tag of an encoded representation.
 *
 * @param {string} body - Encoded representation
 * @returns {string} Quoted hexadecimal SHA-256
 */
export function computeETag(body) {
  const digest = createHash("sha256").update(body, "utf-8").digest("hex");
  return `"${digest}"`;
}

/**
 * Split an `If-Match` or `If-None-Match` header into entity tags.
 *
 * @param {string} [headerValue] - Raw header value
 * @returns {string[]} Entity tags, with any weak prefix removed
 */
export function parseETagList(headerValue) {
  if (!headerValue) {
    return [];
  }
  return headerValue
    .split(",")
    .map((tag) => tag.trim().replace(/^W\//, ""))
    .filter(Boolean);
}

/**
 * Test whether an entity tag list matches the current tag.
 *
 * @param {string} [headerValue] - Raw `If-Match` / `If-None-Match` value
 * @param {string} currentETag - Entity tag of the current representation
 * @returns {boolean} True when the list matches
 */
export function etagMatches(headerValue, currentETag) {
  const tags = parseETagList(headerValue);
  return tags.includes("*") || tags.includes(currentETag);
}

/**
 * Evaluate the conditional request headers of a request.
 *
 * @param {object} headers - Request headers, lower-cased names
 * @param {string} method - HTTP method
 * @param {string} currentETag - Entity tag of the current representation
 * @param {object} [options] - Behaviour switches
 * @param {boolean} [options.requirePrecondition] - Demand `If-Match` on unsafe methods
 * @returns {{notModified: boolean}} Whether the response should be `304`
 * @throws {LinoHttpError} `412` on a failed `If-Match`, `428` when one is required
 */
export function evaluatePreconditions(
  headers,
  method,
  currentETag,
  options = {},
) {
  const safe = method === "GET" || method === "HEAD";
  const ifMatch = headers["if-match"];
  const ifNoneMatch = headers["if-none-match"];

  if (!safe) {
    if (ifMatch !== undefined) {
      if (!etagMatches(ifMatch, currentETag)) {
        throw new LinoHttpError(
          412,
          "The entity tag in If-Match does not match the current representation",
        );
      }
    } else if (options.requirePrecondition) {
      throw new LinoHttpError(
        428,
        "This request requires an If-Match precondition",
      );
    }
  }

  if (ifNoneMatch !== undefined && etagMatches(ifNoneMatch, currentETag)) {
    if (safe) {
      return { notModified: true };
    }
    throw new LinoHttpError(
      412,
      "The entity tag in If-None-Match matches the current representation",
    );
  }

  return { notModified: false };
}
