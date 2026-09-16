"""Tests for cross-origin requests (specification section 8)."""

from lino_rest_api.cors import (
    DEFAULT_ALLOWED_HEADERS,
    DEFAULT_EXPOSED_HEADERS,
    cors_headers,
)
from lino_rest_api.middleware import append_vary


def test_content_type_and_accept_are_allowed_so_browsers_can_negotiate_lino():
    assert "Content-Type" in DEFAULT_ALLOWED_HEADERS
    assert "Accept" in DEFAULT_ALLOWED_HEADERS
    assert "If-Match" in DEFAULT_ALLOWED_HEADERS


def test_etag_and_link_are_exposed_so_clients_can_follow_the_protocol():
    assert "ETag" in DEFAULT_EXPOSED_HEADERS
    assert "Link" in DEFAULT_EXPOSED_HEADERS


def test_the_default_policy_allows_any_origin():
    headers = cors_headers({}, "https://example.com")
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "PATCH" in headers["Access-Control-Allow-Methods"]


def test_an_allow_list_reflects_the_request_origin():
    options = {"origin": ["https://example.com"]}
    allowed = cors_headers(options, "https://example.com")
    assert allowed["Access-Control-Allow-Origin"] == "https://example.com"
    assert cors_headers(options, "https://evil.example") == {}


def test_credentialed_requests_echo_the_origin():
    headers = cors_headers({"credentials": True}, "https://example.com")
    assert headers["Access-Control-Allow-Origin"] == "https://example.com"
    assert headers["Access-Control-Allow-Credentials"] == "true"


def test_enabling_cors_without_a_policy_uses_the_defaults():
    assert cors_headers(True, "https://example.com")["Access-Control-Allow-Origin"] == "*"


def test_append_vary_keeps_existing_field_names():
    headers: dict[str, str] = {}
    append_vary(headers, "Accept")
    append_vary(headers, "Origin")
    append_vary(headers, "accept")
    assert headers["Vary"] == "Accept, Origin"
