# lino-rest-api (Rust)

A REST API framework and client that speak [Links Notation](https://github.com/link-foundation/links-notation) instead of JSON.

Everything the HTTP standards expect of a REST service — content negotiation, conditional requests, problem details, collection pagination, automatic `HEAD`/`OPTIONS`/`405`, CORS, a service description and an OpenAPI document — is provided out of the box, with LINO as the default wire format and JSON as a fallback.

The wire protocol is defined in [`docs/spec/README.md`](../docs/spec/README.md); [`tests/conformance.rs`](tests/conformance.rs) is its executable form. The JavaScript and Python packages speak byte-for-byte the same wire — [`tests/codec_parity.rs`](tests/codec_parity.rs) runs the shared cross-language fixtures — so the three implementations share entity tags.

## Installation

```bash
cargo add lino-rest-api
```

Requires Rust 1.85 (edition 2024). The server shell is built on [axum](https://github.com/tokio-rs/axum) and the client on [reqwest](https://github.com/seanmonstar/reqwest); the application itself is a plain request handler, so it can also be driven in process, without a socket.

## Quick start

```rust
use std::sync::Arc;

use lino_rest_api::{
    MemoryStore, ResourceOptions, ServiceInfo, boolean, create_lino_app, object, serve, string,
};

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let mut app = create_lino_app().with_info(ServiceInfo::new("Tasks API", "1.0.0"));

    let tasks = Arc::new(MemoryStore::seeded([object([
        ("title", string("Write the specification")),
        ("done", boolean(true)),
    ])]));

    // Registers list, create, get, replace, merge and delete, with entity tags,
    // pagination, problem details, automatic HEAD/OPTIONS and 405.
    app.resource("/tasks", tasks, ResourceOptions::new().with_name("task"));

    app.get_fn("/health", "Liveness probe", |_request| {
        Ok(object([("status", string("ok"))]))
    });

    serve(app, "0.0.0.0:8000").await
}
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

That service is [`examples/server.rs`](examples/server.rs):

```bash
cargo run --example server
```

A full tour — negotiation, pagination, conditional requests, problem details — is in [`examples/basic_usage.rs`](examples/basic_usage.rs), which starts a server on an ephemeral port and drives it through the client:

```bash
cargo run --example basic_usage
```

## The client

```rust
use lino_rest_api::{LinoClient, RequestOptions, boolean, int, object, string};

let client = LinoClient::new("http://localhost:8000");
let plain = RequestOptions::new;

let created = client
    .post(
        "/tasks",
        &object([("title", string("Ship it")), ("done", boolean(false))]),
        &plain(),
    )
    .await?;
// → status 201, location "/tasks/2", etag "\"…\"", data Some(…)

let page = client
    .list(
        "/tasks",
        &plain()
            .with_query("done", &boolean(false))
            .with_query_text("sort", "-id")
            .with_query("limit", &int(10)),
    )
    .await?;
// → (items ( … ) page (limit 10 offset 0 total 1 count 1))

let fresh = client
    .get("/tasks/2", &plain().if_none_match(created.etag.unwrap()))
    .await?;
// → status 304, data None

match client.get("/tasks/999", &plain()).await {
    Err(error) => {
        error.status(); // Some(404)
        error.problem(); // Some((type … title … status … detail … instance …))
    }
    Ok(_) => unreachable!(),
}
```

Requests are sent as `text/lino` and `Accept: text/lino, application/json;q=0.5` by default; `4xx` and `5xx` responses become a `LinoClientError::Status` carrying the decoded problem details, and `Display` renders the `detail` member, so `error.to_string()` is the message the service sent.

`with_accept`, `with_content_type`, `with_header` and `with_http_client` configure a client; `RequestOptions` carries what a single call adds.

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
| `GET /tasks`        | Envelope `(items … page …)` with `Link` pagination   |
| `POST /tasks`       | `201` with `Location` and the created representation |
| `GET /tasks/:id`    | The representation, with a strong `ETag`             |
| `PUT /tasks/:id`    | Replace (optionally upsert)                          |
| `PATCH /tasks/:id`  | Merge                                                |
| `DELETE /tasks/:id` | `204`                                                |

Collection queries support `limit`, `offset`, `sort=-priority,title`, `fields=id,title` and arbitrary field filters (`?done=false&tag=a&tag=b`).

A store is anything that implements the `Store` trait — `list`, `get`, `create`, `update`, `patch` and `remove`, each of them `async` and each free to fail with a `LinoHttpError`, so a database-backed store is written the same way as the built-in `MemoryStore`.

Options: `with_name` (used in problem details), `with_id_param`, `with_id_field`, `with_operations` (subset of `["list", "create", "get", "update", "patch", "remove"]`), `with_upsert`, `requiring_precondition`.

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

`app.describe()` and `app.openapi()` return the same documents in process, and `without_description()` withdraws both routes.

## Handlers

A handler receives a `LinoRequest` and returns a value, which is encoded as the negotiated representation:

```rust
use lino_objects_codec::LinoValue;
use lino_rest_api::{LinoHttpError, boolean, created, int, no_content, object, status};

app.post_fn("/echo", "Echo the body", |request| {
    Ok(object([(
        "echoed",
        request.body.clone().unwrap_or(LinoValue::Null),
    )]))
});
app.post_fn("/tasks", "Create a task", |_request| {
    Ok(created(object([("id", int(7))]), "/tasks/7"))
});
app.delete_fn("/tasks/:id", "Delete a task", |_request| Ok(no_content()));
app.get_fn("/teapot", "Short and stout", |_request| {
    Ok(status(418, object([("short", boolean(true))])))
});
app.get_fn("/guarded", "Never allowed", |_request| {
    Err::<LinoValue, _>(LinoHttpError::new(403, Some("Not for you")).with_title("Forbidden"))
});
```

`route`, `get`, `post`, `put`, `patch` and `delete` take an `async` handler; the `_fn` variants take a plain one. Returning `()` sends `204`. A returned `LinoHttpError` becomes problem details, and controls the status, title, headers and extension members.

The request carries `method`, `path`, `headers`, `params`, `query`, the decoded `body` and the negotiated `media_type`; collection queries are parsed on demand with `request.collection_query()`.

## Running the application

`serve(app, address)` binds and serves. `BoundServer::bind(app, "127.0.0.1:0")` binds first and reports the port that was chosen, which is how the test suite runs a real server on an ephemeral port. `serve::router(Arc::new(app))` returns the axum `Router`, for mounting the service inside a larger application, and `app.respond(request)` answers a request in process, without a socket at all.

## API reference

Generated with `cargo doc`, and published at [docs.rs/lino-rest-api](https://docs.rs/lino-rest-api):

```bash
cargo doc --no-deps --open
```

Key exports: `create_lino_app`, `LinoApp`, `RawRequest`, `LinoRequest`, `create_lino_client`, `LinoClient`, `LinoClientError`, `LinoResponse`, `RequestOptions`, `MemoryStore`, `Store`, `ResourceOptions`, `LinoHttpError`, `ServiceInfo`, `CorsPolicy`, `ResponseParts`, `ok`, `created`, `accepted`, `no_content`, `status`, `raw_response`, `serve`, `BoundServer`, `encode`, `decode`, `encode_for`, `decode_from`, `encode_single_line`, `encode_compact_notation`, `object`, `array`, `string`, `int`, `boolean`.

## Tests

```bash
cargo test
cargo fmt --check
cargo clippy --all-targets
```

## License

Unlicense
