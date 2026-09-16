/**
 * lino-rest-api — a REST API framework that speaks Links Notation instead of JSON.
 *
 * The public surface follows the LINO REST API specification shipped in
 * `docs/spec/README.md`: content negotiation, problem details, collections,
 * conditional requests, CORS and a machine-readable service description.
 */

export {
  createLinoApp,
  LinoApp,
  HTTP_METHODS,
  DESCRIPTION_PATH,
  OPENAPI_PATH,
} from "./app.js";

export {
  createLinoClient,
  LinoClient,
  LinoClientError,
  buildQueryString,
  DEFAULT_ACCEPT,
} from "./client.js";

export {
  encode,
  decode,
  encodeSingleLine,
  decodeSingleLine,
  encodeCompactNotation,
  encodeFor,
  decodeFrom,
  CircularReferenceError,
} from "./codec.js";

export {
  LINO_CONTENT_TYPE,
  LINO_LINE_CONTENT_TYPE,
  LINO_COMPACT_CONTENT_TYPE,
  LINO_PROBLEM_CONTENT_TYPE,
  JSON_CONTENT_TYPE,
  SUPPORTED_MEDIA_TYPES,
  negotiateMediaType,
  parseAccept,
  parseContentType,
  isDecodableMediaType,
  withCharset,
} from "./media-type.js";

export {
  linoMiddleware,
  linoBodyParser,
  linoNegotiation,
  linoErrorHandler,
  linoResponse,
  sendProblem,
  DEFAULT_MAX_BODY_BYTES,
} from "./middleware.js";

export {
  LinoHttpError,
  PROBLEM_TYPE_BASE,
  problemDetails,
  problemSlug,
  reasonPhrase,
  toHttpError,
  validationError,
} from "./problem.js";

export {
  LinoResult,
  ok,
  created,
  accepted,
  noContent,
  status,
} from "./response.js";

export {
  parseCollectionQuery,
  parseFields,
  parseScalar,
  parseSort,
  DEFAULT_LIMIT,
  MAX_LIMIT,
  RESERVED_QUERY_PARAMETERS,
} from "./query.js";

export {
  applyCollectionQuery,
  collectionEnvelope,
  matchesFilters,
  paginationLinkHeader,
  projectFields,
  sortItems,
} from "./collection.js";

export {
  computeETag,
  etagMatches,
  evaluatePreconditions,
  parseETagList,
} from "./etag.js";

export {
  corsHeaders,
  linoCors,
  DEFAULT_ALLOWED_HEADERS,
  DEFAULT_EXPOSED_HEADERS,
} from "./cors.js";

export { appendVary } from "./headers.js";

export { compilePathPattern, RouteTable, IMPLICIT_METHODS } from "./router.js";

export {
  infoObject,
  openApiDocument,
  pathParameters,
  serviceDescription,
  toOpenApiPath,
  LINO_API_DESCRIPTION_VERSION,
} from "./description.js";

export {
  registerResource,
  representationETag,
  RESOURCE_OPERATIONS,
} from "./resource.js";

export { MemoryStore } from "./store.js";
