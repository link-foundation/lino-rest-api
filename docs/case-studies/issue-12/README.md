# Issues #10–#12: requirements, research and verification plan

## Complete requirement inventory

Issue #12 requires reading #10 and #11 and their comments, implementing both in
one PR, and retaining separate `Fixes #10`, `Fixes #11`, and `Fixes #12` references.
All three issues and all three PR comment/review channels were empty of feedback
when implementation began. Neither child issue has further sub-issues.

| Requirement                                               | Proposed solution and verification                                                                                                                                                                                                          |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| #10 binary codec dispatch and public media-type constant  | Use `application/lino-binary` consistently in JS, Python and Rust; test public exports and codec round trips.                                                                                                                               |
| Binary negotiation and server transport                   | Add the representation to supported types and descriptions; keep byte bodies through Express, ASGI, FastAPI and axum; exercise HTTP requests/responses, errors, HEAD and ETags.                                                             |
| Binary LinoClient support                                 | Encode request bytes and consume response bytes (`arrayBuffer()` for fetch, `content` for httpx, `bytes()` for reqwest); test actual client/server round trips.                                                                             |
| JSON independently configurable                           | Retain the ordered supported-type policy and reject disabled request types too; test text + binary with JSON disabled, 406 and 415.                                                                                                         |
| Preserve object semantics                                 | Parse **compact typed object notation**, encode its exact AST, decode the bounded binary AST and format it before object decoding; test Unicode, empty values/collections, booleans, numeric-looking strings, and nested/unary collections. |
| Bound request bytes and decoded graph                     | Retain byte limits and enforce finite links, references, expanded nodes, string bytes and depth in upstream DecodeLimits; test malformed/truncated/trailing packets and each graph limit with small finite inputs.                          |
| #11 most specific range determines each candidate quality | Compute effective quality per supported type including q=0, then select greatest positive quality in server order, in all three implementations.                                                                                            |
| Exact/subtype exclusions and positive overrides           | Regression tests for exact q=0 + `*/*`, subtype q=0 + `*/*`, exact positive + less-specific zero, differing explicit qualities + high wildcard, and server-order ties.                                                                      |
| Apply throughout repository                               | Audit public codecs, middleware, adapters, clients, resource ETags, description/OpenAPI, docs and dependency manifests.                                                                                                                     |
| Release and validation                                    | Add one coordinated minor changeset, run focused local tests, then require final-commit CI passing and mark PR ready.                                                                                                                       |

## Research and alternatives

[RFC 9110 §12.5.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.1)
defines specificity before quality for each representation. The existing
range-first selection is the root cause in all three packages. Replacing the
small shared algorithm avoids three unrelated negotiation dependencies and keeps
server preference deterministic.

[links-notation](https://github.com/link-foundation/links-notation) provides
BinaryLinoCodec and DecodeLimits in all three languages, with a
[shared protocol and vectors](https://github.com/link-foundation/links-notation/blob/main/docs/protocol/binary-links-notation.md).
Reuse that codec rather than inventing a binary format or wrapping JSON.
The issue's [consumer adapter](https://github.com/link-foundation/meta-sovereign/pull/57)
uses links-notation 0.31.3 and lino-objects-codec's typed compact AST. Generic
readable AST formatting loses indentation semantics; encodeText canonicalization
also collapses unary containers. Both alternatives are unsuitable.

The existing [object codec](https://github.com/link-foundation/lino-objects-codec)
already supplies compact encoding/decoding, so no new serialization dependency is
needed. Python keeps the existing pinned vendored object codec. Binary limits are
shared conservative finite defaults, applied on both encoding and decoding.

## Compatibility findings

Shared golden packets exposed two differences in the existing object codecs.
Python's vendored codec spells the compact tags `None`, `dict` and `list`;
the binary boundary maps these to `null`, `object` and `array`, and maps them
back before object decoding. Rust's object codec omits the empty base64 payload;
the binary boundary restores its explicit empty reference and adapts it before
the older object parser reads the formatted document. Existing text output is
unchanged.

The JavaScript object decoder also accepts legacy `(array obj_N ...)` metadata.
An anonymous array beginning with a named shared object can be mistaken for that
form. Before decoding a binary document, give affected containers a fresh,
collision-free identifier. The regression checks both shared identity and cycles.

## Verification evidence

- `js/tests/binary.test.js`: six tests cover golden bytes, graph limits,
  malformed packets, actual HTTP/client transport without JSON, fetch's byte
  response path, and resource ETags with successful and stale conditional writes.
- `python/tests/test_binary.py`: twelve tests cover the same shared packets and
  limits, synchronous/asynchronous clients, ASGI, standalone FastAPI request and
  response wrappers, decorated FastAPI endpoints, and resource conditional writes.
- `rust/tests/binary.rs`: seven tests cover shared packets and limits, in-process
  responses, real axum/reqwest transport, streamed byte limits, and resource
  conditional writes, plus preservation of reqwest text charset/BOM handling.
- Every language's existing media-type suite includes all requested specificity
  cases. The JavaScript regression was run against the old algorithm and failed
  (selected `text/lino` rather than `null`), then passed with the replacement.
- Focused existing middleware, description, resource and adapter tests passed.
  Local Rust checks use one compiler job and disabled debug information to stay
  within the container's memory limit. Final-commit full suites, packaging and
  documentation validation are tracked on PR #13's GitHub Actions checks.

The initial prepared-branch checks failed only because no changeset existed
(`checks-42640131037.log`, lines 182–183). This PR includes a coordinated minor
changeset; subsequent checks must be assessed against the implementation SHA.
