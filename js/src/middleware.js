/**
 * Express middleware implementing the request and response halves of the
 * specification: body decoding (§2.1), content negotiation (§2.1), entity tags
 * (§7) and problem details (§5).
 */

import { decodeFrom, encodeFor } from "./codec.js";
import {
  LINO_CONTENT_TYPE,
  SUPPORTED_MEDIA_TYPES,
  isDecodableMediaType,
  negotiateMediaType,
  parseContentType,
  problemMediaType,
  withCharset,
} from "./media-type.js";
import { LinoHttpError, toHttpError } from "./problem.js";
import { computeETag, evaluatePreconditions } from "./etag.js";
import { appendVary } from "./headers.js";

export {
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  JSON_CONTENT_TYPE,
  LINO_PROBLEM_CONTENT_TYPE,
  JSON_PROBLEM_CONTENT_TYPE,
} from "./media-type.js";

/** Largest request body accepted by default, in bytes. */
export const DEFAULT_MAX_BODY_BYTES = 1024 * 1024;

/**
 * Read a request body as a UTF-8 string, refusing oversized payloads.
 *
 * @param {object} req - Express request
 * @param {number} maxBytes - Largest accepted body
 * @returns {Promise<string>} Raw body
 */
function readBody(req, maxBytes) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    let settled = false;

    const finish = (callback, value) => {
      if (settled) {
        return;
      }
      settled = true;
      callback(value);
    };

    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > maxBytes) {
        // Stop reading but leave the socket alive, otherwise the client never
        // sees the 413 it is being told about.
        req.unpipe?.();
        req.pause();
        finish(
          reject,
          new LinoHttpError(413, `Request body exceeds ${maxBytes} bytes`, {
            headers: { Connection: "close" },
          }),
        );
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () =>
      finish(resolve, Buffer.concat(chunks).toString("utf-8")),
    );
    req.on("error", (error) => finish(reject, error));
  });
}

/**
 * Body parser middleware for every media type of the specification.
 *
 * Decoded bodies are exposed as `req.body`; the media type they arrived in is
 * exposed as `req.linoRequestMediaType`.
 *
 * @param {object} [options] - Limits
 * @param {number} [options.maxBodyBytes] - Largest accepted body
 * @returns {Function} Express middleware
 */
export function linoBodyParser(options = {}) {
  const maxBytes = options.maxBodyBytes ?? DEFAULT_MAX_BODY_BYTES;

  return async (req, res, next) => {
    if (req.method === "GET" || req.method === "HEAD") {
      req.body = undefined;
      next();
      return;
    }

    const mediaType = parseContentType(req.headers["content-type"]);
    if (!mediaType) {
      req.body = undefined;
      next();
      return;
    }

    if (!isDecodableMediaType(mediaType)) {
      next(
        new LinoHttpError(415, `Unsupported request media type: ${mediaType}`, {
          extensions: { supported: SUPPORTED_MEDIA_TYPES },
        }),
      );
      return;
    }

    try {
      const raw = await readBody(req, maxBytes);
      req.linoRequestMediaType = mediaType;
      req.body = raw.trim() ? decodeFrom(raw, mediaType) : undefined;
      next();
    } catch (error) {
      if (error instanceof LinoHttpError) {
        next(error);
        return;
      }
      next(
        new LinoHttpError(
          400,
          `Malformed ${mediaType} request body: ${error.message}`,
        ),
      );
    }
  };
}

/**
 * Content negotiation middleware.
 *
 * Stores the selected representation on `req.linoMediaType` and installs the
 * `res.lino(...)` and `res.problem(...)` helpers.
 *
 * @param {object} [options] - Negotiation policy
 * @param {string[]} [options.supported] - Representations the server can produce
 * @returns {Function} Express middleware
 */
export function linoNegotiation(options = {}) {
  const supported = options.supported ?? SUPPORTED_MEDIA_TYPES;

  return (req, res, next) => {
    const selected = negotiateMediaType(req.headers.accept, supported);
    appendVary(res, "Accept");

    if (!selected) {
      next(
        new LinoHttpError(
          406,
          `No acceptable representation for Accept: ${req.headers.accept}`,
          { extensions: { supported } },
        ),
      );
      return;
    }

    req.linoMediaType = selected;

    /**
     * Send a value as the negotiated representation.
     *
     * @param {*} value - Value to encode
     * @param {number} [statusCode] - HTTP status code
     * @param {object} [sendOptions] - Response options
     * @param {object} [sendOptions.headers] - Extra response headers
     * @param {boolean} [sendOptions.etag] - Emit an `ETag` (default true)
     * @param {boolean} [sendOptions.preconditions] - Evaluate conditional headers (default: safe methods only)
     * @param {boolean} [sendOptions.requirePrecondition] - Demand `If-Match` on unsafe methods
     * @returns {object} The Express response
     */
    res.lino = (value, statusCode = 200, sendOptions = {}) => {
      for (const [name, headerValue] of Object.entries(
        sendOptions.headers ?? {},
      )) {
        res.set(name, headerValue);
      }

      if (statusCode === 204 || value === undefined) {
        res.status(statusCode === 200 ? 204 : statusCode);
        return res.end();
      }

      const body = encodeFor(value, selected);

      if (sendOptions.etag !== false) {
        const etag = computeETag(body);
        res.set("ETag", etag);

        // Preconditions on unsafe methods have to be evaluated against the
        // *current* representation before the change is applied, which only the
        // route handler can do; here the body is already the new representation.
        const safe = req.method === "GET" || req.method === "HEAD";
        if (sendOptions.preconditions ?? safe) {
          const { notModified } = evaluatePreconditions(
            req.headers,
            req.method,
            etag,
            { requirePrecondition: sendOptions.requirePrecondition },
          );
          if (notModified) {
            res.status(304);
            return res.end();
          }
        }
      }

      res.status(statusCode);
      res.set("Content-Type", withCharset(selected));
      return res.send(body);
    };

    /**
     * Send problem details for an error.
     *
     * @param {*} error - Thrown value or {@link LinoHttpError}
     * @returns {object} The Express response
     */
    res.problem = (error) => sendProblem(req, res, error);

    next();
  };
}

/**
 * Write problem details for an error onto a response.
 *
 * @param {object} req - Express request
 * @param {object} res - Express response
 * @param {*} error - Thrown value
 * @returns {object} The Express response
 */
export function sendProblem(req, res, error) {
  const httpError = toHttpError(error);
  const mediaType = req.linoMediaType ?? LINO_CONTENT_TYPE;
  const problem = httpError.toProblem(req.originalUrl ?? req.url);

  for (const [name, value] of Object.entries(httpError.headers ?? {})) {
    res.set(name, value);
  }

  res.status(httpError.status);
  appendVary(res, "Accept");
  res.set("Content-Type", withCharset(problemMediaType(mediaType)));

  if (req.method === "HEAD") {
    return res.end();
  }
  return res.send(encodeFor(problem, mediaType));
}

/**
 * Terminal error handler turning any thrown value into problem details.
 *
 * @param {object} [options] - Behaviour switches
 * @param {boolean} [options.exposeStack] - Attach the stack trace to `5xx` problems
 * @returns {Function} Express error middleware
 */
export function linoErrorHandler(options = {}) {
  return (error, req, res, next) => {
    if (res.headersSent) {
      next(error);
      return;
    }
    const httpError = toHttpError(error);
    if (options.exposeStack && httpError.status >= 500 && error?.stack) {
      httpError.extensions = { ...httpError.extensions, stack: error.stack };
    }
    sendProblem(req, res, httpError);
  };
}

/**
 * The full request pipeline: negotiation followed by body decoding.
 *
 * @param {object} [options] - Options forwarded to the individual middleware
 * @returns {Function[]} Express middleware chain
 */
export function linoMiddleware(options = {}) {
  const negotiation = linoNegotiation(options);
  const bodyParser = linoBodyParser(options);

  return (req, res, next) => {
    negotiation(req, res, (negotiationError) => {
      if (negotiationError) {
        next(negotiationError);
        return;
      }
      bodyParser(req, res, next);
    });
  };
}

/**
 * Send a value as Links Notation without the negotiation middleware.
 *
 * @param {object} res - Express response
 * @param {*} value - Value to encode
 * @param {number} [statusCode] - HTTP status code
 * @returns {object} The Express response
 */
export function linoResponse(res, value, statusCode = 200) {
  res.status(statusCode);
  res.set("Content-Type", withCharset(LINO_CONTENT_TYPE));
  return res.send(encodeFor(value, LINO_CONTENT_TYPE));
}
