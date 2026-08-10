import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

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


async def test_health(client: TestClient):
    resp = await client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"


async def test_analyze_requires_path_and_objective(client: TestClient):
    resp = await client.post("/analyze", json={})
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


async def test_analyze_creates_job(client: TestClient):
    with patch("rgi.server.run_analysis", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"status": "completed", "findings": []}
        with tempfile.TemporaryDirectory() as tmp:
            resp = await client.post(
                "/analyze",
                json={"path": tmp, "objective": "test", "mock": True},
            )
            assert resp.status == 200
            data = await resp.json()
            assert "job_id" in data
            assert data["status"] == "pending"

            # Wait briefly for the background task to call run_analysis.
            for _ in range(50):
                await asyncio.sleep(0.05)
                status_resp = await client.get(f"/jobs/{data['job_id']}/status")
                status = await status_resp.json()
                if status["status"] in ("completed", "failed"):
                    break

            mock_run.assert_awaited_once()
            result_resp = await client.get(f"/jobs/{data['job_id']}/result")
            assert result_resp.status == 200
            result = await result_resp.json()
            assert result["status"] == "completed"


async def test_status_for_unknown_job(client: TestClient):
    resp = await client.get("/jobs/unknown/status")
    assert resp.status == 404


async def test_result_for_unknown_job(client: TestClient):
    resp = await client.get("/jobs/unknown/result")
    assert resp.status == 404


async def test_result_not_ready(client: TestClient):
    async def never_return(*args, **kwargs):
        await asyncio.Event().wait()

    with patch("rgi.server.run_analysis", new_callable=AsyncMock) as mock_run:
        mock_run.side_effect = never_return
        with tempfile.TemporaryDirectory() as tmp:
            resp = await client.post(
                "/analyze",
                json={"path": tmp, "objective": "test", "mock": True},
            )
            data = await resp.json()
            result_resp = await client.get(f"/jobs/{data['job_id']}/result")
            assert result_resp.status == 409
