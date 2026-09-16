/**
 * Links Notation REST client (specification §10).
 *
 * Built on the platform `fetch`, so the same module runs on Node, Bun, Deno and
 * in browsers.
 */

import { decodeFrom, encodeFor } from "./codec.js";
import {
  JSON_CONTENT_TYPE,
  LINO_CONTENT_TYPE,
  isDecodableMediaType,
  parseContentType,
  withCharset,
} from "./media-type.js";

/** Default `Accept` sent by the client: LINO first, JSON as a fallback. */
export const DEFAULT_ACCEPT = `${LINO_CONTENT_TYPE}, ${JSON_CONTENT_TYPE};q=0.5`;

/**
 * Error raised for any `4xx` or `5xx`, carrying the decoded problem details.
 */
export class LinoClientError extends Error {
  /**
   * @param {number} status - HTTP status code
   * @param {*} problem - Decoded problem details, when the body could be decoded
   * @param {object} [response] - The `Response` that produced this error
   */
  constructor(status, problem, response) {
    const detail =
      (problem && (problem.detail || problem.title)) ||
      `Request failed with status ${status}`;
    super(detail);
    this.name = "LinoClientError";
    this.status = status;
    this.problem = problem;
    this.response = response;
  }
}

/**
 * Build a query string from an object, expanding array values.
 *
 * @param {object} [query] - Query parameters
 * @returns {string} Query string including `?`, or an empty string
 */
export function buildQueryString(query) {
  if (!query) {
    return "";
  }
  const parameters = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value === undefined || value === null) {
      continue;
    }
    for (const item of Array.isArray(value) ? value : [value]) {
      parameters.append(name, String(item));
    }
  }
  const encoded = parameters.toString();
  return encoded ? `?${encoded}` : "";
}

/**
 * A client for a service that speaks Links Notation.
 */
export class LinoClient {
  /**
   * @param {string} baseUrl - Base URL of the service
   * @param {object} [options] - Client options
   * @param {string} [options.accept] - `Accept` header sent with every request
   * @param {string} [options.contentType] - Representation used for request bodies
   * @param {object} [options.headers] - Headers sent with every request
   * @param {Function} [options.fetch] - `fetch` implementation to use
   */
  constructor(baseUrl, options = {}) {
    this.baseUrl = String(baseUrl).replace(/\/$/, "");
    this.accept = options.accept ?? DEFAULT_ACCEPT;
    this.contentType = options.contentType ?? LINO_CONTENT_TYPE;
    this.headers = options.headers ?? {};
    this.fetch = options.fetch ?? globalThis.fetch;
    if (typeof this.fetch !== "function") {
      throw new TypeError("No fetch implementation available");
    }
  }

  /**
   * Perform a request and decode the response.
   *
   * @param {string} method - HTTP method
   * @param {string} path - Path, appended to the base URL
   * @param {object} [options] - Request options
   * @param {*} [options.body] - Value to encode as the request body
   * @param {object} [options.query] - Query parameters
   * @param {object} [options.headers] - Extra request headers
   * @param {string} [options.accept] - Override the `Accept` header
   * @param {string} [options.ifMatch] - `If-Match` precondition
   * @param {string} [options.ifNoneMatch] - `If-None-Match` precondition
   * @param {AbortSignal} [options.signal] - Abort signal
   * @returns {Promise<{status: number, headers: Headers, data: *, etag: string|null, location: string|null, response: Response}>} Decoded response
   * @throws {LinoClientError} For any `4xx` or `5xx` response
   */
  async request(method, path, options = {}) {
    const url = `${this.baseUrl}${path}${buildQueryString(options.query)}`;
    const headers = {
      Accept: options.accept ?? this.accept,
      ...this.headers,
      ...options.headers,
    };

    if (options.ifMatch) {
      headers["If-Match"] = options.ifMatch;
    }
    if (options.ifNoneMatch) {
      headers["If-None-Match"] = options.ifNoneMatch;
    }

    let body;
    if (options.body !== undefined) {
      body = encodeFor(options.body, this.contentType);
      headers["Content-Type"] = withCharset(this.contentType);
    }

    const response = await this.fetch(url, {
      method,
      headers,
      body,
      signal: options.signal,
    });

    const data = await this.#decodeBody(response, method);

    if (!response.ok && response.status !== 304) {
      throw new LinoClientError(response.status, data, response);
    }

    return {
      status: response.status,
      headers: response.headers,
      data,
      etag: response.headers.get("etag"),
      location: response.headers.get("location"),
      response,
    };
  }

  /**
   * Decode a response body according to its own `Content-Type` (§10).
   *
   * @param {object} response - Fetch response
   * @param {string} method - Request method
   * @returns {Promise<*>} Decoded value, or undefined when there is no body
   */
  async #decodeBody(response, method) {
    if (
      response.status === 204 ||
      response.status === 304 ||
      method === "HEAD"
    ) {
      return undefined;
    }

    const text = await response.text();
    if (text === "") {
      return undefined;
    }

    const mediaType = parseContentType(response.headers.get("content-type"));
    if (!isDecodableMediaType(mediaType)) {
      return text;
    }
    try {
      return decodeFrom(text, mediaType);
    } catch {
      return text;
    }
  }

  /**
   * `GET` a resource.
   *
   * @param {string} path - Path
   * @param {object} [options] - Request options
   * @returns {Promise<object>} Decoded response
   */
  get(path, options) {
    return this.request("GET", path, options);
  }

  /**
   * `POST` to a collection.
   *
   * @param {string} path - Path
   * @param {*} body - Value to send
   * @param {object} [options] - Request options
   * @returns {Promise<object>} Decoded response
   */
  post(path, body, options = {}) {
    return this.request("POST", path, { ...options, body });
  }

  /**
   * `PUT` a representation.
   *
   * @param {string} path - Path
   * @param {*} body - Value to send
   * @param {object} [options] - Request options
   * @returns {Promise<object>} Decoded response
   */
  put(path, body, options = {}) {
    return this.request("PUT", path, { ...options, body });
  }

  /**
   * `PATCH` a representation.
   *
   * @param {string} path - Path
   * @param {*} body - Value to send
   * @param {object} [options] - Request options
   * @returns {Promise<object>} Decoded response
   */
  patch(path, body, options = {}) {
    return this.request("PATCH", path, { ...options, body });
  }

  /**
   * `DELETE` a resource.
   *
   * @param {string} path - Path
   * @param {object} [options] - Request options
   * @returns {Promise<object>} Decoded response
   */
  delete(path, options) {
    return this.request("DELETE", path, options);
  }

  /**
   * `HEAD` a resource.
   *
   * @param {string} path - Path
   * @param {object} [options] - Request options
   * @returns {Promise<object>} Decoded response
   */
  head(path, options) {
    return this.request("HEAD", path, options);
  }

  /**
   * `OPTIONS` a path, returning the advertised methods.
   *
   * @param {string} path - Path
   * @param {object} [options] - Request options
   * @returns {Promise<string[]>} Methods listed in `Allow`
   */
  async options(path, options) {
    const response = await this.request("OPTIONS", path, options);
    return (response.headers.get("allow") ?? "")
      .split(",")
      .map((method) => method.trim())
      .filter(Boolean);
  }

  /**
   * List a collection, returning the decoded envelope.
   *
   * @param {string} path - Collection path
   * @param {object} [query] - Collection query parameters
   * @param {object} [options] - Request options
   * @returns {Promise<{items: object[], page: object}>} Collection envelope
   */
  async list(path, query, options = {}) {
    const response = await this.request("GET", path, { ...options, query });
    return response.data;
  }

  /**
   * Fetch the service description of specification §9.
   *
   * @returns {Promise<object>} Description document
   */
  async describe() {
    const response = await this.get("/.well-known/lino-api");
    return response.data;
  }
}

/**
 * Create a client.
 *
 * @param {string} baseUrl - Base URL of the service
 * @param {object} [options] - Client options, see {@link LinoClient}
 * @returns {LinoClient} New client
 */
export function createLinoClient(baseUrl, options = {}) {
  return new LinoClient(baseUrl, options);
}
