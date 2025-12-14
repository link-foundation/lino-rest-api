/**
 * Express middleware for Links Notation (LINO) format.
 *
 * Provides request body parsing and response formatting using LINO
 * instead of JSON.
 */

import { encode, decode } from "./vendor/codec.js";

/**
 * Content type for Links Notation format.
 */
export const LINO_CONTENT_TYPE = "text/lino";

/**
 * Body parser middleware for Links Notation format.
 *
 * Parses incoming request bodies in LINO format and makes the decoded
 * JavaScript object available as `req.body`.
 *
 * @returns {Function} Express middleware function
 */
export function linoBodyParser() {
  return async (req, res, next) => {
    // Only parse if content-type is LINO
    const contentType = req.headers["content-type"] || "";
    if (!contentType.includes(LINO_CONTENT_TYPE)) {
      return next();
    }

    let body = "";

    req.on("data", (chunk) => {
      body += chunk.toString();
    });

    req.on("end", () => {
      try {
        if (body.trim()) {
          req.body = decode(body);
        } else {
          req.body = null;
        }
        next();
      } catch (err) {
        res.status(400);
        res.set("Content-Type", LINO_CONTENT_TYPE);
        res.send(
          encode({ error: "Invalid LINO format", message: err.message }),
        );
      }
    });

    req.on("error", (err) => {
      res.status(500);
      res.set("Content-Type", LINO_CONTENT_TYPE);
      res.send(encode({ error: "Request error", message: err.message }));
    });
  };
}

/**
 * Response helper for sending LINO-formatted responses.
 *
 * @param {object} res - Express response object
 * @param {*} data - Data to encode and send
 * @param {number} [statusCode=200] - HTTP status code
 */
export function linoResponse(res, data, statusCode = 200) {
  res.status(statusCode);
  res.set("Content-Type", LINO_CONTENT_TYPE);
  res.send(encode(data));
}

/**
 * Combined middleware that sets up LINO parsing and adds helper methods.
 *
 * Adds `res.lino(data, statusCode)` helper method for easy LINO responses.
 *
 * @returns {Function} Express middleware function
 */
export function linoMiddleware() {
  const bodyParser = linoBodyParser();

  return (req, res, next) => {
    // Add lino response helper
    res.lino = (data, statusCode = 200) => {
      linoResponse(res, data, statusCode);
    };

    // Apply body parser
    bodyParser(req, res, next);
  };
}
