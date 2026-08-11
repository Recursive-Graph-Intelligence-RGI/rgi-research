import pytest

from rgi.cli import run_analysis


@pytest.mark.asyncio
async def test_spawn_search_mock_run_completes(monkeypatch, tmp_path):
    monkeypatch.setenv("RGI_SPAWN_SEARCH", "1")
    report_path = tmp_path / "spawn_search_report.json"
    report = await run_analysis(
        "sample_project", "find security vulnerabilities",
        str(report_path), mock=True,
        provider="ollama", model="qwen2.5:1.5b", max_llm_calls=20,
    )
    assert report["status"] == "completed"


@pytest.mark.asyncio
async def test_spawn_search_disabled_mock_run_completes(monkeypatch, tmp_path):
    monkeypatch.delenv("RGI_SPAWN_SEARCH", raising=False)
    report_path = tmp_path / "default_report.json"
    report = await run_analysis(
        "sample_project", "find security vulnerabilities",
        str(report_path), mock=True,
        provider="ollama", model="qwen2.5:1.5b", max_llm_calls=20,
    )
    assert report["status"] == "completed"
