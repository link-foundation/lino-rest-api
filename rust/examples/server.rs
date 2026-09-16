//! A service left running, so that it can be driven with `curl`.
//!
//! Run with `cargo run --example server` from the `rust` directory, then:
//!
//! ```bash
//! curl -H 'Accept: text/lino' http://localhost:8000/tasks
//! curl -H 'Accept: text/lino' http://localhost:8000/.well-known/lino-api
//! curl -X POST http://localhost:8000/tasks \
//!   -H 'Content-Type: text/lino' \
//!   --data $'(\n  title "Ship it"\n  done false\n)'
//! ```
//!
//! The address may be given as the first argument; it defaults to `0.0.0.0:8000`.

// A handler reports a `LinoHttpError`, which is larger than clippy's threshold
// for an error type; the crate allows it at its root for the same reason.
#![allow(clippy::result_large_err)]

use std::sync::Arc;

use lino_rest_api::{
    CorsPolicy, MemoryStore, ResourceOptions, ServiceInfo, boolean, create_lino_app, object, serve,
    string,
};

#[tokio::main]
async fn main() -> std::io::Result<()> {
    let address = std::env::args()
        .nth(1)
        .unwrap_or("0.0.0.0:8000".to_string());

    let mut app = create_lino_app()
        .with_info(
            ServiceInfo::new("Tasks API", "1.0.0")
                .describing("A task list served as Links Notation instead of JSON"),
        )
        .with_cors(CorsPolicy::permissive());

    let tasks = Arc::new(MemoryStore::seeded([object([
        ("title", string("Write the specification")),
        ("done", boolean(true)),
    ])]));
    app.resource("/tasks", tasks, ResourceOptions::new().with_name("task"));
    app.get_fn("/health", "Liveness probe", |_request| {
        Ok(object([("status", string("ok"))]))
    });

    println!("Serving the Tasks API on http://{address}");
    serve(app, &address).await
}
