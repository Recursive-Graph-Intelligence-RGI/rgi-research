import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from rgi.api import project_store as project_store_module
from rgi.server import RGIServer, STORE as RGI_STORE


@pytest.fixture
async def client():
    server = RGIServer(host="127.0.0.1", port=0)
    app = server._make_app()
    test_server = TestServer(app)
    test_client = TestClient(test_server)
    await test_client.start_server()
    yield test_client
    await test_client.close()


@pytest.fixture(autouse=True)
def reset_store():
    project_store_module.STORE = project_store_module.ProjectStore()
    yield


async def test_health_ok(client: TestClient):
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "ok"


async def test_foreign_host_rejected(client: TestClient):
    resp = await client.get("/health", headers={"Host": "evil.example.com"})
    assert resp.status == 403
    body = await resp.json()
    assert body["error"] == "forbidden_host"


async def test_foreign_origin_rejected(client: TestClient):
    resp = await client.get(
        "/health", headers={"Origin": "https://evil.example.com"}
    )
    assert resp.status == 403
    body = await resp.json()
    assert body["error"] == "forbidden_origin"


async def test_localhost_origin_allowed_with_cors(client: TestClient):
    resp = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.status == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"


async def test_options_preflight(client: TestClient):
    resp = await client.options("/v1/projects/x/chat", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    })
    assert resp.status == 204
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"
    assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")


async def test_security_scan_unknown_project(client: TestClient):
    resp = await client.post("/v1/projects/nope/security-scan", json={})
    assert resp.status == 404
    body = await resp.json()
    assert body["error"] == "project_not_found"


async def test_security_scan_path_outside_project_rejected(client: TestClient):
    RGI_STORE.create(
        "p1", object(), path="/tmp/rgi-scan-test-project"
    )
    resp = await client.post(
        "/v1/projects/p1/security-scan", json={"path": "/etc/passwd"}
    )
    assert resp.status == 400
    body = await resp.json()
    assert "path outside project root" in body["error"]


async def test_mcp_initialize(client: TestClient):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.status == 200
    assert resp.headers.get("Mcp-Session-Id")
    body = await resp.json()
    assert body["result"]["serverInfo"]["name"] == "rgi"
    assert body["result"]["capabilities"]["tools"] is not None


async def test_mcp_tools_list_contains_security_scan(client: TestClient):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert resp.status == 200
    body = await resp.json()
    names = {t["name"] for t in body["result"]["tools"]}
    assert "security_scan" in names
    assert "read_file" in names


async def test_mcp_tools_call_executes_stat(client: TestClient, tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hello")
    resp = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "stat", "arguments": {"path": str(target)}},
        },
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["result"]["isError"] is False
    text = body["result"]["content"][0]["text"]
    assert "hello.txt" in text


async def test_mcp_tools_call_unknown_tool(client: TestClient):
    resp = await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}},
        },
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["error"]["code"] == -32602


async def test_mcp_unknown_method(client: TestClient):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 5, "method": "bogus", "params": {}},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["error"]["code"] == -32601


async def test_mcp_notifications_get_empty_response(client: TestClient):
    resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert resp.status == 200
