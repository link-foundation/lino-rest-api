# lino-rest-api (Python)

A REST API framework and client that speak [Links Notation](https://github.com/link-foundation/links-notation) instead of JSON.

Everything the HTTP standards expect of a REST service — content negotiation, conditional requests, problem details, collection pagination, automatic `HEAD`/`OPTIONS`/`405`, CORS, a service description and an OpenAPI document — is provided out of the box, with LINO as the default wire format and JSON as a fallback.

The wire protocol is defined in [`docs/spec/README.md`](../docs/spec/README.md); [`tests/test_conformance.py`](tests/test_conformance.py) is its executable form. The JavaScript package speaks byte-for-byte the same wire, so the two implementations share entity tags.

## Installation

```bash
pip install lino-rest-api
```

Requires Python 3.13. The application is a plain [ASGI](https://asgi.readthedocs.io/) callable, so it runs under uvicorn, hypercorn, daphne or anything else that speaks ASGI; the client is built on [httpx](https://www.python-httpx.org/) and comes in a synchronous and an asynchronous flavour.

## Quick start

```python
from lino_rest_api import MemoryStore, create_lino_app

app = create_lino_app(title="Tasks API", version="1.0.0", cors=True)

tasks = MemoryStore()
tasks.create({"title": "Write the specification", "done": True})

# Registers list, create, get, replace, merge and delete, with entity tags,
# pagination, problem details, automatic HEAD/OPTIONS and 405.
app.resource("/tasks", tasks, name="task")

app.get("/health", lambda request: {"status": "ok"})

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```bash
curl -H 'Accept: text/lino' http://localhost:8000/tasks/1
```

```lino
(
  title "Write the specification"
  done true
  id 1
)
```

A full tour — negotiation, pagination, conditional requests, problem details — is in [`examples/basic_usage.py`](examples/basic_usage.py):

```bash
python examples/basic_usage.py
```

## The client

```python
from lino_rest_api import LinoClientError, create_lino_client

client = create_lino_client("http://localhost:8000")

created = client.post("/tasks", {"title": "Ship it", "done": False})
# → LinoResponse(status=201, location="/tasks/2", etag='"…"', data={…})

page = client.list("/tasks", {"done": False, "sort": "-id", "limit": 10})
# → {"items": [ … ], "page": {"limit": 10, "offset": 0, "total": 1, "count": 1}}

fresh = client.get("/tasks/2", if_none_match=created.etag)
# → LinoResponse(status=304, data=None)

try:
    client.get("/tasks/999")
except LinoClientError as error:
    error.status  # 404
    error.problem  # {"type": …, "title": …, "status": …, "detail": …, "instance": …}
```

`create_async_lino_client` returns the same surface with awaitable methods:

```python
async with create_async_lino_client("http://localhost:8000") as client:
    page = await client.list("/tasks", {"done": False})
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

`app.resource(path, store, **options)` turns any store into a full collection:

| Request             | Behaviour                                            |
| ------------------- | ---------------------------------------------------- |
| `GET /tasks`        | Envelope `{items, page}` with `Link` pagination      |
| `POST /tasks`       | `201` with `Location` and the created representation |
| `GET /tasks/:id`    | The representation, with a strong `ETag`             |
| `PUT /tasks/:id`    | Replace (optionally upsert)                          |
| `PATCH /tasks/:id`  | Merge                                                |
| `DELETE /tasks/:id` | `204`                                                |

Collection queries support `limit`, `offset`, `sort=-priority,title`, `fields=id,title` and arbitrary field filters (`?done=false&tag=a&tag=b`).

A store is any object with `list`, `get`, `create`, `update`, `patch` and `remove`; `MemoryStore` is the built-in implementation, and it may be replaced with anything that fulfils the same contract (including async database access — a coroutine returned by a store method is awaited).

Options: `name` (used in problem details), `operations` (subset of `["list", "create", "get", "update", "patch", "remove"]`), `upsert`, `require_precondition`.

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

A handler receives a `LinoHttpRequest` and returns a value, which is encoded as the negotiated representation:

```python
from lino_rest_api import LinoHttpError, created, no_content, status

app.post("/echo", lambda request: {"echoed": request.body})
app.post("/tasks", lambda request: created({"id": 7}, "/tasks/7"))
app.delete("/tasks/:id", lambda request: no_content())
app.get("/teapot", lambda request: status(418, {"short": True, "stout": True}))


@app.get("/guarded")
def guarded(request):
    raise LinoHttpError(403, "Not for you", title="Forbidden")
```

Handlers may be plain functions or coroutines. Returning `None` sends `204`. Any raised exception becomes problem details; `LinoHttpError` controls the status, title, headers and extension members.

The request carries `method`, `path`, `headers`, `params`, `query`, the decoded `body` and the negotiated `media_type`; collection queries are parsed on demand with `request.collection_query()`.

## FastAPI adapter

The pre-0.2 FastAPI surface (`LinoAPI`, `LinoRequest`, `LinoResponse`, `lino_request_handler`) is still exported and still works, for services that are already built on it:

```bash
pip install lino-rest-api[fastapi]
```

Those names are imported lazily, so the package works without FastAPI installed.

## API reference

Generated with [pdoc](https://pdoc.dev/):

```bash
pip install lino-rest-api[docs]
pdoc lino_rest_api -o ../docs/site/python
```

Key exports: `create_lino_app`, `LinoApp`, `create_lino_client`, `create_async_lino_client`, `LinoClient`, `AsyncLinoClient`, `LinoClientError`, `MemoryStore`, `register_resource`, `LinoHttpError`, `LinoHttpRequest`, `ok`, `created`, `accepted`, `no_content`, `status`, `raw_response`, `encode`, `decode`, `encode_for`, `decode_from`, `encode_single_line`, `encode_compact_notation`, `negotiate_request`, `decode_request_body`, `build_response`, `build_problem_response`, `compute_etag`, `evaluate_preconditions`, `parse_collection_query`, `apply_collection_query`, `collection_envelope`, `pagination_link_header`, `service_description`, `openapi_document`.

## Tests

```bash
pip install -e .[dev]
pytest tests/ -v
ruff check src tests examples
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

```python
app = create_lino_app(supported=[LINO_CONTENT_TYPE, LINO_BINARY_CONTENT_TYPE])
client = AsyncLinoClient("http://localhost:8000",
                        accept=LINO_BINARY_CONTENT_TYPE,
                        content_type=LINO_BINARY_CONTENT_TYPE)
```

`encode_for` returns `bytes` for binary and `str` for text; `decode_from` accepts
bytes for binary. Sync and async clients both consume response bytes. Standalone
FastAPI `LinoRequest` recognizes binary; `LinoResponse(...,
media_type=LINO_BINARY_CONTENT_TYPE)` emits it.
