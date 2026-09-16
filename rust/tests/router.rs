//! The route registry, ported from `python/tests/test_router.py`
//! (specification sections 4.1 and 9).
//!
//! The Python package compiles a pattern into a matcher object; Rust matches a
//! pattern against a path directly, so `compile_path_pattern` is spelled
//! [`match_path`] here.

use lino_rest_api::router::{RouteDescription, RouteMeta, RouteTable, match_path};

#[test]
fn path_patterns_match_parameters_and_tolerate_a_trailing_slash() {
    assert!(match_path("/items/:id", "/items/42").is_some());
    assert!(match_path("/items/:id", "/items/42/").is_some());
    assert!(match_path("/items/:id", "/items").is_none());
    assert!(match_path("/items/:id", "/items/42/tags").is_none());
}

#[test]
fn a_dot_in_a_path_is_matched_literally() {
    assert!(match_path("/.well-known/openapi.json", "/.well-known/openapi.json").is_some());
    assert!(match_path("/.well-known/openapi.json", "/.well-known/openapiXjson").is_none());
}

#[test]
fn a_matched_path_yields_its_parameters() {
    let mut table = RouteTable::new();
    table.register("GET", "/items/:id", RouteMeta::default());
    let (entry, params) = table.match_path("/items/42").expect("the route matches");
    assert_eq!(entry.pattern, "/items/:id");
    assert_eq!(params["id"], "42");
    assert!(table.match_path("/missing").is_none());
}

#[test]
fn options_is_always_allowed_and_head_follows_get() {
    let mut table = RouteTable::new();
    table.register("GET", "/items", RouteMeta::default());
    table.register("POST", "/items", RouteMeta::default());
    assert_eq!(
        table.allowed_methods("/items"),
        Some(vec![
            "GET".to_string(),
            "HEAD".to_string(),
            "OPTIONS".to_string(),
            "POST".to_string(),
        ])
    );
}

#[test]
fn a_path_without_get_does_not_advertise_head() {
    let mut table = RouteTable::new();
    table.register("POST", "/jobs", RouteMeta::default());
    assert_eq!(
        table.allowed_methods("/jobs"),
        Some(vec!["OPTIONS".to_string(), "POST".to_string()])
    );
}

#[test]
fn an_unknown_path_has_no_allowed_methods() {
    assert_eq!(RouteTable::new().allowed_methods("/missing"), None);
}

#[test]
fn the_registry_renders_the_routes_of_a_service_description() {
    let mut table = RouteTable::new();
    table.register("GET", "/items", RouteMeta::summary("List items"));
    table.register("GET", "/health", RouteMeta::default());
    assert_eq!(
        table.describe(),
        vec![
            RouteDescription {
                path: "/health".to_string(),
                methods: vec!["GET".to_string(), "HEAD".to_string(), "OPTIONS".to_string()],
                summary: None,
            },
            RouteDescription {
                path: "/items".to_string(),
                methods: vec!["GET".to_string(), "HEAD".to_string(), "OPTIONS".to_string()],
                summary: Some("List items".to_string()),
            },
        ]
    );
}

#[test]
fn registering_a_method_twice_replaces_its_metadata() {
    let mut table = RouteTable::new();
    table.register("GET", "/items", RouteMeta::summary("Old"));
    table.register("GET", "/items", RouteMeta::summary("List items"));
    assert_eq!(table.entries().len(), 1);
    assert_eq!(table.describe()[0].summary.as_deref(), Some("List items"));
}

#[test]
fn removing_the_last_method_removes_the_route() {
    let mut table = RouteTable::new();
    table.register("GET", "/items", RouteMeta::default());
    table.register("POST", "/items", RouteMeta::default());
    table.remove("POST", "/items");
    assert!(
        table
            .find("/items")
            .expect("the route is still there")
            .has_method("GET")
    );
    table.remove("GET", "/items");
    assert!(table.find("/items").is_none());
}

#[test]
fn a_wildcard_segment_swallows_the_rest_of_the_path() {
    let params = match_path("/files/*path", "/files/a/b/c").expect("the wildcard matches");
    assert_eq!(params["path"], "a/b/c");
}
