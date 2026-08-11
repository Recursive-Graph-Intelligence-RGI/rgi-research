import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from rgi.api.sse import event_stream


async def _gen():
    yield {"kind": "token", "token": "hi"}
    yield {"kind": "thinking", "step": "planning"}


async def test_sse_writes_events():
    app = web.Application()
    app.router.add_get("/stream", lambda r: event_stream(r, _gen()))
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.get("/stream")
        assert resp.status == 200
        text = await resp.text()
        assert 'data: {"kind": "token", "token": "hi"}' in text
        assert 'data: {"kind": "thinking", "step": "planning"}' in text
        assert "data: [DONE]" in text
    finally:
        await client.close()
