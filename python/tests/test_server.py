"""
Tests that drive the application over a real socket.

Every other HTTP test in this suite runs the application in process through an
ASGI transport, which is fast but never touches a TCP connection, an HTTP parser
or the synchronous client. This module runs a real ``uvicorn`` server so that
those layers are covered too.
"""

import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from lino_rest_api import (
    LINO_CONTENT_TYPE,
    LinoApp,
    LinoClient,
    LinoClientError,
    MemoryStore,
    create_lino_app,
    decode,
)

#: How long to wait for the server to bind, in seconds.
STARTUP_TIMEOUT = 10.0


def build_app() -> LinoApp:
    """
    Build the application served over a real socket.

    Returns:
        Application under test
    """
    app = create_lino_app(title="Live API", version="1.0.0", cors=True)
    app.resource("/items", MemoryStore([{"name": "first"}]), name="item")
    app.get("/health", lambda request: {"status": "ok"}, {"summary": "Health check"})
    return app


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    """
    Run the application on an ephemeral port for the duration of the module.

    Yields:
        Base URL of the running server
    """
    config = uvicorn.Config(
        build_app(), host="127.0.0.1", port=0, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while not server.started:
        if time.monotonic() > deadline:  # pragma: no cover - only on a broken host
            server.should_exit = True
            raise TimeoutError("the test server did not start in time")
        time.sleep(0.01)

    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=STARTUP_TIMEOUT)


@pytest.fixture
def client(base_url: str) -> Iterator[LinoClient]:
    """
    Open a synchronous client against the running server.

    Args:
        base_url: Base URL of the running server

    Yields:
        Client under test
    """
    with LinoClient(base_url) as connected:
        yield connected


def test_the_server_answers_over_a_real_socket(client: LinoClient):
    response = client.get("/health")
    assert response.status == 200
    assert response.data == {"status": "ok"}
    assert response.response.headers["content-type"] == "text/lino; charset=utf-8"


def test_the_synchronous_client_drives_a_full_resource_lifecycle(client: LinoClient):
    created = client.post("/items", {"name": "second", "done": False})
    assert created.status == 201
    assert created.location == f"/items/{created.data['id']}"

    read = client.get(created.location)
    assert read.data == created.data
    assert read.etag == created.etag

    merged = client.patch(created.location, {"done": True}, if_match=read.etag)
    assert merged.data["done"] is True

    assert client.delete(created.location).status == 204
    with pytest.raises(LinoClientError) as raised:
        client.get(created.location)
    assert raised.value.status == 404


def test_the_synchronous_client_reads_the_description_and_the_methods(
    client: LinoClient,
):
    description = client.describe()
    assert description["info"]["title"] == "Live API"
    assert client.options("/health") == ["GET", "HEAD", "OPTIONS"]


def test_a_conditional_read_over_a_real_socket_answers_304(client: LinoClient):
    first = client.get("/items/1")
    cached = client.get("/items/1", if_none_match=first.etag)
    assert cached.status == 304
    assert cached.data is None


def test_a_raw_request_carries_the_expected_headers(base_url: str):
    import httpx

    response = httpx.get(
        f"{base_url}/items/1",
        headers={"Accept": LINO_CONTENT_TYPE, "Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["vary"]
    assert decode(response.text)["name"] == "first"
