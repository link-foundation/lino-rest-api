"""Tests for the route registry (specification sections 4.1 and 9)."""

from lino_rest_api.router import RouteTable, compile_path_pattern


def test_path_patterns_match_parameters_and_tolerate_a_trailing_slash():
    matcher = compile_path_pattern("/items/:id")
    assert matcher.match("/items/42")
    assert matcher.match("/items/42/")
    assert not matcher.match("/items")
    assert not matcher.match("/items/42/tags")


def test_a_dot_in_a_path_is_matched_literally():
    matcher = compile_path_pattern("/.well-known/openapi.json")
    assert matcher.match("/.well-known/openapi.json")
    assert not matcher.match("/.well-known/openapiXjson")


def test_a_matched_path_yields_its_parameters():
    table = RouteTable()
    table.register("GET", "/items/:id")
    entry, params = table.match("/items/42")
    assert entry.pattern == "/items/:id"
    assert params == {"id": "42"}
    assert table.match("/missing") is None


def test_options_is_always_allowed_and_head_follows_get():
    table = RouteTable()
    table.register("GET", "/items")
    table.register("POST", "/items")
    assert table.allowed_methods("/items") == ["GET", "HEAD", "OPTIONS", "POST"]


def test_a_path_without_get_does_not_advertise_head():
    table = RouteTable()
    table.register("POST", "/jobs")
    assert table.allowed_methods("/jobs") == ["OPTIONS", "POST"]


def test_an_unknown_path_has_no_allowed_methods():
    assert RouteTable().allowed_methods("/missing") is None


def test_the_registry_renders_the_routes_of_a_service_description():
    table = RouteTable()
    table.register("GET", "/items", {"summary": "List items"})
    table.register("GET", "/health")
    assert table.describe() == [
        {"path": "/health", "methods": ["GET", "HEAD", "OPTIONS"]},
        {
            "path": "/items",
            "methods": ["GET", "HEAD", "OPTIONS"],
            "summary": "List items",
        },
    ]
