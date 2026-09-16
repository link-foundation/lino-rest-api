/**
 * RFC 9457 problem details, expressed in Links Notation (specification §5).
 */

/** Base URI every registered problem type is resolved against. */
export const PROBLEM_TYPE_BASE =
  "https://link-foundation.github.io/lino-rest-api/errors/";

const REASON_PHRASES = {
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  405: "Method Not Allowed",
  406: "Not Acceptable",
  409: "Conflict",
  410: "Gone",
  412: "Precondition Failed",
  413: "Content Too Large",
  415: "Unsupported Media Type",
  422: "Unprocessable Content",
  428: "Precondition Required",
  429: "Too Many Requests",
  500: "Internal Server Error",
  501: "Not Implemented",
  502: "Bad Gateway",
  503: "Service Unavailable",
  504: "Gateway Timeout",
};

/**
 * Reason phrase of a status code, falling back to a generic class phrase.
 *
 * @param {number} status - HTTP status code
 * @returns {string} Human readable reason phrase
 */
export function reasonPhrase(status) {
  if (REASON_PHRASES[status]) {
    return REASON_PHRASES[status];
  }
  return status >= 500 ? "Server Error" : "Request Error";
}

/**
 * Kebab-case slug used as the last segment of a problem type URI.
 *
 * @param {string} title - Problem title
 * @returns {string} Slug
 */
export function problemSlug(title) {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * An HTTP error that carries problem details.
 *
 * Throwing one of these from a handler produces a conforming error response; the
 * client library raises the same shape when a server answers with `4xx`/`5xx`.
 */
export class LinoHttpError extends Error {
  /**
   * @param {number} status - HTTP status code
   * @param {string} [detail] - Human readable explanation of this occurrence
   * @param {object} [options] - Additional problem members
   * @param {string} [options.title] - Short, type-wide summary
   * @param {string} [options.type] - Problem type URI
   * @param {string} [options.instance] - URI of this occurrence
   * @param {object} [options.headers] - Response headers to send with the error
   * @param {object} [options.extensions] - Extra problem members
   */
  constructor(status, detail, options = {}) {
    const title = options.title ?? reasonPhrase(status);
    super(detail ?? title);

    this.name = "LinoHttpError";
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.type = options.type ?? `${PROBLEM_TYPE_BASE}${problemSlug(title)}`;
    this.instance = options.instance;
    this.headers = options.headers ?? {};
    this.extensions = options.extensions ?? {};
  }

  /**
   * Render the error as the problem details object of the specification.
   *
   * @param {string} [instance] - URI of this occurrence when not already set
   * @returns {object} Problem details ready to be encoded
   */
  toProblem(instance) {
    const problem = {
      type: this.type,
      title: this.title,
      status: this.status,
    };
    if (this.detail !== undefined && this.detail !== null) {
      problem.detail = this.detail;
    }
    const resolvedInstance = this.instance ?? instance;
    if (resolvedInstance) {
      problem.instance = resolvedInstance;
    }
    return { ...problem, ...this.extensions };
  }
}

/**
 * Build problem details for a status code without throwing.
 *
 * @param {number} status - HTTP status code
 * @param {string} [detail] - Human readable explanation
 * @param {object} [options] - Additional problem members, see {@link LinoHttpError}
 * @returns {object} Problem details ready to be encoded
 */
export function problemDetails(status, detail, options = {}) {
  return new LinoHttpError(status, detail, options).toProblem(options.instance);
}

/**
 * A `422` carrying field-level validation failures.
 *
 * @param {Array<{field: string, message: string}>} errors - Field failures
 * @param {string} [detail] - Human readable explanation
 * @returns {LinoHttpError} Error ready to be thrown
 */
export function validationError(
  errors,
  detail = "Request body failed validation",
) {
  return new LinoHttpError(422, detail, {
    title: "Unprocessable Content",
    type: `${PROBLEM_TYPE_BASE}validation-failed`,
    extensions: { errors },
  });
}

/**
 * Turn any thrown value into a {@link LinoHttpError}.
 *
 * Errors that are already problem-shaped keep their status and details; anything
 * else becomes a `500` whose detail is the original message.
 *
 * @param {*} error - Thrown value
 * @returns {LinoHttpError} Normalised error
 */
export function toHttpError(error) {
  if (error instanceof LinoHttpError) {
    return error;
  }
  if (error && typeof error.status === "number" && error.status >= 400) {
    return new LinoHttpError(error.status, error.message, {
      headers: error.headers,
    });
  }
  return new LinoHttpError(500, error?.message ?? String(error));
}
