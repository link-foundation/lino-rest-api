# lino-rest-api

[![Checks and release](https://github.com/link-foundation/lino-rest-api/actions/workflows/release.yml/badge.svg)](https://github.com/link-foundation/lino-rest-api/actions/workflows/release.yml)
[![Documentation](https://github.com/link-foundation/lino-rest-api/actions/workflows/docs.yml/badge.svg)](https://github.com/link-foundation/lino-rest-api/actions/workflows/docs.yml)

A REST API framework and client that speak [Links Notation](https://github.com/link-foundation/links-notation) instead of JSON, in JavaScript, Python and Rust.

Everything the HTTP standards expect of a REST service — content negotiation, conditional requests, problem details, collection pagination, automatic `HEAD`/`OPTIONS`/`405`, CORS, a service description and an OpenAPI document — is provided out of the box, with LINO as the default wire format and JSON as a fallback.

The three implementations speak the same wire, byte for byte, so a value encoded by any of them carries the same entity tag. That wire is written down in the [specification](docs/spec/README.md), and every package ships its executable form as a conformance suite.

**Documentation: <https://link-foundation.github.io/lino-rest-api/>**

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

## Packages

| Directory            | Package                     | Runtime                 | Server shell         | Client            |
| -------------------- | --------------------------- | ----------------------- | -------------------- | ----------------- |
| [`js/`](js/)         | `lino-rest-api` (npm)       | Node.js 20+, Bun        | `node:http`, Express | `fetch`           |
| [`python/`](python/) | `lino-rest-api` (PyPI)      | Python 3.13             | ASGI, uvicorn        | httpx, sync/async |
| [`rust/`](rust/)     | `lino-rest-api` (crates.io) | Rust 1.85, edition 2024 | axum                 | reqwest           |

Each package has its own guide: [JavaScript](js/README.md), [Python](python/README.md), [Rust](rust/README.md).

## Documentation

The website is generated from this repository and published to GitHub Pages on every push to `main`:

```bash
npm run docs        # writes docs/site
```

It renders the guides and the specification, and embeds the API references built by JSDoc, [pdoc](https://pdoc.dev) and rustdoc. See [`scripts/build-docs.mjs`](scripts/build-docs.mjs).

- [Wire specification](docs/spec/README.md) — the normative document the three implementations share
- [JavaScript API](https://link-foundation.github.io/lino-rest-api/api/javascript/index.html)
- [Python API](https://link-foundation.github.io/lino-rest-api/api/python/lino_rest_api.html)
- [Rust API](https://link-foundation.github.io/lino-rest-api/api/rust/lino_rest_api/index.html)
- [Case study: issue #5](docs/case-studies/issue-5/README.md) — the requirements behind this design, and how each was met

## Development

```bash
npm install                      # root tooling: prettier, eslint, changesets
npm test                         # JavaScript suites
cd python && pip install -e ".[dev]" && pytest
cd rust && cargo test
npm run format:check             # prettier
npm run lint:python              # ruff
```

Every change needs exactly one changeset (`npm run changeset`); the release workflow versions and publishes from it.

## Related projects

- [links-notation](https://github.com/link-foundation/links-notation) — the notation, its parser and its writer
- [lino-objects-codec](https://github.com/link-foundation/lino-objects-codec) — the object ↔ Links Notation codec
- [link-cli](https://github.com/link-foundation/link-cli) — the links CLI this library is meant to serve over HTTP
- [test-anywhere](https://github.com/link-foundation/test-anywhere) — the test runner the JavaScript package uses

## License

[Unlicense](LICENSE)
