/**
 * Machine-readable service description (specification §9).
 *
 * The same route registry is rendered twice: once as the native Links Notation
 * description served at `/.well-known/lino-api`, and once as an OpenAPI 3.1
 * document served at `/.well-known/openapi.json` so that existing tooling keeps
 * working against a LINO API.
 */

import { SUPPORTED_MEDIA_TYPES } from "./media-type.js";

/** Version of the description document this package emits. */
export const LINO_API_DESCRIPTION_VERSION = "1.0";

/**
 * Build the native service description.
 *
 * @param {object} info - `title` and `version` of the service
 * @param {Array<{path: string, methods: string[], summary: string}>} routes - Route descriptions
 * @param {string[]} [mediaTypes] - Representations the service can produce
 * @returns {object} Description ready to be encoded as Links Notation
 */
export function serviceDescription(
  info,
  routes,
  mediaTypes = SUPPORTED_MEDIA_TYPES,
) {
  return {
    lino_api: LINO_API_DESCRIPTION_VERSION,
    info: { title: info.title, version: info.version },
    media_types: [...mediaTypes],
    routes,
  };
}

/**
 * Convert an Express-style path to the OpenAPI template syntax.
 *
 * @param {string} path - Path pattern with `:param` segments
 * @returns {string} Path template with `{param}` segments
 */
export function toOpenApiPath(path) {
  return path.replace(/:([A-Za-z0-9_]+)/g, "{$1}");
}

/**
 * Extract the path parameters of an Express-style path.
 *
 * @param {string} path - Path pattern
 * @returns {string[]} Parameter names
 */
export function pathParameters(path) {
  return [...path.matchAll(/:([A-Za-z0-9_]+)/g)].map((match) => match[1]);
}

const LINO_SCHEMA = {
  description:
    "Links Notation document, see https://github.com/link-foundation/links-notation",
  type: "string",
};

/**
 * Build an OpenAPI 3.1 document describing the service.
 *
 * Every request and response body is declared for all negotiable media types, so
 * that a generated client knows it may ask for `text/lino`.
 *
 * @param {object} info - `title` and `version` of the service
 * @param {Array<{path: string, methods: string[], summary: string}>} routes - Route descriptions
 * @param {string[]} [mediaTypes] - Representations the service can produce
 * @returns {object} OpenAPI 3.1 document
 */
export function openApiDocument(
  info,
  routes,
  mediaTypes = SUPPORTED_MEDIA_TYPES,
) {
  const content = Object.fromEntries(
    mediaTypes.map((mediaType) => [mediaType, { schema: LINO_SCHEMA }]),
  );

  const paths = {};
  for (const route of routes) {
    const template = toOpenApiPath(route.path);
    const parameters = pathParameters(route.path).map((name) => ({
      name,
      in: "path",
      required: true,
      schema: { type: "string" },
    }));

    paths[template] = {};
    for (const method of route.methods) {
      const operation = {
        summary: route.summary ?? `${method} ${route.path}`,
        responses: {
          200: { description: "Success", content },
          default: {
            description: "RFC 9457 problem details in Links Notation",
            content,
          },
        },
      };
      if (parameters.length > 0) {
        operation.parameters = parameters;
      }
      if (["POST", "PUT", "PATCH"].includes(method)) {
        operation.requestBody = { required: true, content };
      }
      paths[template][method.toLowerCase()] = operation;
    }
  }

  return {
    openapi: "3.1.0",
    info: { title: info.title, version: info.version },
    paths,
  };
}
