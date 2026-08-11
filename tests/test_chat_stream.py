import pytest
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock, patch

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


async def test_chat_requires_project(client: TestClient):
    resp = await client.post("/v1/projects/missing/chat", json={"message": "hi"})
    assert resp.status == 200
    text = await resp.text()
    assert "project not found" in text


async def test_chat_streams_findings_and_result(client: TestClient, tmp_path):
    import_snapshot(
        {"version": "rgi-graph-snapshot-v1", "nodes": [], "edges": []},
        "chat-test",
        path=str(tmp_path),
    )
    (tmp_path / "auth.py").write_text("API_KEY = 'supersecret123456'\n")

    fake_report = {
        "findings": [
            {
                "kind": "hardcoded_secret",
                "file": str(tmp_path / "auth.py"),
                "line": 1,
                "detail": "Hardcoded secret API_KEY",
            }
        ],
        "summary": "Found one hardcoded secret.",
    }

    with patch("rgi.api.chat_stream.run_analysis", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = fake_report
        resp = await client.post(
            "/v1/projects/chat-test/chat",
            json={"message": "Find secrets", "options": {"max_llm_calls": 2}},
        )
        assert resp.status == 200
        text = await resp.text()
        assert "thinking" in text
        assert "hardcoded_secret" in text
        assert "filesRead" in text
        assert "Found one hardcoded secret." in text

        mock_run.assert_awaited_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["path"] == str(tmp_path)
        assert call_kwargs["objective"] == "Find secrets"
        assert call_kwargs["max_llm_calls"] == 2
