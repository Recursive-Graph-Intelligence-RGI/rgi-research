import pytest
from aiohttp.test_utils import TestClient, TestServer

from rgi.api import project_store as project_store_module
from rgi.api.snapshot import import_snapshot
from rgi.server import RGIServer


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


async def test_security_scan_finds_hardcoded_secret(client: TestClient, tmp_path):
    p = tmp_path / "secret.py"
    p.write_text("API_KEY = 'supersecret123456'\n")
    import_snapshot(
        {"version": "rgi-graph-snapshot-v1", "nodes": [], "edges": []},
        "sec",
        path=str(tmp_path),
    )
    resp = await client.post("/v1/projects/sec/security-scan", json={})
    assert resp.status == 200
    text = await resp.text()
    assert "hardcoded_secret" in text
    assert "security_scan_started" in text
    assert "Found 1 issue" in text


async def test_security_scan_missing_project(client: TestClient):
    resp = await client.post("/v1/projects/no-such/security-scan", json={})
    assert resp.status == 200
    text = await resp.text()
    assert "project not found" in text


async def test_security_scan_override_path(client: TestClient, tmp_path):
    p = tmp_path / "override.py"
    p.write_text("PASSWORD = 'hunter2'\n")
    import_snapshot(
        {"version": "rgi-graph-snapshot-v1", "nodes": [], "edges": []},
        "override",
        path=None,
    )
    resp = await client.post(
        "/v1/projects/override/security-scan",
        json={"path": str(tmp_path)},
    )
    assert resp.status == 200
    text = await resp.text()
    assert "hardcoded_secret" in text
