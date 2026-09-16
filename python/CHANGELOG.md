# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-16

- Implement the full Links Notation REST API specification in JavaScript, Python and Rust: content negotiation, conditional requests, RFC 9457 problem details, collection queries with RFC 8288 pagination, CORS, automatic `HEAD`/`OPTIONS`/`405`, a service description and an OpenAPI 3.1 document, with the three packages encoding the same value into the same bytes. Adds the Rust server and client crate, a documentation website published to GitHub Pages, and a case study of the work in `docs/case-studies/issue-5`.
### Added

- Full implementation of the Links Notation REST API specification
  (`docs/spec/README.md`): content negotiation over `text/lino`,
  `text/lino-line`, `text/lino-compact` and `application/json`, RFC 9457 problem
  details, collection queries with pagination, strong entity tags and
  conditional requests, CORS, automatic `HEAD`, `OPTIONS` and `405`, a service
  description and an OpenAPI 3.1 document
- `LinoApp`/`create_lino_app`: a plain ASGI application, free of any framework
  dependency, with routes registered by call or by decorator
- `MemoryStore` and `register_resource`/`app.resource`, turning any store —
  synchronous or asynchronous — into a full CRUD collection
- `LinoClient`, `AsyncLinoClient` and their factories, built on httpx
- An optional prose `description` for the service, carried by both description
  documents
- A conformance suite (`tests/test_conformance.py`) and a live-server suite
  (`tests/test_server.py`), mirroring the JavaScript package test for test

### Changed

- FastAPI is now optional (`pip install lino-rest-api[fastapi]`); the legacy
  `LinoAPI` surface is still exported and is resolved on first use

### Fixed

- The JSON representation is now encoded with the same separators as the
  JavaScript package, so both implementations produce the same entity tag for
  the same value
- Boolean query parameters are spelled `true`/`false` rather than Python's
  `True`/`False`, so filters sent by the client are understood by the server

## [0.1.1] - 2025-12-14

- Add release workflow with changeset support and update to Python 3.13 only

- Updated Python support to only version 3.13 (the latest stable)
- Added comprehensive release workflow similar to test-anywhere
- Implemented PyPI OIDC trusted publishing
- Created changeset-based version management system
- Added Python-specific release scripts
## [0.1.0] - 2024-12-13

### Added

- Initial release with LINO REST API framework
- FastAPI middleware for Links Notation parsing
- Basic server implementation with uvicorn
- Python 3.13 support only
