/**
 * Cross-origin resource sharing (specification §8).
 */

import { appendVary } from "./headers.js";

/** Headers a browser must be allowed to send to negotiate Links Notation. */
export const DEFAULT_ALLOWED_HEADERS = [
  "Content-Type",
  "Accept",
  "Authorization",
  "If-Match",
  "If-None-Match",
];

/** Headers a browser must be allowed to read to follow the protocol. */
export const DEFAULT_EXPOSED_HEADERS = ["ETag", "Link", "Location", "Allow"];

const DEFAULT_METHODS = [
  "GET",
  "HEAD",
  "OPTIONS",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
];

/**
 * Build the CORS response headers for a request.
 *
 * @param {object} [options] - Policy
 * @param {string|string[]} [options.origin] - Allowed origin(s), `"*"` by default
 * @param {string[]} [options.methods] - Allowed methods
 * @param {string[]} [options.allowedHeaders] - Allowed request headers
 * @param {string[]} [options.exposedHeaders] - Response headers exposed to scripts
 * @param {boolean} [options.credentials] - Allow credentialed requests
 * @param {number} [options.maxAge] - Preflight cache lifetime in seconds
 * @param {string} [requestOrigin] - `Origin` header of the request
 * @returns {object} Response headers
 */
export function corsHeaders(options = {}, requestOrigin) {
  const {
    origin = "*",
    methods = DEFAULT_METHODS,
    allowedHeaders = DEFAULT_ALLOWED_HEADERS,
    exposedHeaders = DEFAULT_EXPOSED_HEADERS,
    credentials = false,
    maxAge = 600,
  } = options;

  const allowedOrigins = Array.isArray(origin) ? origin : [origin];
  let allowOrigin = null;
  if (allowedOrigins.includes("*")) {
    allowOrigin = credentials && requestOrigin ? requestOrigin : "*";
  } else if (requestOrigin && allowedOrigins.includes(requestOrigin)) {
    allowOrigin = requestOrigin;
  }

  if (!allowOrigin) {
    return {};
  }

  const headers = {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": methods.join(", "),
    "Access-Control-Allow-Headers": allowedHeaders.join(", "),
    "Access-Control-Expose-Headers": exposedHeaders.join(", "),
    "Access-Control-Max-Age": String(maxAge),
  };
  if (credentials) {
    headers["Access-Control-Allow-Credentials"] = "true";
  }
  return headers;
}

/**
 * Express middleware applying a CORS policy and answering preflight requests.
 *
 * @param {object} [options] - Policy, see {@link corsHeaders}
 * @returns {Function} Express middleware
 */
export function linoCors(options = {}) {
  return (req, res, next) => {
    const headers = corsHeaders(options, req.headers.origin);
    for (const [name, value] of Object.entries(headers)) {
      res.set(name, value);
    }
    if (headers["Access-Control-Allow-Origin"] !== "*") {
      appendVary(res, "Origin");
    }
    if (
      req.method === "OPTIONS" &&
      req.headers["access-control-request-method"]
    ) {
      res.status(204).end();
      return;
    }
    next();
  };
}
