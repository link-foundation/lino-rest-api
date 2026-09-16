# LINO REST API Specification

Version: 1.0 (draft)

This document defines how a REST API exchanges data in
[Links Notation](https://github.com/link-foundation/links-notation) (LINO) instead of JSON.
It is the single normative reference shared by the JavaScript, Python and Rust
implementations in this repository. Every implementation is expected to pass the
same conformance checklist at the end of this document.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be interpreted as
described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 1. Rationale

REST is a transport-agnostic architectural style; JSON is only the representation
format that became conventional. Replacing the representation with LINO keeps
every REST property (uniform interface, statelessness, cacheability, layered
system, resource identification via URIs) and changes only how a representation is
serialised on the wire.

LINO's readable form is line-oriented, indentation-structured and free of the
punctuation noise of JSON:

```lino
(
  id 1
  name "Hello, Links!"
  tags (
    "a"
    "b"
  )
)
```

is the LINO representation of

```json
{ "id": 1, "name": "Hello, Links!", "tags": ["a", "b"] }
```

## 2. Media types

| Media type          | Meaning                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------- |
| `text/lino`         | Readable, indented Links Notation. **The default** representation.                                      |
| `text/lino-line`    | Readable Links Notation restricted to a single line per value. Used for append-only logs and streaming. |
| `text/lino-compact` | Type-tagged, base64 Links Notation. Preserves object identity and circular references.                  |
| `application/json`  | Optional JSON fallback for clients that cannot speak LINO.                                              |

A server MUST accept `text/lino` on request bodies and MUST produce `text/lino` by
default. A server MUST include `charset=utf-8` when it emits a LINO media type.

`text/lino-compact` is the only form that can carry shared object identity and
cycles. `text/lino` and `text/lino-line` are plain trees; an encoder MUST fail with
`422 Unprocessable Content` when asked to write a cyclic value in those forms.

### 2.1 Content negotiation

- A request body is decoded according to its `Content-Type`. An unsupported type
  MUST produce `415 Unsupported Media Type`.
- A response representation is selected from the `Accept` header using standard
  quality values (RFC 9110 §12.5.1). When no listed type is supported the server
  MUST respond `406 Not Acceptable`.
- A missing or `*/*` `Accept` header selects `text/lino`.
- Every response with a body MUST carry `Vary: Accept`.

### 2.2 Streaming

`text/lino-line` writes exactly one value per line, so a response body is a
newline-delimited sequence of records that stays greppable, tailable and countable
with `wc -l`. It is the representation used for streaming collection endpoints.

## 3. Value model

The representation carries the LINO object model, which maps one-to-one onto the
common scalar/collection model of every host language:

| LINO             | JavaScript | Python  | Rust                |
| ---------------- | ---------- | ------- | ------------------- |
| `null`           | `null`     | `None`  | `LinoValue::Null`   |
| `true` / `false` | `boolean`  | `bool`  | `LinoValue::Bool`   |
| integer          | `number`   | `int`   | `LinoValue::Int`    |
| float            | `number`   | `float` | `LinoValue::Float`  |
| `"quoted"`       | `string`   | `str`   | `LinoValue::String` |
| `(a b c)`        | `Array`    | `list`  | `LinoValue::Array`  |
| `(k v)` pairs    | `Object`   | `dict`  | `LinoValue::Object` |

Encoding and decoding is delegated to
[lino-objects-codec](https://github.com/link-foundation/lino-objects-codec), which
produces byte-identical readable output in all four of its languages.

## 4. Uniform interface

### 4.1 Methods

| Method    | Safe | Idempotent | Body | Usual success         |
| --------- | ---- | ---------- | ---- | --------------------- |
| `GET`     | yes  | yes        | no   | `200`                 |
| `HEAD`    | yes  | yes        | no   | `200`, headers only   |
| `OPTIONS` | yes  | yes        | no   | `204` with `Allow`    |
| `POST`    | no   | no         | yes  | `201` with `Location` |
| `PUT`     | no   | yes        | yes  | `200` or `204`        |
| `PATCH`   | no   | no         | yes  | `200`                 |
| `DELETE`  | no   | yes        | no   | `204`                 |

A server MUST answer `HEAD` for every registered `GET` route with the same status
and headers and an empty body. A server MUST answer `OPTIONS` for every registered
path with an `Allow` header listing the methods registered on that path, always
including `OPTIONS` and including `HEAD` whenever `GET` is registered. A request
with a method that is not registered on an existing path MUST receive `405 Method
Not Allowed` together with an `Allow` header.

### 4.2 Status codes

Implementations use the standard HTTP semantics of RFC 9110. The codes with
specific obligations in this specification are `201`, `204`, `304`, `405`, `406`,
`409`, `412`, `415`, `422` and `428`.

## 5. Errors

Errors are [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457)
expressed in LINO and served as `text/lino` (a server MAY use the more specific
`application/problem+lino` when it needs to distinguish error bodies):

```lino
(
  type "https://link-foundation.github.io/lino-rest-api/errors/not-found"
  title "Not Found"
  status 404
  detail "Item 42 does not exist"
  instance "/items/42"
)
```

`type`, `title` and `status` MUST be present. `detail` and `instance` SHOULD be
present. Additional members MAY be added; `errors` is reserved for a list of
field-level validation failures:

```lino
(
  type "https://link-foundation.github.io/lino-rest-api/errors/validation-failed"
  title "Unprocessable Content"
  status 422
  detail "Request body failed validation"
  errors (
    (
      field "name"
      message "is required"
    )
  )
)
```

Registered problem types live under
`https://link-foundation.github.io/lino-rest-api/errors/` and use the kebab-case
slug of the HTTP reason phrase (`bad-request`, `not-found`, `conflict`,
`unsupported-media-type`, `validation-failed`, `internal-server-error`, …).

## 6. Collections

A collection response is an object with `items` and `page`:

```lino
(
  items (
    (
      id 1
      name "first"
    )
    (
      id 2
      name "second"
    )
  )
  page (
    limit 20
    offset 0
    total 2
    count 2
  )
)
```

### 6.1 Pagination

Offset pagination is driven by the `limit` and `offset` query parameters.
`limit` MUST be clamped to a server-configured maximum. `page.total` is the number
of items matching the query before pagination; `page.count` is the number of items
in this response.

When more items exist the server SHOULD emit RFC 8288 `Link` headers with `next`,
`prev`, `first` and `last` relations.

### 6.2 Filtering

Any query parameter that is not reserved is a field equality filter.
`GET /items?status=open` returns the items whose `status` field equals `"open"`.
The reserved parameter names are `limit`, `offset`, `sort` and `fields`.

Filter values are parsed with the LINO scalar rules, so `?done=true` filters on the
boolean `true` and `?id=7` filters on the integer `7`.

### 6.3 Sorting

`sort` takes a comma-separated list of field names. A leading `-` reverses the
order for that field: `GET /items?sort=-created_at,name`.

### 6.4 Sparse fieldsets

`fields` takes a comma-separated list of field names; the server MUST return only
those fields of each item.

## 7. Conditional requests and caching

A server SHOULD emit a strong `ETag` for every single-resource `GET`. The entity
tag is the hexadecimal SHA-256 of the encoded representation bytes, quoted.

- `If-None-Match` matching the current tag on a safe method MUST yield `304 Not
Modified` with no body.
- `If-Match` not matching the current tag on an unsafe method MUST yield `412
Precondition Failed`.
- A route MAY be declared as requiring a precondition; an unsafe request to such a
  route without `If-Match` MUST yield `428 Precondition Required`.

## 8. Cross-origin requests

A server MAY enable CORS. When enabled it MUST answer preflight `OPTIONS`
requests with `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` and
`Access-Control-Allow-Headers`, and it MUST list `Content-Type` and `Accept` among
the allowed headers so that browsers may negotiate LINO.

## 9. Service description

A server SHOULD expose a machine-readable description of its routes at
`GET /.well-known/lino-api`, encoded as LINO:

```lino
(
  lino_api "1.0"
  info (
    title "Items API"
    version "1.0.0"
  )
  media_types (
    "text/lino"
    "text/lino-line"
    "text/lino-compact"
    "application/json"
  )
  routes (
    (
      path "/items"
      methods (
        "GET"
        "POST"
      )
      summary "Item collection"
    )
  )
)
```

The same structure is also offered as an OpenAPI 3.1 document at
`GET /.well-known/openapi.json` so that existing tooling can consume the API.

## 10. Client obligations

A conforming client MUST:

- send `Accept: text/lino` unless the caller asked for another representation;
- send `Content-Type: text/lino` with encoded bodies;
- decode a response according to the response `Content-Type` rather than the
  requested one;
- raise a typed error carrying the decoded problem details for any `4xx`/`5xx`;
- treat `204` and an empty body as the absence of a representation, not as `null`.

## 11. Conformance checklist

An implementation conforms when it provides all of:

1. `text/lino` request decoding and response encoding.
2. `text/lino-line` and `text/lino-compact` as negotiable alternatives.
3. `application/json` fallback.
4. `Accept`-driven negotiation with quality values, `406` and `Vary: Accept`.
5. `415` for unsupported request media types.
6. `GET`, `HEAD`, `OPTIONS`, `POST`, `PUT`, `PATCH`, `DELETE` with the semantics of §4.1.
7. Automatic `HEAD`, automatic `OPTIONS` and `405` with `Allow`.
8. RFC 9457 problem details in LINO for every error path.
9. Collection envelope with pagination, filtering, sorting and sparse fieldsets.
10. `ETag`, `If-None-Match`, `If-Match`, `304`, `412`, `428`.
11. CORS middleware.
12. Service description at `/.well-known/lino-api` and OpenAPI at `/.well-known/openapi.json`.
13. A client library meeting §10.
