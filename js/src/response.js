/**
 * Explicit response values.
 *
 * A handler may return a plain value, which is sent as `200`, or one of these
 * results when it needs to control the status code or the headers.
 */

/**
 * A handler result carrying a status code and headers alongside the value.
 */
export class LinoResult {
  /**
   * @param {*} value - Value to encode, or undefined for an empty body
   * @param {number} [status] - HTTP status code
   * @param {object} [headers] - Response headers
   * @param {object} [options] - Response options forwarded to `res.lino`
   */
  constructor(value, status = 200, headers = {}, options = {}) {
    this.value = value;
    this.status = status;
    this.headers = headers;
    this.options = options;
  }
}

/**
 * A `200 OK` carrying a value.
 *
 * @param {*} value - Value to encode
 * @param {object} [headers] - Response headers
 * @returns {LinoResult} Handler result
 */
export function ok(value, headers = {}) {
  return new LinoResult(value, 200, headers);
}

/**
 * A `201 Created` carrying a value and a `Location`.
 *
 * @param {*} value - Value to encode
 * @param {string} location - URI of the created resource
 * @param {object} [headers] - Additional response headers
 * @returns {LinoResult} Handler result
 */
export function created(value, location, headers = {}) {
  return new LinoResult(value, 201, { Location: location, ...headers });
}

/**
 * A `202 Accepted` carrying a value.
 *
 * @param {*} value - Value to encode
 * @param {object} [headers] - Response headers
 * @returns {LinoResult} Handler result
 */
export function accepted(value, headers = {}) {
  return new LinoResult(value, 202, headers);
}

/**
 * A `204 No Content`.
 *
 * @param {object} [headers] - Response headers
 * @returns {LinoResult} Handler result
 */
export function noContent(headers = {}) {
  return new LinoResult(undefined, 204, headers);
}

/**
 * A response with an explicit status code.
 *
 * @param {number} statusCode - HTTP status code
 * @param {*} [value] - Value to encode
 * @param {object} [headers] - Response headers
 * @returns {LinoResult} Handler result
 */
export function status(statusCode, value, headers = {}) {
  return new LinoResult(value, statusCode, headers);
}
