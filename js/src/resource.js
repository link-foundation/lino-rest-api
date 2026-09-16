/**
 * CRUD resource registration.
 *
 * Turns a store object into the six routes the specification describes for a
 * collection and its items, including pagination `Link` headers (§6.1),
 * entity tags and conditional requests (§7).
 */

import { applyCollectionQuery, paginationLinkHeader } from "./collection.js";
import { encodeFor } from "./codec.js";
import { computeETag, evaluatePreconditions } from "./etag.js";
import { LINO_CONTENT_TYPE } from "./media-type.js";
import { LinoHttpError } from "./problem.js";
import { parseCollectionQuery } from "./query.js";
import { created, LinoResult, noContent } from "./response.js";

/** Operations a resource can expose, in registration order. */
export const RESOURCE_OPERATIONS = [
  "list",
  "create",
  "get",
  "update",
  "patch",
  "remove",
];

/**
 * Entity tag of a value in the representation the client asked for.
 *
 * Entity tags are per representation, which is why the negotiated media type is
 * part of the computation and why every response carries `Vary: Accept`.
 *
 * @param {object} req - Express request
 * @param {*} value - Value to tag
 * @returns {string} Quoted entity tag
 */
export function representationETag(req, value) {
  return computeETag(encodeFor(value, req.linoMediaType ?? LINO_CONTENT_TYPE));
}

/**
 * Build the `404` raised when an item does not exist.
 *
 * @param {string} name - Human readable resource name
 * @param {*} id - Identifier that was looked up
 * @returns {LinoHttpError} Problem to throw
 */
function notFound(name, id) {
  return new LinoHttpError(404, `${name} ${id} does not exist`);
}

/**
 * Require a decoded request body.
 *
 * @param {object} req - Express request
 * @returns {object} The body
 * @throws {LinoHttpError} `400` when the body is missing
 */
function requireBody(req) {
  if (req.body === undefined || req.body === null) {
    throw new LinoHttpError(400, "A request body is required");
  }
  return req.body;
}

/**
 * Normalise whatever a store's `list` returned into a collection envelope.
 *
 * @param {*} result - Array of items, or an envelope
 * @param {object} query - Parsed collection query
 * @returns {{items: object[], page: object}} Collection envelope
 */
function toEnvelope(result, query) {
  if (Array.isArray(result)) {
    return applyCollectionQuery(result, query);
  }
  return result;
}

/**
 * Register the routes of a CRUD resource on an application.
 *
 * @param {object} app - {@link LinoApp} to register on
 * @param {string} basePath - Collection path, for example `/items`
 * @param {object} store - Store implementing `list`, `get`, `create`, `update`, `patch` and `remove`
 * @param {object} [options] - Resource options
 * @param {string} [options.idParam] - Path parameter holding the identifier
 * @param {string} [options.idField] - Field of an item holding the identifier
 * @param {string} [options.name] - Human readable name used in problem details
 * @param {string[]} [options.operations] - Subset of {@link RESOURCE_OPERATIONS} to expose
 * @param {boolean} [options.requirePrecondition] - Demand `If-Match` on `PUT`, `PATCH` and `DELETE`
 * @param {boolean} [options.upsert] - Let `PUT` create a missing item
 * @param {number} [options.defaultLimit] - Page size when unspecified
 * @param {number} [options.maxLimit] - Largest accepted page size
 * @returns {object} The application, for chaining
 */
export function registerResource(app, basePath, store, options = {}) {
  const idParam = options.idParam ?? "id";
  const idField = options.idField ?? store.idField ?? "id";
  const name = options.name ?? basePath.replace(/^\//, "").replace(/\/$/, "");
  const operations = options.operations ?? RESOURCE_OPERATIONS;
  const itemPath = `${basePath}/:${idParam}`;

  /**
   * Read the current item and evaluate `If-Match` against it before mutating.
   *
   * @param {object} req - Express request
   * @returns {Promise<*>} The current item, or undefined when absent
   */
  const loadForWrite = async (req) => {
    const id = req.params[idParam];
    const existing = await store.get(id);
    if (existing === undefined || existing === null) {
      return undefined;
    }
    evaluatePreconditions(
      req.headers,
      req.method,
      representationETag(req, existing),
      { requirePrecondition: options.requirePrecondition },
    );
    return existing;
  };

  const handlers = {
    list: () =>
      app.get(
        basePath,
        async (req) => {
          const query = parseCollectionQuery(req.query, options);
          const envelope = toEnvelope(await store.list(query), query);
          const link = paginationLinkHeader(req.path, req.query, {
            limit: envelope.page.limit,
            offset: envelope.page.offset,
            total: envelope.page.total,
          });
          return new LinoResult(envelope, 200, link ? { Link: link } : {});
        },
        { summary: `List ${name}` },
      ),

    create: () =>
      app.post(
        basePath,
        async (req) => {
          const item = await store.create(requireBody(req));
          const id = item?.[idField];
          const location =
            id === undefined
              ? undefined
              : `${basePath}/${encodeURIComponent(String(id))}`;
          return created(item, location);
        },
        { summary: `Create ${name}` },
      ),

    get: () =>
      app.get(
        itemPath,
        async (req) => {
          const item = await store.get(req.params[idParam]);
          if (item === undefined || item === null) {
            throw notFound(name, req.params[idParam]);
          }
          return item;
        },
        { summary: `Read one ${name}` },
      ),

    update: () =>
      app.put(
        itemPath,
        async (req) => {
          const body = requireBody(req);
          const existing = await loadForWrite(req);
          if (existing === undefined) {
            if (!options.upsert) {
              throw notFound(name, req.params[idParam]);
            }
            const item = await store.create({
              ...body,
              [idField]: req.params[idParam],
            });
            return created(
              item,
              `${basePath}/${encodeURIComponent(String(item?.[idField]))}`,
            );
          }
          return store.update(req.params[idParam], body);
        },
        { summary: `Replace one ${name}` },
      ),

    patch: () =>
      app.patch(
        itemPath,
        async (req) => {
          const body = requireBody(req);
          const existing = await loadForWrite(req);
          if (existing === undefined) {
            throw notFound(name, req.params[idParam]);
          }
          return store.patch(req.params[idParam], body);
        },
        { summary: `Merge changes into one ${name}` },
      ),

    remove: () =>
      app.delete(
        itemPath,
        async (req) => {
          const existing = await loadForWrite(req);
          if (existing === undefined) {
            throw notFound(name, req.params[idParam]);
          }
          await store.remove(req.params[idParam]);
          return noContent();
        },
        { summary: `Delete one ${name}` },
      ),
  };

  for (const operation of RESOURCE_OPERATIONS) {
    if (operations.includes(operation)) {
      handlers[operation]();
    }
  }

  return app;
}
