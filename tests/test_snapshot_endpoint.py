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


async def test_snapshot_import(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "test",
        "nodes": [{"id": "a", "kind": "file", "label": "a.py"}],
        "edges": [],
    }
    resp = await client.post("/v1/projects/test/snapshot", json=payload)
    assert resp.status == 200
    body = await resp.json()
    assert body["project_id"] == "test"
    assert body["status"] == "imported"
    assert body["nodes"] == 1
    assert body["edges"] == 0


async def test_snapshot_rejects_bad_version(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v0",
        "project_id": "test",
        "nodes": [],
        "edges": [],
    }
    resp = await client.post("/v1/projects/test/snapshot", json=payload)
    assert resp.status == 400
    body = await resp.json()
    assert "unsupported snapshot version" in body["error"]


async def test_snapshot_maps_edge_kinds(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "edge-test",
        "nodes": [
            {"id": "f:auth.py", "kind": "file", "label": "auth.py", "path": "auth.py"},
            {"id": "fn:login", "kind": "function", "label": "login", "path": "auth.py", "line": 12, "name": "login"},
        ],
        "edges": [
            {"id": "e:1", "kind": "contains", "source": "f:auth.py", "target": "fn:login", "line": 12},
            {"id": "e:2", "kind": "call", "source": "fn:login", "target": "f:auth.py"},
        ],
    }
    resp = await client.post("/v1/projects/edge-test/snapshot", json=payload)
    assert resp.status == 200
    body = await resp.json()
    assert body["nodes"] == 2
    assert body["edges"] == 2


async def test_project_status(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "status-test",
        "nodes": [{"id": "a", "kind": "file", "label": "a.py"}],
        "edges": [],
    }
    await client.post("/v1/projects/status-test/snapshot", json=payload)
    resp = await client.get("/v1/projects/status-test/status")
    assert resp.status == 200
    body = await resp.json()
    assert body["project_id"] == "status-test"
    assert body["status"] == "ready"
    assert body["nodes"] == 1


async def test_project_status_missing(client: TestClient):
    resp = await client.get("/v1/projects/no-such-project/status")
    assert resp.status == 404
    body = await resp.json()
    assert body["error"] == "project_not_found"


async def test_exec_result_received(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "exec-test",
        "nodes": [{"id": "a", "kind": "file", "label": "a.py"}],
        "edges": [],
    }
    await client.post("/v1/projects/exec-test/snapshot", json=payload)
    resp = await client.post(
        "/v1/projects/exec-test/exec-result",
        json={"opId": 1, "ok": True, "value": {"passed": True}, "error": None},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "received"


async def test_exec_result_missing_project(client: TestClient):
    resp = await client.post(
        "/v1/projects/no-such-project/exec-result",
        json={"opId": 1, "ok": True, "value": {}, "error": None},
    )
    assert resp.status == 404


async def test_snapshot_rejects_absolute_path(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "abs-test",
        "nodes": [
            {"id": "a", "kind": "file", "label": "a.py", "path": "/etc/passwd"},
        ],
        "edges": [],
    }
    resp = await client.post("/v1/projects/abs-test/snapshot", json=payload)
    assert resp.status == 400
    body = await resp.json()
    assert "absolute or parent-relative path rejected" in body["error"]


async def test_snapshot_rejects_parent_relative_path(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "rel-test",
        "nodes": [
            {"id": "a", "kind": "file", "label": "a.py", "path": "../secrets.py"},
        ],
        "edges": [],
    }
    resp = await client.post("/v1/projects/rel-test/snapshot", json=payload)
    assert resp.status == 400


async def test_snapshot_rejects_windows_drive_path(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "win-test",
        "nodes": [
            {"id": "a", "kind": "file", "label": "a.py", "path": "C:\\Windows\\x.py"},
        ],
        "edges": [],
    }
    resp = await client.post("/v1/projects/win-test/snapshot", json=payload)
    assert resp.status == 400


async def test_snapshot_accepts_project_path(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "path-test",
        "project_path": "/tmp/rgi-path-test-project",
        "nodes": [{"id": "a", "kind": "file", "label": "a.py"}],
        "edges": [],
    }
    resp = await client.post("/v1/projects/path-test/snapshot", json=payload)
    assert resp.status == 200
    # The server and snapshot modules captured the same singleton at import time;
    # the autouse fixture replaces project_store_module.STORE, so read rgi.server.STORE.
    project = RGI_STORE.get("path-test")
    assert project is not None
    assert project.path == "/tmp/rgi-path-test-project"


async def test_snapshot_rejects_relative_project_path(client: TestClient):
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "badpath-test",
        "project_path": "relative/path",
        "nodes": [],
        "edges": [],
    }
    resp = await client.post("/v1/projects/badpath-test/snapshot", json=payload)
    assert resp.status == 400
    body = await resp.json()
    assert "project_path must be an absolute" in body["error"]
