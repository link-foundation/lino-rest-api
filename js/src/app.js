/**
 * The LINO REST API application.
 *
 * Wraps Express with the behaviour the specification requires: content
 * negotiation, Links Notation bodies, problem details, automatic `HEAD`,
 * automatic `OPTIONS`, `405 Method Not Allowed` with `Allow`, and a
 * machine-readable service description.
 */

import express from "express";

import { encode, decode } from "./codec.js";
import { linoCors } from "./cors.js";
import { openApiDocument, serviceDescription } from "./description.js";
import { JSON_CONTENT_TYPE, LINO_CONTENT_TYPE } from "./media-type.js";
import { linoErrorHandler, linoMiddleware } from "./middleware.js";
import { LinoHttpError } from "./problem.js";
import { parseCollectionQuery } from "./query.js";
import { registerResource } from "./resource.js";
import { LinoResult } from "./response.js";
import { RouteTable } from "./router.js";

/** Methods a handler can be registered for. */
export const HTTP_METHODS = [
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS",
];

/** Where the native service description lives (specification §9). */
export const DESCRIPTION_PATH = "/.well-known/lino-api";

/** Where the generated OpenAPI 3.1 document lives (specification §9). */
export const OPENAPI_PATH = "/.well-known/openapi.json";

/**
 * An Express application that speaks Links Notation.
 */
export class LinoApp {
  /**
   * @param {object} [options] - Application options
   * @param {string} [options.title] - Service title used in the description
   * @param {string} [options.version] - Service version used in the description
   * @param {boolean|object} [options.cors] - Enable CORS, optionally with a policy
   * @param {boolean} [options.describe] - Serve the service description (default true)
   * @param {string[]} [options.supported] - Representations the server may produce
   * @param {number} [options.maxBodyBytes] - Largest accepted request body
   * @param {boolean} [options.exposeStack] - Attach stack traces to `5xx` problems
   * @param {number} [options.defaultLimit] - Default collection page size
   * @param {number} [options.maxLimit] - Largest collection page size
   */
  constructor(options = {}) {
    this.options = options;
    this.info = {
      title: options.title ?? "LINO REST API",
      version: options.version ?? "1.0.0",
    };
    this.routes = new RouteTable();

    this.app = express();
    this.app.disable("x-powered-by");
    this.app.disable("etag");

    if (options.cors) {
      this.app.use(linoCors(options.cors === true ? {} : options.cors));
    }
    this.app.use(linoMiddleware(options));

    // Express answers OPTIONS itself as soon as a router owns the path, with a
    // 200 and an Allow header that omits OPTIONS. Intercept it first so that
    // specification §4.1 wins.
    this.app.use(this.#options());

    // User routes live in their own router, which Express dispatches at request
    // time. Routes registered later therefore still run before the fallbacks
    // below, so the application never needs an explicit "finalize" step.
    this.router = express.Router();
    this.app.use(this.router);

    if (options.describe !== false) {
      this.#registerDescription();
    }

    this.app.use(this.#fallback());
    this.app.use(linoErrorHandler({ exposeStack: options.exposeStack }));
  }

  /**
   * Register the service description routes of specification §9.
   *
   * @returns {void}
   */
  #registerDescription() {
    this.get(DESCRIPTION_PATH, () => this.describe(), {
      summary: "Service description",
    });

    this.routes.register("GET", OPENAPI_PATH, {
      summary: "OpenAPI 3.1 description",
    });
    this.router.get(OPENAPI_PATH, (req, res) => {
      res.status(200);
      res.set("Content-Type", `${JSON_CONTENT_TYPE}; charset=utf-8`);
      res.send(`${JSON.stringify(this.openapi(), null, 2)}\n`);
    });
  }

  /**
   * Middleware answering `OPTIONS` with `Allow` (specification §4.1).
   *
   * A path with an explicitly registered `OPTIONS` handler is left to that
   * handler.
   *
   * @returns {Function} Express middleware
   */
  #options() {
    return (req, res, next) => {
      if (req.method !== "OPTIONS") {
        next();
        return;
      }
      const entry = this.routes.find(req.path);
      if (!entry || entry.methods.has("OPTIONS")) {
        next();
        return;
      }
      res.set("Allow", (this.routes.allowedMethods(req.path) ?? []).join(", "));
      res.status(204).end();
    };
  }

  /**
   * The terminal middleware answering `405` and `404`.
   *
   * @returns {Function} Express middleware
   */
  #fallback() {
    return (req, res, next) => {
      const allowed = this.routes.allowedMethods(req.path);

      if (!allowed) {
        next(new LinoHttpError(404, `No resource at ${req.path}`));
        return;
      }

      const allow = allowed.join(", ");
      next(
        new LinoHttpError(405, `${req.method} is not allowed on ${req.path}`, {
          headers: { Allow: allow },
        }),
      );
    };
  }

  /**
   * Adapt a handler that returns a value into an Express handler.
   *
   * @param {Function} handler - `(req, res) => value | LinoResult | Promise<…>`
   * @returns {Function} Express handler
   */
  #wrap(handler) {
    return async (req, res, next) => {
      try {
        req.collectionQuery = (queryOptions = {}) =>
          parseCollectionQuery(req.query, { ...this.options, ...queryOptions });

        const result = await handler(req, res);

        if (res.headersSent) {
          return;
        }
        if (result instanceof LinoResult) {
          res.lino(result.value, result.status, {
            headers: result.headers,
            ...result.options,
          });
          return;
        }
        if (result === undefined) {
          res.lino(undefined, 204);
          return;
        }
        res.lino(result);
      } catch (error) {
        next(error);
      }
    };
  }

  /**
   * Register a handler for a method and path.
   *
   * @param {string} method - HTTP method
   * @param {string} path - Path pattern
   * @param {Function} handler - Route handler
   * @param {object} [meta] - Description metadata, for example `summary`
   * @returns {LinoApp} This application, for chaining
   */
  route(method, path, handler, meta = {}) {
    const normalized = method.toUpperCase();
    if (!HTTP_METHODS.includes(normalized)) {
      throw new TypeError(`Unsupported HTTP method: ${method}`);
    }
    this.routes.register(normalized, path, meta);
    this.router[normalized.toLowerCase()](path, this.#wrap(handler));
    return this;
  }

  /**
   * Register a `GET` handler.
   *
   * @param {string} path - Path pattern
   * @param {Function} handler - Route handler
   * @param {object} [meta] - Description metadata
   * @returns {LinoApp} This application, for chaining
   */
  get(path, handler, meta) {
    return this.route("GET", path, handler, meta);
  }

  /**
   * Register a `POST` handler.
   *
   * @param {string} path - Path pattern
   * @param {Function} handler - Route handler
   * @param {object} [meta] - Description metadata
   * @returns {LinoApp} This application, for chaining
   */
  post(path, handler, meta) {
    return this.route("POST", path, handler, meta);
  }

  /**
   * Register a `PUT` handler.
   *
   * @param {string} path - Path pattern
   * @param {Function} handler - Route handler
   * @param {object} [meta] - Description metadata
   * @returns {LinoApp} This application, for chaining
   */
  put(path, handler, meta) {
    return this.route("PUT", path, handler, meta);
  }

  /**
   * Register a `PATCH` handler.
   *
   * @param {string} path - Path pattern
   * @param {Function} handler - Route handler
   * @param {object} [meta] - Description metadata
   * @returns {LinoApp} This application, for chaining
   */
  patch(path, handler, meta) {
    return this.route("PATCH", path, handler, meta);
  }

  /**
   * Register a `DELETE` handler.
   *
   * @param {string} path - Path pattern
   * @param {Function} handler - Route handler
   * @param {object} [meta] - Description metadata
   * @returns {LinoApp} This application, for chaining
   */
  delete(path, handler, meta) {
    return this.route("DELETE", path, handler, meta);
  }

  /**
   * Register a CRUD resource, see {@link registerResource}.
   *
   * @param {string} path - Collection path
   * @param {object} store - Resource store
   * @param {object} [options] - Resource options
   * @returns {LinoApp} This application, for chaining
   */
  resource(path, store, options = {}) {
    return registerResource(this, path, store, {
      defaultLimit: this.options.defaultLimit,
      maxLimit: this.options.maxLimit,
      ...options,
    });
  }

  /**
   * Add Express middleware to the user router.
   *
   * @param {...any} args - Middleware arguments
   * @returns {LinoApp} This application, for chaining
   */
  use(...args) {
    this.router.use(...args);
    return this;
  }

  /**
   * The native service description of specification §9.
   *
   * @returns {object} Description document
   */
  describe() {
    return serviceDescription(
      this.info,
      this.routes.describe(),
      this.options.supported,
    );
  }

  /**
   * The OpenAPI 3.1 rendering of the service description.
   *
   * @returns {object} OpenAPI document
   */
  openapi() {
    return openApiDocument(
      this.info,
      this.routes.describe(),
      this.options.supported,
    );
  }

  /**
   * The underlying Express application, usable as a request listener.
   *
   * @returns {object} Express application
   */
  getExpressApp() {
    return this.app;
  }

  /**
   * Start an HTTP server.
   *
   * @param {number} port - Port to listen on
   * @param {Function} [callback] - Called once the server is listening
   * @returns {object} Node HTTP server
   */
  listen(port, callback) {
    return this.app.listen(port, callback);
  }
}

/**
 * Create a new application.
 *
 * @param {object} [options] - Application options, see {@link LinoApp}
 * @returns {LinoApp} New application
 */
export function createLinoApp(options = {}) {
  return new LinoApp(options);
}

export { encode, decode, LINO_CONTENT_TYPE };
