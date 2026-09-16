//! A complete Links Notation REST service and a client that talks to it.
//!
//! Run with `cargo run --example basic_usage` from the `rust` directory. The
//! example starts a server on an ephemeral port, drives every part of the
//! protocol through the client and prints the wire representations, so the
//! output doubles as a protocol tour.

// A handler reports a `LinoHttpError`, which is larger than clippy's threshold
// for an error type; the crate allows it at its root for the same reason.
#![allow(clippy::result_large_err)]

use std::sync::Arc;

use lino_rest_api::{
    BoundServer, CorsPolicy, LINO_CONTENT_TYPE, LinoApp, LinoClient, LinoClientError, MemoryStore,
    RequestOptions, ResourceOptions, ServiceInfo, boolean, create_lino_app, encode, int, object,
    string,
};

/// Build the service: one resource and one liveness probe.
fn build_app() -> LinoApp {
    let mut app = create_lino_app()
        .with_info(
            ServiceInfo::new("Tasks API", "1.0.0")
                .describing("A task list served as Links Notation instead of JSON"),
        )
        .with_cors(CorsPolicy::permissive());

    let tasks = Arc::new(MemoryStore::seeded([
        object([
            ("title", string("Write the specification")),
            ("done", boolean(true)),
            ("priority", int(1)),
        ]),
        object([
            ("title", string("Implement the server")),
            ("done", boolean(false)),
            ("priority", int(2)),
        ]),
        object([
            ("title", string("Implement the client")),
            ("done", boolean(false)),
            ("priority", int(3)),
        ]),
    ]));

    // One call registers list, create, get, replace, merge and delete, together
    // with automatic HEAD, automatic OPTIONS, 405, entity tags and problem
    // details.
    app.resource("/tasks", tasks, ResourceOptions::new().with_name("task"));
    app.get_fn("/health", "Liveness probe", |_request| {
        Ok(object([("status", string("ok"))]))
    });
    app
}

/// Print a labelled section.
fn section(title: &str) {
    println!("\n=== {title} ===");
}

/// Drive the running service through every part of the protocol.
async fn tour(base: &str) -> Result<(), LinoClientError> {
    let client = LinoClient::new(base);
    let plain = RequestOptions::new;

    section("The service describes itself");
    println!("{}", encode(&client.describe().await?));

    section("Create a task");
    let created = client
        .post(
            "/tasks",
            &object([
                ("title", string("Ship the release")),
                ("done", boolean(false)),
                ("priority", int(4)),
            ]),
            &plain(),
        )
        .await?;
    println!("status   {}", created.status);
    println!("location {}", created.location.clone().unwrap_or_default());
    println!("etag     {}", created.etag.clone().unwrap_or_default());
    println!("{}", encode(&created.value()));

    section("List, filter, sort and paginate");
    let page = client
        .list(
            "/tasks",
            &plain()
                .with_query("done", &boolean(false))
                .with_query_text("sort", "-priority")
                .with_query("limit", &int(2)),
        )
        .await?;
    println!("{}", encode(&page));

    section("The raw wire format");
    let raw = reqwest::Client::new()
        .get(format!("{base}/tasks/1"))
        .header("Accept", LINO_CONTENT_TYPE)
        .send()
        .await
        .expect("the service answers");
    println!(
        "content-type {}",
        raw.headers()
            .get("content-type")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
    );
    println!("{}", raw.text().await.expect("a readable body"));

    section("Conditional requests");
    let current = client.get("/tasks/1", &plain()).await?;
    let tag = current.etag.clone().unwrap_or_default();
    let cached = client
        .get("/tasks/1", &plain().if_none_match(tag.clone()))
        .await?;
    println!("unchanged    {} (nothing was transferred)", cached.status);

    let updated = client
        .patch(
            "/tasks/1",
            &object([("done", boolean(false))]),
            &plain().if_match(tag.clone()),
        )
        .await?;
    println!(
        "updated      {} with a new etag {}",
        updated.status,
        updated.etag.clone().unwrap_or_default()
    );

    if let Err(error) = client
        .patch(
            "/tasks/1",
            &object([("done", boolean(true))]),
            &plain().if_match(tag),
        )
        .await
    {
        println!(
            "lost update  {} {error}",
            error.status().unwrap_or_default()
        );
    }

    section("Errors are problem details, in Links Notation");
    if let Err(error) = client.get("/tasks/999", &plain()).await {
        if let Some(problem) = error.problem() {
            println!("{}", encode(problem));
        }
    }

    section("Allowed methods");
    println!(
        "/tasks     {}",
        client.options("/tasks", &plain()).await?.join(", ")
    );
    println!(
        "/tasks/1   {}",
        client.options("/tasks/1", &plain()).await?.join(", ")
    );

    section("Delete");
    let location = created.location.clone().unwrap_or_default();
    println!(
        "status {}",
        client.delete(&location, &plain()).await?.status
    );
    Ok(())
}

#[tokio::main]
async fn main() {
    let server = BoundServer::bind(build_app(), "127.0.0.1:0")
        .await
        .expect("an ephemeral port is available");
    let base = server.base_url();
    tokio::spawn(async move {
        let _ = server.serve().await;
    });

    tour(&base).await.expect("the tour completes");
}
