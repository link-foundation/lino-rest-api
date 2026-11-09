# lino-rest-api (JavaScript)

A REST API framework and client that speak [Links Notation](https://github.com/link-foundation/links-notation) instead of JSON.

Everything the HTTP standards expect of a REST service — content negotiation, conditional requests, problem details, collection pagination, automatic `HEAD`/`OPTIONS`/`405`, CORS, a service description and an OpenAPI document — is provided out of the box, with LINO as the default wire format and JSON as a fallback.

The wire protocol is defined in [`docs/spec/README.md`](../docs/spec/README.md); [`tests/conformance.test.js`](tests/conformance.test.js) is its executable form.

## Installation

```bash
npm install lino-rest-api
# or
bun add lino-rest-api
```

Requires Node 20+, Bun or Deno — the client is built on the platform `fetch`, so it also runs in browsers.

## Quick start

```javascript
import { createLinoApp, MemoryStore } from "lino-rest-api";

const app = createLinoApp({ title: "Tasks API", version: "1.0.0", cors: true });

const tasks = new MemoryStore();
tasks.create({ title: "Write the specification", done: true });

// Registers list, create, get, replace, merge and delete, with entity tags,
// pagination, problem details, automatic HEAD/OPTIONS and 405.
app.resource("/tasks", tasks, { name: "task" });

app.get("/health", () => ({ status: "ok" }));

app.listen(3000, () => console.log("Listening on http://localhost:3000"));
```

```bash
curl -H 'Accept: text/lino' http://localhost:3000/tasks/1
```

```lino
(
  title "Write the specification"
  done true
  id 1
)
```

A full tour — negotiation, pagination, conditional requests, problem details — is in [`examples/basic_usage.js`](examples/basic_usage.js):

```bash
npm run example
```

## The client

```javascript
import { createLinoClient } from "lino-rest-api";

const client = createLinoClient("http://localhost:3000");

const created = await client.post("/tasks", { title: "Ship it", done: false });
// → { status: 201, location: "/tasks/2", etag: '"…"', data: { … } }

const page = await client.list("/tasks", {
  done: false,
  sort: "-id",
  limit: 10,
});
// → { items: [ … ], page: { limit: 10, offset: 0, total: 1, count: 1 } }

const fresh = await client.get("/tasks/2", { ifNoneMatch: created.etag });
// → { status: 304, data: undefined }

try {
  await client.get("/tasks/999");
} catch (error) {
  error.status; // 404
  error.problem; // { type, title, status, detail, instance }
}
```

Requests are sent as `text/lino` and `Accept: text/lino, application/json;q=0.5` by default; `4xx` and `5xx` responses become a `LinoClientError` carrying the decoded problem details.

## Representations

| Media type          | Shape                                                      |
| ------------------- | ---------------------------------------------------------- |
| `text/lino`         | Readable, indented Links Notation. The default.            |
| `text/lino-line`    | The same value on a single line: `(o: (a 1))`.             |
| `text/lino-compact` | Type-tagged base64, preserving object identity and cycles. |
| `application/json`  | Fallback for clients that cannot speak LINO.               |

Errors use `application/problem+lino` (or `application/problem+json`), carrying [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details.

The response representation is chosen from `Accept`, including quality values; every response carries `Vary: Accept`, an unsatisfiable `Accept` is a `406`, and an undecodable `Content-Type` is a `415`.

## Resources

`app.resource(path, store, options)` turns any store into a full collection:

| Request             | Behaviour                                            |
| ------------------- | ---------------------------------------------------- |
| `GET /tasks`        | Envelope `{items, page}` with `Link` pagination      |
| `POST /tasks`       | `201` with `Location` and the created representation |
| `GET /tasks/:id`    | The representation, with a strong `ETag`             |
| `PUT /tasks/:id`    | Replace (optionally upsert)                          |
| `PATCH /tasks/:id`  | Merge                                                |
| `DELETE /tasks/:id` | `204`                                                |

Collection queries support `limit`, `offset`, `sort=-priority,title`, `fields=id,title` and arbitrary field filters (`?done=false&tag=a&tag=b`).

A store is any object with `list`, `get`, `create`, `update`, `patch` and `remove`; `MemoryStore` is the built-in implementation, and it may be replaced with anything that fulfils the same contract (including async database access).

Options: `name` (used in problem details), `operations` (subset of `["list", "create", "get", "update", "patch", "remove"]`), `upsert`, `requirePrecondition`.

## Conditional requests

Every representation carries a strong `ETag`: the SHA-256 of the encoded body, so the tag is per representation — the LINO and JSON forms of the same value have different tags, which is why `Vary: Accept` is always present.

- `If-None-Match` on a safe method → `304 Not Modified`
- `If-Match` that does not match → `412 Precondition Failed`
- no `If-Match` where one is required → `428 Precondition Required`

## Describing the service

| Path                        | Document                                                  |
| --------------------------- | --------------------------------------------------------- |
| `/.well-known/lino-api`     | Service description: routes, methods, media types, info   |
| `/.well-known/openapi.json` | OpenAPI 3.1, every media type declared, problem responses |

`app.describe()` and `app.openapi()` return the same documents in process.

## Handlers

A handler receives the Express request and returns a value, which is encoded as the negotiated representation:

```javascript
import { created, noContent, status, LinoHttpError } from "lino-rest-api";

app.post("/echo", (req) => ({ echoed: req.body }));
app.post("/tasks", (req) => created({ id: 7 }, "/tasks/7"));
app.delete("/tasks/:id", () => noContent());
app.get("/teapot", () => status(418, { short: true, stout: true }));

app.get("/guarded", () => {
  throw new LinoHttpError(403, "Not for you", { title: "Forbidden" });
});
```

Returning `undefined` sends `204`. Any thrown value becomes problem details; `LinoHttpError` controls the status, title, headers and extension members.

Collection queries are parsed on demand with `req.collectionQuery()`.

## API reference

Generated with JSDoc:

```bash
npm run docs
```

Key exports: `createLinoApp`, `LinoApp`, `createLinoClient`, `LinoClient`, `LinoClientError`, `MemoryStore`, `registerResource`, `LinoHttpError`, `ok`, `created`, `accepted`, `noContent`, `status`, `encode`, `decode`, `encodeFor`, `decodeFrom`, `encodeSingleLine`, `encodeCompactNotation`, `linoMiddleware`, `linoBodyParser`, `linoNegotiation`, `linoErrorHandler`, `linoCors`, `computeETag`, `evaluatePreconditions`, `parseCollectionQuery`, `applyCollectionQuery`, `collectionEnvelope`, `paginationLinkHeader`, `serviceDescription`, `openApiDocument`.

## Tests

```bash
npm test          # node --test tests/*.test.js
bun test          # the same suites under Bun
```

## License

Unlicense

## Binary transport

`application/lino-binary` carries the typed compact object AST in a
[Links Notation binary v1 packet](https://github.com/link-foundation/links-notation/blob/main/docs/protocol/binary-links-notation.md).
Use the exported `LINO_BINARY_CONTENT_TYPE` constant for both Accept and request
Content-Type. Binary bodies are bytes and have no charset parameter. Text remains
the default. JSON is independent: configure the server's supported types to
`text/lino` and `application/lino-binary` to reject JSON requests (415) and JSON
responses (406). The explicit OpenAPI JSON description route remains available.

Binary encoding and decoding enforce finite budgets: 65,536 links, 262,144
references, 65,536 expanded AST nodes, 1 MiB of expanded UTF-8 strings, and depth 64. Request bodies additionally obey `maxBodyBytes` / `max_body_bytes` (1 MiB by
default), enforced while reading. Malformed or over-budget packets receive 400;
oversized request bodies receive 413. ETags hash exact representation bytes.
Accept quality is determined by each candidate's most specific matching range,
including zero; equal qualities use the server's supported-type order.

```javascript
const app = createLinoApp({
  supported: [LINO_CONTENT_TYPE, LINO_BINARY_CONTENT_TYPE],
});
const client = new LinoClient("http://localhost:8000", {
  accept: LINO_BINARY_CONTENT_TYPE,
  contentType: LINO_BINARY_CONTENT_TYPE,
});
```

`encodeFor` returns a `Uint8Array` for binary and a string for text. `decodeFrom`
accepts the corresponding byte or string body. The fetch client reads binary
responses with `arrayBuffer()` according to response Content-Type.
