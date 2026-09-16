# Case study: issue #5 — a full REST standard with Links Notation instead of JSON

[Issue #5](https://github.com/link-foundation/lino-rest-api/issues/5) asks this
repository to become the library somebody reaches for when they want a REST API
whose wire format is [Links Notation](https://github.com/link-foundation/links-notation)
rather than JSON, in JavaScript, Python **and** Rust, with the documentation to
prove it. This document collects the data behind that request, states every
requirement it contains, surveys what already exists, and records the plan and
the outcome for each requirement.

The raw material is in [`raw-data/`](raw-data): the issue and its comments, the
five upstream `link-cli` issues it points at, and the registry versions of the
dependencies, all captured with `gh` and the public registry APIs.

## 1. The request, in the words of the issue

> We need to make sure we support full REST API standard (with Links Notation
> instead of JSON) for any API here as library, including for use cases at
> <https://github.com/link-foundation/link-cli/issues/32>
>
> Based on <https://github.com/link-foundation/rust-ai-driven-development-pipeline-template>
> we should add full support for Rust server and client libraries, as well as
> make sure we have all the features for python and javascript.
>
> We must also have automated docs generation and GitHub Web Pages website, to
> show it all. So whoever needs REST API with links notation instead of JSON can
> make some.
>
> Also we need to make sure we update exactly all our dependencies to the latest
> version […] We can pause if some of these repositories do not have some
> features we require, yet we should fully implement workarounds if possible
> here […]

— [`raw-data/issue-5.json`](raw-data/issue-5.json). The issue carries no
comments ([`raw-data/issue-5-comments.json`](raw-data/issue-5-comments.json) is
an empty list), so the body is the whole brief.

### The upstream use case

`link-cli` issue #32, _LINO API (REST)_, is two sentences long: “Make a REST
style API, but use LINO instead of JSON.”
([`raw-data/link-cli-issue-32.json`](raw-data/link-cli-issue-32.json)). It sits
in a family of sibling issues that share one parent idea — expose the CLI’s link
store over a network in a Links-Notation-native way:

| Upstream issue                                               | Title                                               | Body                                                                                                      |
| ------------------------------------------------------------ | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| [#30](https://github.com/link-foundation/link-cli/issues/30) | LiNo protocol server mode (LINO API)                | “Add `--server` option to start server listening on a port. That can be implemented as websocket server.” |
| [#31](https://github.com/link-foundation/link-cli/issues/31) | Benchmark CLI access vs LiNo protocol server access | _(empty)_                                                                                                 |
| [#32](https://github.com/link-foundation/link-cli/issues/32) | LINO API (REST)                                     | “Make a REST style API, but use LINO instead of JSON.”                                                    |
| [#33](https://github.com/link-foundation/link-cli/issues/33) | LINO API (GRPC)                                     | “Make a GRPC style API, but use LINO instead of JSON.”                                                    |
| [#34](https://github.com/link-foundation/link-cli/issues/34) | LINO API (GraphQL)                                  | “Make a GraphQL style API, but use LINO instead of JSON.”                                                 |

Two readings of the brief follow from this table, and the difference matters.

The **narrow reading** is “write a REST server for `link-cli`”. That is not what
issue #5 asks for: it says “for any API here **as library**”, and `link-cli` is
a separate repository written in Rust. The **wide reading** — the one taken here
— is that this repository must offer a library that `link-cli` (and anyone else)
can depend on to get a standards-complete REST layer for free, in whichever of
the three languages they are working in. `link-cli` is a Rust program, which is
exactly why the issue asks for Rust server _and_ client support: without a Rust
crate, the primary consumer of this work could not consume it at all.

The gRPC (#33) and GraphQL (#34) siblings are explicitly _not_ in scope for this
repository’s issue #5, which names only #32. They do, however, set a design
constraint: the value model and the codec must not be entangled with HTTP, so
that a future gRPC or GraphQL layer can reuse them.

## 2. What “full REST API standard” has to mean

“REST” is an architectural style, not a specification one can conform to
mechanically, so “full REST API standard” needs a concrete reading before it can
be implemented or tested. The reading adopted here is: **everything the current
HTTP RFCs expect of a well-behaved resource-oriented HTTP API**, with LINO in
the place JSON usually occupies. That resolves to a checkable list:

| Concern                    | Standard                                                                    | What it demands                                                                                                               |
| -------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Uniform interface          | [RFC 9110 §9](https://www.rfc-editor.org/rfc/rfc9110#section-9)             | `GET`/`HEAD`/`POST`/`PUT`/`PATCH`/`DELETE`/`OPTIONS` with their defined semantics; safe and idempotent methods behave as such |
| Method not allowed         | [RFC 9110 §15.5.6](https://www.rfc-editor.org/rfc/rfc9110#section-15.5.6)   | `405` carries `Allow`                                                                                                         |
| Content negotiation        | [RFC 9110 §12](https://www.rfc-editor.org/rfc/rfc9110#section-12)           | `Accept` with quality values, `406`, `Vary`                                                                                   |
| Unsupported request bodies | [RFC 9110 §15.5.16](https://www.rfc-editor.org/rfc/rfc9110#section-15.5.16) | `415` for an unknown `Content-Type`                                                                                           |
| Entity tags and caching    | [RFC 9110 §8.8](https://www.rfc-editor.org/rfc/rfc9110#section-8.8)         | strong `ETag`, `Last-Modified`                                                                                                |
| Conditional requests       | [RFC 9110 §13](https://www.rfc-editor.org/rfc/rfc9110#section-13)           | `If-None-Match` → `304`, `If-Match` → `412`, `428` when an edit is unconditional                                              |
| Errors                     | [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)                          | problem details with `type`, `title`, `status`, `detail`, `instance`                                                          |
| Pagination                 | [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288)                          | `Link` with `first`/`prev`/`next`/`last`                                                                                      |
| Cross-origin access        | [Fetch, §CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol)  | preflight, allow-listed origins, `Vary: Origin`                                                                               |
| Self-description           | [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)                         | a machine-readable document; plus a home document for humans                                                                  |

The LINO substitution then adds requirements of its own. A media type has to
exist for each notation flavour, JSON has to remain reachable as a fallback so
that ordinary HTTP tooling still works, and — the subtle one — **all three
implementations must serialise identically**. Strong entity tags are a hash of
the encoded body; if the Python encoder emits one byte that the JavaScript
encoder does not, a client that fetches from a Python server and revalidates
against a Rust server gets a spurious `200` instead of a `304`. Byte parity is
therefore not a nicety, it is a correctness requirement that falls directly out
of RFC 9110 §8.8.1’s definition of a strong validator.

## 3. Requirements extracted from the issue

Every requirement the issue states, numbered for reference, with its status in
this pull request.

| #   | Requirement                                                                            | Source sentence                                                                                                                                                         | Status                                                                                                 |
| --- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| R1  | Support the full REST standard, with LINO in place of JSON, as a **library**           | “support full REST API standard (with Links Notation instead of JSON) for any API here as library”                                                                      | Done — specified in [`docs/spec/README.md`](../../spec/README.md), implemented three times             |
| R2  | Cover the `link-cli` #32 use case                                                      | “including for use cases at …/link-cli/issues/32”                                                                                                                       | Done — analysed in §1; the Rust crate is the consumable form                                           |
| R3  | Add a full Rust **server** library                                                     | “add full support for Rust server … libraries”                                                                                                                          | Done — [`rust/src/app.rs`](../../../rust/src/app.rs), [`serve.rs`](../../../rust/src/serve.rs) on axum |
| R4  | Add a full Rust **client** library                                                     | “… and client libraries”                                                                                                                                                | Done — [`rust/src/client.rs`](../../../rust/src/client.rs) on reqwest                                  |
| R5  | Follow the Rust pipeline template                                                      | “Based on …/rust-ai-driven-development-pipeline-template”                                                                                                               | Done — `fmt`/`clippy -D warnings`/`test`/`package` in CI, rustdoc published                            |
| R6  | Make sure Python has all the features                                                  | “make sure we have all the features for python”                                                                                                                         | Done — parity table in §6                                                                              |
| R7  | Make sure JavaScript has all the features                                              | “… and javascript”                                                                                                                                                      | Done — parity table in §6                                                                              |
| R8  | Automated documentation generation                                                     | “We must also have automated docs generation”                                                                                                                           | Done — [`scripts/build-docs.mjs`](../../../scripts/build-docs.mjs) drives JSDoc, pdoc and rustdoc      |
| R9  | A GitHub Pages website that shows it all                                               | “and GitHub Web Pages website, to show it all”                                                                                                                          | Done — [`.github/workflows/docs.yml`](../../../.github/workflows/docs.yml)                             |
| R10 | Be usable by a stranger who needs such an API                                          | “So whoever needs REST API with links notation instead of JSON can make some.”                                                                                          | Done — quickstarts in all three READMEs, runnable examples per language                                |
| R11 | Update **exactly all** dependencies to the latest version                              | “we need to make sure we update exactly all our dependencies to the latest version”                                                                                     | Done with two documented ceilings — §7                                                                 |
| R12 | Specifically `links-notation` and `lino-objects-codec`                                 | the two listed URLs                                                                                                                                                     | Done — `links-notation` 0.20.0 everywhere; codec at each registry’s maximum, §7                        |
| R13 | Work around missing upstream features rather than stopping                             | “we should fully implement workarounds if possible here”                                                                                                                | Done — the vendored Python codec, §7.2                                                                 |
| R14 | Compile the collected data into `./docs/case-studies/issue-5`                          | “make sure we compile that data to `./docs/case-studies/issue-{id}` folder”                                                                                             | Done — this folder                                                                                     |
| R15 | Deep case study: requirements, solution plans, existing-component survey, online facts | “use it to do deep case study analysis … list of each and all requirements … propose possible solutions and solution plans … check known existing components/libraries” | Done — this document                                                                                   |
| R16 | One pull request for everything                                                        | “plan and execute everything in this single pull request”                                                                                                               | Done — [#6](https://github.com/link-foundation/lino-rest-api/pull/6)                                   |

## 4. Existing components surveyed

Before writing anything, the obvious question is whether an existing library
already does this. The survey below is why each piece was written, reused, or
deliberately not used.

### 4.1 Could an existing framework be configured into it?

| Candidate                                                          | Why it does not solve R1 by itself                                                                                                                                                                                                      | How it is used here                                                                                                                                                                                   |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **FastAPI** (Python)                                               | Its request/response model, validation and OpenAPI generation are built around JSON and Pydantic; a custom media type can be bolted on per route, but negotiation, conditional requests and problem details remain the author’s problem | Kept as an **optional adapter**, [`fastapi_adapter.py`](../../../python/src/lino_rest_api/fastapi_adapter.py), so existing FastAPI applications can add LINO routes; the core no longer depends on it |
| **Express 5** (JavaScript)                                         | A routing and middleware layer, no opinion about representation, negotiation or caching                                                                                                                                                 | Used as an optional mount target; the core app is framework-free                                                                                                                                      |
| **axum 0.8** (Rust)                                                | Excellent HTTP plumbing, `Json<T>` extractor; nothing about LINO, problem details or ETags                                                                                                                                              | Used as the server shell in [`serve.rs`](../../../rust/src/serve.rs); the application itself is transport-agnostic                                                                                    |
| **`problem-details` / `http-problem-details` crates and packages** | Cover RFC 9457 only, and only in JSON                                                                                                                                                                                                   | Not used — the problem document must serialise as `application/problem+lino` through the same codec as everything else, so it shares the value model instead                                          |
| **`content-type` / `negotiator` (npm), `accept` parsers**          | Solve one row of the table in §2                                                                                                                                                                                                        | Not used — a 90-line negotiator that the three languages can implement identically is cheaper than three different third-party parsers that disagree at the edges                                     |
| **`hal`, `siren`, `jsonapi` toolkits**                             | Hypermedia formats defined _in terms of JSON_                                                                                                                                                                                           | Not used; `Link` headers (RFC 8288) carry the hypermedia affordances instead, which is format-neutral                                                                                                 |

The conclusion is the design: reuse **transport** libraries (axum, Express,
ASGI, reqwest, httpx, `fetch`) and the **notation** libraries, and write the REST
semantics once as a specification that all three implementations satisfy.

### 4.2 Reused wholesale

- [`links-notation`](https://github.com/link-foundation/links-notation) — the
  notation parser and writer. Published in all three ecosystems at the same
  version, which is what makes tri-language parity feasible at all.
- [`lino-objects-codec`](https://github.com/link-foundation/lino-objects-codec) —
  the object ↔ LINO mapping, including the compact and single-line flavours.
- axum + tokio, Express, ASGI; reqwest, httpx, `fetch` on the client side.
- JSDoc, pdoc and rustdoc for reference documentation; `marked` for the prose
  pages.

### 4.3 The precedent inside the Link Foundation

The issue points at
[`rust-ai-driven-development-pipeline-template`](https://github.com/link-foundation/rust-ai-driven-development-pipeline-template)
as the model for the Rust side (R5). What that template establishes, and what
this pull request adopts, is the check set: `cargo fmt --check`, `cargo clippy
--all-targets -- -D warnings`, `cargo test`, and a packaging check, run in CI on
every change, with the crate’s documentation published rather than merely built.

## 5. Solution plans, requirement by requirement

### R1 — the standard, as a specification first

_Options considered._ (a) Implement three libraries and hope they agree.
(b) Write a specification, then implement it three times, with a conformance
suite derived from the specification. (c) Generate three implementations from a
single source of truth.

_Chosen: (b)._ Option (a) has no defence against drift — and drift here is
observable by users as broken ETags. Option (c) buys consistency at the cost of
idiomatic code in each language, which is precisely what R6/R7/R10 ask for.

_Plan._ Write [`docs/spec/README.md`](../../spec/README.md) as eleven numbered
sections — rationale, media types, value model, uniform interface, errors,
collections, conditional requests, CORS, service description, client
obligations, and a conformance checklist. Then implement each section in each
language, and give each language a `conformance` test suite that walks the
checklist in order. The checklist is the contract; `js/tests/conformance.test.js`,
`python/tests/test_conformance.py` and `rust/tests/conformance.rs` are its three
witnesses.

_Byte parity._ A shared fixture file, `readable-format-cases.json`, is checked
into the Python and Rust test trees and exercised by `test_codec_parity.py` and
`codec_parity.rs`; the JavaScript codec suite covers the same cases. Any
encoder change that moves a byte breaks a test in at least one language.

### R2 — the `link-cli` use case

_Plan._ Do not add a `--server` mode to anything; instead make the Rust crate the
thing `link-cli` can depend on, with a `Store` trait it can implement over its
own link storage, and an axum shell it can mount. [`rust/src/store.rs`](../../../rust/src/store.rs)
defines the trait and ships a `MemoryStore`; [`rust/examples/server.rs`](../../../rust/examples/server.rs)
is the twenty-line program that turns a store into a standards-complete REST
service. That is the smallest possible surface for issue #32 to consume.

### R3 and R4 — the Rust server and client

_Plan._ Port the existing module structure one-for-one, so the three libraries
stay legible side by side: `app`, `client`, `codec`, `collection`, `cors`,
`description`, `etag`, `headers`, `media_type`, `middleware`, `problem`,
`query`, `request`, `resource`, `response`, `router`, `serve`, `store`, `value`.
Keep the application transport-free (`LinoApp::respond(RawRequest) ->
ResponseParts`) so it can be tested in process and served over a socket by the
same code, and re-export the JavaScript/Python surface at the crate root so the
three libraries read alike.

_Notable consequence._ Every fallible operation returns `LinoHttpError`, because
that is what becomes a problem document. It exceeds clippy’s
`result_large_err` threshold, so the crate allows the lint at its root with the
reasoning written down — and, because each integration test and example is its
own crate, the allow has to be repeated in those files. That is a real and
easily-missed property of Cargo’s build model, recorded here so the next person
does not rediscover it.

### R5 — the Rust pipeline

_Plan._ A `test-rust` job in [`release.yml`](../../../.github/workflows/release.yml)
running `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`,
`cargo test` and `cargo package --allow-dirty`, cached with
`Swatinem/rust-cache@v2`, with the release job gated on it.

### R6 and R7 — Python and JavaScript feature parity

_Plan._ Treat the specification’s checklist as the parity definition and hold
all three to it, rather than comparing the libraries to each other informally.
Where a language had a gap, close it (see §6).

### R8 and R9 — documentation and the website

_Options considered._ (a) A documentation framework (Docusaurus, MkDocs,
mdBook). (b) Three separate reference sites, linked from the repository README.
(c) One small generator that renders the repository’s own markdown and embeds
the three native reference builds.

_Chosen: (c)._ (a) adds a large dependency and a second copy of the prose, which
then rots against the READMEs GitHub shows. (b) leaves no place where a visitor
sees “it all”, which is what R9 asks for. (c) keeps a single source per document:
`js/README.md` is both what GitHub renders and what the website serves.

_Plan._ [`scripts/build-docs.mjs`](../../../scripts/build-docs.mjs) renders the
prose pages with `marked` into a shared template, rewriting relative links so
that a link which works on GitHub also works on the site (targets that are
rendered pages become site-relative; everything else points back at the
repository), then invokes JSDoc, pdoc and rustdoc and copies their output under
`api/`. `.nojekyll` is written into the site root, because rustdoc emits
`_`-prefixed directories that Jekyll would otherwise discard.
[`docs.yml`](../../../.github/workflows/docs.yml) builds on every push and pull
request and deploys to Pages outside pull requests.

### R11, R12, R13 — dependencies

_Plan._ Check every direct dependency against its registry, raise it to the
maximum published version, and where the maximum is not the upstream repository’s
latest, say so explicitly rather than silently pinning. See §7.

### R14, R15 — the case study

_Plan._ Capture the sources with `gh` and the registry APIs into `raw-data/`,
then write this analysis against them, with every factual claim traceable to a
file in that folder or to a cited specification.

## 6. Feature parity across the three languages

The specification’s conformance checklist, and where each requirement is met.
Every row is covered by a test in all three suites.

| Capability                                                             | JavaScript                          | Python                      | Rust                                        |
| ---------------------------------------------------------------------- | ----------------------------------- | --------------------------- | ------------------------------------------- |
| `text/lino`, `text/lino-line`, `text/lino-compact`, `application/json` | `src/media-type.js`                 | `media_type.py`             | `media_type.rs`                             |
| Negotiation with quality values, `406`, `Vary`                         | ✓                                   | ✓                           | ✓                                           |
| `415` on an unknown request media type                                 | ✓                                   | ✓                           | ✓                                           |
| Automatic `HEAD`, `OPTIONS`, `405` + `Allow`                           | `src/router.js`                     | `router.py`                 | `router.rs`                                 |
| Strong `ETag` (SHA-256 of the encoded body), `Last-Modified`           | `src/etag.js`                       | `etag.py`                   | `etag.rs`                                   |
| `If-None-Match` → `304`, `If-Match` → `412`, `428`                     | `src/middleware.js`                 | `middleware.py`             | `middleware.rs`                             |
| RFC 9457 problem details as `application/problem+lino`                 | `src/problem.js`                    | `problem.py`                | `problem.rs`                                |
| Collections: filter, sort, paginate, sparse fields                     | `src/collection.js`, `src/query.js` | `collection.py`, `query.py` | `collection.rs`, `query.rs`                 |
| RFC 8288 `Link` pagination                                             | ✓                                   | ✓                           | ✓                                           |
| CORS incl. preflight and `Vary: Origin`                                | `src/cors.js`                       | `cors.py`                   | `cors.rs`                                   |
| Service description + OpenAPI 3.1                                      | `src/description.js`                | `description.py`            | `description.rs`                            |
| Resource registration over a pluggable store                           | `src/resource.js`, `src/store.js`   | `resource.py`, `store.py`   | `resource.rs`, `store.rs`                   |
| HTTP client honouring the client obligations                           | `src/client.js`                     | `client.py`                 | `client.rs`                                 |
| Server shell                                                           | Express / `node:http`               | ASGI / uvicorn              | axum                                        |
| Runnable example                                                       | `js/examples/basic_usage.js`        | `python/examples/`          | `rust/examples/basic_usage.rs`, `server.rs` |
| Conformance suite                                                      | `tests/conformance.test.js`         | `tests/test_conformance.py` | `tests/conformance.rs`                      |
| Cross-language byte parity                                             | codec suite                         | `test_codec_parity.py`      | `codec_parity.rs`                           |

Test counts at the time of writing: 141 JavaScript tests, 344 Python tests, and
the Rust suite’s 17 integration and unit binaries plus 25 documentation tests.

## 7. The dependency audit

Registry state as collected on 2026-09-16
([`raw-data/registry-versions.json`](raw-data/registry-versions.json)):

| Package                        | npm           | PyPI          | crates.io     |
| ------------------------------ | ------------- | ------------- | ------------- |
| `links-notation`               | 0.20.0        | 0.20.0        | 0.20.0        |
| `lino-objects-codec`           | 0.8.0         | _absent_      | 0.7.0         |
| `lino-rest-api` (this project) | _unpublished_ | _unpublished_ | _unpublished_ |

### 7.1 What is at its maximum

`links-notation` is at 0.20.0 in all three ecosystems and this repository
requires 0.20.0 in all three. Every other direct dependency — Express 5.2.1,
httpx, axum 0.8.9, reqwest 0.13.5, tokio 1.53.1, `serde_json` 1.0.151, sha2
0.11.0, `async-trait` 0.1.92 — is at its latest published version;
`cargo update --dry-run --verbose` reports no available upgrade for any direct
dependency. Ten _transitive_ crates (`encoding_rs`, the `icu_*` family,
`idna_adapter`, `matchit`) are held one version back by the crate’s
`rust-version = "1.85"`. Raising the MSRV to take them would trade a documented
compatibility guarantee for nothing the library uses; the ceiling is recorded
here instead.

### 7.2 Where upstream is the ceiling — and the workarounds

Two gaps exist, and R13 says to work around them rather than stop.

**`lino-objects-codec` is not on PyPI at all.** The Python package therefore
carries a verbatim copy of the upstream Python implementation under
[`python/src/lino_rest_api/vendor/lino_objects_codec`](../../../python/src/lino_rest_api/vendor),
with the pinned upstream commit recorded in `VENDORED.md` and a refresh script,
`scripts/sync-vendored-codec.mjs`, that re-syncs it. The vendored tree is
exercised by the same parity fixtures as the other two languages, so a divergence
between the copy and its upstream shows up as a failing parity test rather than
as a silently different wire format. When the package appears on PyPI, the
vendor directory can be deleted and a dependency added — the import surface in
`vendor/__init__.py` is already shaped like the upstream module’s.

**crates.io stops at 0.7.0 while npm has 0.8.0.** The Rust crate therefore
depends on `lino-objects-codec = "0.7.0"`, the maximum that exists for it. This
is not a pin chosen for convenience: 0.8.0 cannot be depended on from Cargo
until it is published. The parity fixtures confirm that 0.7.0 produces the same
bytes as npm 0.8.0 for every case in `readable-format-cases.json`, so the version
skew is currently invisible on the wire. If a future codec release changes the
encoding, the parity suites are what will detect it.

Neither gap is a reason to pause under R13’s test — both have working
workarounds, and all the code that does not depend on the missing publications
is complete.

## 8. What a future contributor should know

- **The specification is the contract.** A change to behaviour belongs in
  `docs/spec/README.md` first, then in three implementations and three
  conformance suites.
- **Byte parity is load-bearing.** Encoder changes must keep
  `readable-format-cases.json` passing everywhere, or entity tags stop matching
  across languages.
- **pdoc reads `__all__` from the module dictionary.** `lino_rest_api`’s lazy
  `__getattr__` for the optional FastAPI adapter binds resolved names into
  `globals()` for exactly this reason (pdoc’s `doc.py`, `_member_objects`, only
  consults `self.obj.__dict__`), and three tests in
  `python/tests/test_fastapi_adapter.py` guard the behaviour.
- **Each Rust test and example is its own crate**, so crate-level `allow`
  attributes do not reach them from `lib.rs`.
- **gRPC (#33) and GraphQL (#34) are out of scope but anticipated**: the value
  model, the codec and the store abstraction carry no HTTP assumptions, so a
  second transport can reuse them.

## 9. Sources

- [`raw-data/issue-5.json`](raw-data/issue-5.json), [`raw-data/issue-5-comments.json`](raw-data/issue-5-comments.json) — the issue and its (empty) comment list.
- [`raw-data/link-cli-issue-30.json`](raw-data/link-cli-issue-30.json) … [`raw-data/link-cli-issue-34.json`](raw-data/link-cli-issue-34.json) — the upstream use cases.
- [`raw-data/registry-versions.json`](raw-data/registry-versions.json) — npm, PyPI and crates.io versions of the dependencies.
- RFC [9110](https://www.rfc-editor.org/rfc/rfc9110) (HTTP semantics), [9457](https://www.rfc-editor.org/rfc/rfc9457) (problem details), [8288](https://www.rfc-editor.org/rfc/rfc8288) (web linking); the [Fetch standard](https://fetch.spec.whatwg.org/#http-cors-protocol) for CORS; [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0).
- [`docs/spec/README.md`](../../spec/README.md) — the wire protocol all three implementations satisfy.
