import os

import pytest

from rgi.cli import run_analysis


@pytest.mark.asyncio
async def test_spawn_search_mock_run_completes():
    os.environ["RGI_SPAWN_SEARCH"] = "1"
    report = await run_analysis(
        "sample_project", "find security vulnerabilities",
        "/tmp/rgi_spawn_search_mock.json", mock=True,
        provider="ollama", model="qwen2.5:1.5b", max_llm_calls=20,
    )
    assert report["status"] == "completed"
