# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-16

### Added

- First release of the Rust crate: a full implementation of the Links Notation
  REST API specification (`docs/spec/README.md`), matching the JavaScript and
  Python packages feature for feature and byte for byte
- Content negotiation over `text/lino`, `text/lino-line`, `text/lino-compact`
  and `application/json`, with quality values, `Vary: Accept`, `406` and `415`
- RFC 9457 problem details, in `application/problem+lino` and
  `application/problem+json`
- Collection queries — `limit`, `offset`, `sort`, `fields` and field filters —
  with the `(items … page …)` envelope and RFC 8288 `Link` pagination
- Strong entity tags (SHA-256 of the encoded body) and conditional requests:
  `304`, `412` and `428`
- CORS, automatic `HEAD`, automatic `OPTIONS` and `405` with an `Allow` header
- The service description at `/.well-known/lino-api` and the OpenAPI 3.1
  document at `/.well-known/openapi.json`
- `LinoApp`/`create_lino_app`: a plain request handler, free of any server
  dependency, with `async` and plain handlers
- `MemoryStore`, the `Store` trait and `ResourceOptions`/`app.resource`,
  turning any store into a full CRUD collection
- `LinoClient`, `RequestOptions` and `LinoClientError`, built on reqwest
- `serve`, `BoundServer` and `serve::router`, the axum shell that carries an
  application over HTTP
- A conformance suite (`tests/conformance.rs`), a live-server suite
  (`tests/server.rs`) and a cross-language codec parity suite
  (`tests/codec_parity.rs`) running the shared fixtures the other packages run
- `examples/basic_usage.rs`, a printed tour of the whole protocol, and
  `examples/server.rs`, a service left running for `curl`
