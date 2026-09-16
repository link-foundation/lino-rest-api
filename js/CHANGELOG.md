# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-16

### Added

- Full implementation of the Links Notation REST API specification
  (`docs/spec/README.md`): content negotiation over `text/lino`,
  `text/lino-line`, `text/lino-compact` and `application/json`, RFC 9457 problem
  details, collection queries with pagination, strong entity tags and
  conditional requests, CORS, automatic `HEAD`, `OPTIONS` and `405`, a service
  description and an OpenAPI 3.1 document
- `createLinoApp`: a plain request handler, free of any server dependency, that
  runs on `node:http`, on Bun and behind Express
- `MemoryStore` and `registerResource`/`app.resource`, turning any store —
  synchronous or asynchronous — into a full CRUD collection
- `createLinoClient`, the client of specification section 10, built on `fetch`
- An optional prose `description` for the service, carried by both description
  documents
- A conformance suite (`tests/conformance.test.js`) walking the specification
  checklist in order, and a suite per module

### Changed

- `lino-objects-codec` is now a dependency instead of a vendored copy, so the
  JavaScript, Python and Rust packages encode the same value into the same bytes
- The package exports the whole surface from `src/index.js`; the Express server
  in `src/server.js` is one way to mount it rather than the entry point

### Fixed

- JSON is encoded with the separators the other packages use, so all three
  implementations produce the same entity tag for the same value

## [0.1.0] - 2024-12-13

### Added

- Initial release with the LINO REST API middleware and an Express server
