/**
 * Collection query parsing (specification §6.2 - §6.4).
 *
 * Turns the reserved query parameters (`limit`, `offset`, `sort`, `fields`) and
 * the free-form field filters of a request URL into a structured query.
 */

import { LinoHttpError } from "./problem.js";

/** Query parameters that are not field filters. */
export const RESERVED_QUERY_PARAMETERS = ["limit", "offset", "sort", "fields"];

/** Page size used when a request does not ask for one. */
export const DEFAULT_LIMIT = 20;

/** Largest page a server will serve, whatever the request asks for. */
export const MAX_LIMIT = 100;

/**
 * Parse a filter value with the LINO scalar rules.
 *
 * `?done=true` filters on the boolean, `?id=7` on the integer, and anything else
 * stays a string.
 *
 * @param {string} raw - Raw query parameter value
 * @returns {*} Parsed scalar
 */
export function parseScalar(raw) {
  if (raw === "true") {
    return true;
  }
  if (raw === "false") {
    return false;
  }
  if (raw === "null") {
    return null;
  }
  if (raw !== "" && !Number.isNaN(Number(raw))) {
    return Number(raw);
  }
  return raw;
}

/**
 * Parse a bounded non-negative integer query parameter.
 *
 * @param {string|undefined} raw - Raw query parameter value
 * @param {number} fallback - Value used when the parameter is absent
 * @param {string} name - Parameter name, used in the error detail
 * @param {number} [maximum] - Largest accepted value
 * @returns {number} Parsed value
 * @throws {LinoHttpError} `400` when the value is not a non-negative integer
 */
function parseBoundedInteger(raw, fallback, name, maximum) {
  if (raw === undefined || raw === "") {
    return fallback;
  }
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 0) {
    throw new LinoHttpError(
      400,
      `Query parameter "${name}" must be a non-negative integer`,
    );
  }
  return maximum === undefined ? value : Math.min(value, maximum);
}

/**
 * Parse a `sort` parameter into ordered sort keys.
 *
 * @param {string|undefined} raw - Raw `sort` value
 * @returns {Array<{field: string, descending: boolean}>} Sort keys
 */
export function parseSort(raw) {
  if (!raw) {
    return [];
  }
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) =>
      part.startsWith("-")
        ? { field: part.slice(1), descending: true }
        : { field: part, descending: false },
    );
}

/**
 * Parse a `fields` parameter into a sparse fieldset.
 *
 * @param {string|undefined} raw - Raw `fields` value
 * @returns {string[]|null} Field names, or null when every field is requested
 */
export function parseFields(raw) {
  if (!raw) {
    return null;
  }
  const fields = raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return fields.length > 0 ? fields : null;
}

/**
 * Parse a full collection query from request query parameters.
 *
 * @param {object} query - Request query parameters
 * @param {object} [options] - Limits
 * @param {number} [options.defaultLimit] - Page size when unspecified
 * @param {number} [options.maxLimit] - Largest accepted page size
 * @returns {{limit: number, offset: number, sort: Array, fields: string[]|null, filters: object}} Parsed query
 */
export function parseCollectionQuery(query = {}, options = {}) {
  const defaultLimit = options.defaultLimit ?? DEFAULT_LIMIT;
  const maxLimit = options.maxLimit ?? MAX_LIMIT;

  const filters = {};
  for (const [name, value] of Object.entries(query)) {
    if (RESERVED_QUERY_PARAMETERS.includes(name)) {
      continue;
    }
    filters[name] = Array.isArray(value)
      ? value.map(parseScalar)
      : parseScalar(value);
  }

  return {
    limit: parseBoundedInteger(query.limit, defaultLimit, "limit", maxLimit),
    offset: parseBoundedInteger(query.offset, 0, "offset"),
    sort: parseSort(query.sort),
    fields: parseFields(query.fields),
    filters,
  };
}
