"""Portable binary fixtures and byte transport regressions for issue #10."""
import json
from pathlib import Path

import httpx
import pytest
from links_notation import BinaryLinoCodec, DecodeLimits, Link

from lino_rest_api import (
    LINO_BINARY_CONTENT_TYPE as BINARY,
)
from lino_rest_api import (
    LINO_CONTENT_TYPE as TEXT,
)
from lino_rest_api import (
    AsyncLinoClient,
    LinoClient,
    LinoClientError,
    MemoryStore,
    compute_etag,
    create_lino_app,
    decode_from,
    encode_for,
)

from .helpers import serve

CASES = json.loads((Path(__file__).parent / 'fixtures/binary.json').read_text())


def test_portable_binary_values_and_golden_bytes():
    for case in CASES:
        body = encode_for(case['value'], BINARY)
        assert isinstance(body, bytes)
        assert body.hex() == case['hex']
        assert decode_from(body, BINARY) == case['value']
    shared = {'value': 1}
    decoded = decode_from(encode_for([shared, shared], BINARY), BINARY)
    assert decoded[0] is decoded[1]
    cycle = []
    cycle.append(cycle)
    decoded = decode_from(encode_for(cycle, BINARY), BINARY)
    assert decoded[0] is decoded


def test_binary_rejects_malformed_truncated_trailing_and_depth():
    body = encode_for({'ok': True}, BINARY)
    for packet in [b'\xff', body[:-1], body + b'\0']:
        with pytest.raises(ValueError):
            decode_from(packet, BINARY)
    codec = BinaryLinoCodec(limits=DecodeLimits(max_depth=128))
    node = Link('x', [])
    for _ in range(70):
        node = Link(None, [node])
    deep = codec.encode([node])
    with pytest.raises(ValueError, match='nesting'):
        decode_from(deep, BINARY)


async def test_binary_asgi_client_without_json():
    app = create_lino_app(supported=[TEXT, BINARY], max_body_bytes=4096)
    app.post('/echo', lambda request: request.body)
    app.get('/value', lambda request: CASES[-1]['value'])
    async with serve(app, accept=BINARY, content_type=BINARY) as s:
        response = await s.client.post('/echo', CASES[-1]['value'])
        assert response.data == CASES[-1]['value']
        assert response.headers['content-type'] == BINARY
        response = await s.client.get('/value')
        assert response.etag == compute_etag(encode_for(response.data, BINARY))
        assert (await s.client.get('/value', if_none_match=response.etag)).status == 304
        assert (await s.client.head('/value')).data is None
        with pytest.raises(LinoClientError) as caught:
            await s.client.get('/missing')
        assert caught.value.problem['status'] == 404
        for headers, body, status in [
            ({'accept': 'application/json'}, b'', 406),
            ({'accept': BINARY, 'content-type': 'application/json'}, b'{}', 415),
            ({'accept': BINARY, 'content-type': BINARY}, b'\xff', 400),
            ({'accept': BINARY, 'content-type': BINARY}, bytes(4097), 413),
        ]:
            response = await s.raw('/echo', 'POST', headers=headers, content=body)
            assert response.status_code == status
        assert (await s.client.describe())['media_types'] == [TEXT, BINARY]
        text_client = AsyncLinoClient(s.base, client=s.http, accept=TEXT, content_type=TEXT)
        assert (await text_client.post('/echo', {'ok': True})).data == {'ok': True}


def test_sync_client_uses_response_bytes():
    def echo(request):
        assert request.headers['content-type'] == BINARY
        return httpx.Response(200, content=request.content, headers={'content-type': BINARY})
    with httpx.Client(transport=httpx.MockTransport(echo)) as http:
        client = LinoClient('http://test', client=http, content_type=BINARY)
        assert client.post('/', CASES[-1]['value']).data == CASES[-1]['value']


async def test_fastapi_binary_request_and_response():
    from fastapi import FastAPI, Request

    from lino_rest_api.fastapi_adapter import LinoRequest, LinoResponse

    app = FastAPI()

    @app.post('/echo')
    async def echo(request: Request):
        return LinoResponse(await LinoRequest(request).body(), media_type=BINARY)

    async with serve(app, accept=BINARY, content_type=BINARY) as s:
        response = await s.client.post('/echo', CASES[-1]['value'])
        assert response.headers['content-type'] == BINARY
        assert response.data == CASES[-1]['value']


@pytest.mark.parametrize('case', json.loads(
    (Path(__file__).parent / 'fixtures/binary-limits.json').read_text()
))
def test_every_graph_budget_rejects_small_hostile_packet(case):
    with pytest.raises(ValueError, match='limit|budget|excessive|too many|depth|nesting'):
        decode_from(bytes.fromhex(case['hex']), BINARY)


async def test_fastapi_decorators_negotiate_binary_and_refuse_disabled_json():
    from lino_rest_api import LinoAPI
    api = LinoAPI(supported=[TEXT, BINARY], max_body_bytes=4096)

    @api.post('/echo')
    def echo(body):
        return body

    async with serve(api.get_fastapi_app(), accept=BINARY, content_type=BINARY) as s:
        assert (await s.client.post('/echo', CASES[-1]['value'])).data == CASES[-1]['value']
        response = await s.raw('/echo', 'POST',
                               headers={'accept': BINARY, 'content-type': 'application/json'},
                               content=b'{}')
        assert response.status_code == 415
        assert decode_from(response.content, BINARY)['status'] == 415
        response = await s.raw('/echo', 'POST', headers={'accept': 'application/json'})
        assert response.status_code == 406


async def test_binary_resource_etags_support_conditional_writes():
    app = create_lino_app(supported=[TEXT, BINARY])
    app.resource('/items', MemoryStore([{'name': 'old'}]))
    async with serve(app, accept=BINARY, content_type=BINARY) as s:
        first = await s.client.get('/items/1')
        assert first.etag == compute_etag(encode_for(first.data, BINARY))
        changed = await s.client.put('/items/1', {'name': 'new'}, if_match=first.etag)
        assert changed.data['name'] == 'new'
        with pytest.raises(LinoClientError) as caught:
            await s.client.put('/items/1', {'name': 'stale'}, if_match=first.etag)
        assert caught.value.status == 412
