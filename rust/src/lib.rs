//! A REST API framework and client that speak Links Notation instead of JSON.
//!
//! Everything the HTTP standards expect of a REST service — content negotiation,
//! conditional requests, problem details, collection pagination, automatic
//! `HEAD`/`OPTIONS`/`405`, CORS, a service description and an OpenAPI document —
//! is provided out of the box, with LINO as the default wire format and JSON as
//! a fallback. The wire protocol is defined in `docs/spec/README.md`, and the
//! JavaScript, Python and Rust packages speak it byte for byte alike, so the
//! three implementations produce the same entity tags.

// Every fallible operation in this crate reports a `LinoHttpError`, because that
// is what becomes a problem details response. It is larger than clippy's
// threshold for an error type, and boxing it at every call site would cost more
// in noise than it saves in moved bytes.
#![allow(clippy::result_large_err)]

pub mod app;
pub mod codec;
pub mod collection;
pub mod cors;
pub mod description;
pub mod etag;
pub mod headers;
pub mod media_type;
pub mod middleware;
pub mod problem;
pub mod query;
pub mod request;
pub mod resource;
pub mod response;
pub mod router;
pub mod store;
pub mod value;
