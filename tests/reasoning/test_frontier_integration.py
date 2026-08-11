import pytest
from rgi.reasoning.frontier_integration import (
    ArbitrationResult, FrontierConfig, FrontierIntegration, PlanResult,
    SynthesisResult,
)


def test_plan_result_defaults():
    r = PlanResult(
        strategy="breadth-first security audit",
        initial_subgraph_objectives=["Analyze JWT handling"],
        focus_areas=["auth.py"],
    )
    assert r.expected_findings == []


def test_arbitration_result_valid_decision():
    r = ArbitrationResult(decision="respawn", reasoning="local confidence stalled")
    assert r.spawn_objectives == []
    assert not r.escalate_to_user


def test_frontier_config_defaults():
    cfg = FrontierConfig()
    assert not cfg.enabled
    assert cfg.max_arbitration_calls == 2


@pytest.mark.asyncio
async def test_frontier_integration_disabled_returns_none():
    cfg = FrontierConfig(enabled=False)
    frontier = FrontierIntegration(cfg)
    plan = await frontier.plan_root("objective", {})
    assert plan is None
