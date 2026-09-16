# lino-rest-api

A REST API framework and client that speak [Links Notation](https://github.com/link-foundation/links-notation) instead of JSON, in JavaScript, Python and Rust.

Everything the HTTP standards expect of a REST service — content negotiation, conditional requests, problem details, collection pagination, automatic `HEAD`/`OPTIONS`/`405`, CORS, a service description and an OpenAPI document — is provided out of the box, with LINO as the default wire format and JSON as a fallback.

The three implementations speak the same wire, byte for byte, so a value encoded by any of them carries the same entity tag. That wire is written down in the [specification](spec/README.md) and every package ships its executable form as a conformance suite.

## Install

```bash
npm install lino-rest-api        # JavaScript, on Node.js or Bun
pip install lino-rest-api        # Python 3.13, any ASGI server
cargo add lino-rest-api          # Rust, on axum
```

## A service in three languages

```javascript
import { MemoryStore, createLinoApp } from "lino-rest-api";

const app = createLinoApp({ title: "Tasks API", version: "1.0.0" });
app.resource("/tasks", new MemoryStore(), { name: "task" });
app.get("/health", () => ({ status: "ok" }));
app.listen(8000);
```

```python
from lino_rest_api import MemoryStore, create_lino_app

app = create_lino_app(title="Tasks API", version="1.0.0")
app.resource("/tasks", MemoryStore(), name="task")
app.get("/health", lambda request: {"status": "ok"})
```

```rust
use lino_rest_api::{MemoryStore, ResourceOptions, create_lino_app, object, serve, string};
use std::sync::Arc;

let mut app = create_lino_app();
app.resource("/tasks", Arc::new(MemoryStore::new()), ResourceOptions::new().with_name("task"));
app.get_fn("/health", "Liveness probe", |_request| Ok(object([("status", string("ok"))])));
serve(app, "0.0.0.0:8000").await?;
```

Each one answers the same request the same way:

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

## What you get

| Capability            | Behaviour                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Representations       | `text/lino`, `text/lino-line`, `text/lino-compact`, `application/json`                           |
| Negotiation           | `Accept` with quality values, `Vary: Accept`, `406` and `415` as problem details                 |
| Errors                | [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details as `application/problem+lino` |
| Collections           | `limit`, `offset`, `sort`, `fields`, field filters, `Link` pagination                            |
| Conditional requests  | Strong `ETag` per representation, `304`, `412`, `428`                                            |
| Uniform interface     | Automatic `HEAD`, `OPTIONS` with `Allow`, `405` for a known path                                 |
| Cross-origin requests | Preflight and simple-request CORS, including exposed headers                                     |
| Description           | `/.well-known/lino-api` and `/.well-known/openapi.json` (OpenAPI 3.1)                            |

## Guides

- [JavaScript](../js/README.md) — Express 5, Node.js and Bun
- [Python](../python/README.md) — ASGI, with a synchronous and an asynchronous client
- [Rust](../rust/README.md) — axum, with `async` stores and a typed client

## Reference

- [Wire specification](spec/README.md) — the normative document the three implementations share
- [JavaScript API](https://link-foundation.github.io/lino-rest-api/api/javascript/index.html) — generated with JSDoc
- [Python API](https://link-foundation.github.io/lino-rest-api/api/python/lino_rest_api.html) — generated with pdoc
- [Rust API](https://link-foundation.github.io/lino-rest-api/api/rust/lino_rest_api/index.html) — generated with rustdoc

## Case studies

- [Issue #5 — all the features for a LINO REST API](case-studies/issue-5/README.md)

## Project

The source, the issue tracker and the releases live on [GitHub](https://github.com/link-foundation/lino-rest-api). The code is released into the public domain under the [Unlicense](https://github.com/link-foundation/lino-rest-api/blob/main/LICENSE).
