from types import SimpleNamespace

import pytest

from rgi.cli import run_analysis
from rgi.core.engine import _execute_spawn_action
from rgi.core.models import CognitiveGraph, GraphPolicy, GraphState, LoopType
from rgi.core.spawn_search import SpawnAction


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


@pytest.mark.asyncio
async def test_frontier_arbitrate_action_triggers_arbitration():
    graph = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="test", max_iterations=10),
        policy=GraphPolicy(auto_spawn=True),
    )
    action = SpawnAction(
        action_type="frontier_arbitrate",
        objective="Request frontier arbitration to resolve deadlock",
        target_files=[],
        reason="deadlock:max_iterations_low_confidence",
        estimated_cost=1,
        metadata={"deadlock_signals": ["max_iterations_low_confidence"]},
    )
    harness = SimpleNamespace(
        frontier_config=SimpleNamespace(enabled=True),
    )
    progressed = await _execute_spawn_action(graph, harness, action)
    assert progressed is True
    assert graph.memory_snapshot.get("frontier_arbitrate_triggered") is True
