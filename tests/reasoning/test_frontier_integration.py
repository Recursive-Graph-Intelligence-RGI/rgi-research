import pytest
from rgi.reasoning.frontier_integration import (
    ArbitrationResult, FrontierConfig, FrontierIntegration, PlanResult,
    SynthesisResult,
)


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def reason(self, task: str, context: str) -> dict:
        self.calls.append((task, context))
        return self.response


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


@pytest.mark.asyncio
async def test_plan_root_uses_frontier_llm():
    fake = _FakeLLM({
        "strategy": "focus on auth",
        "initial_subgraph_objectives": ["JWT analysis"],
        "focus_areas": ["auth.py"],
        "expected_findings": ["weak secret"],
    })
    cfg = FrontierConfig(enabled=True, provider="kimi", model="kimi-k2")
    frontier = FrontierIntegration(cfg, llm_client=fake)
    result = await frontier.plan_root("Analyze auth security", {"auth.py": "JWT code"})
    assert result.strategy == "focus on auth"
    assert result.initial_subgraph_objectives == ["JWT analysis"]
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_arbitrate_returns_structured_result():
    fake = _FakeLLM({
        "decision": "respawn",
        "reasoning": "confidence stalled",
        "spawn_objectives": ["Re-analyze JWT"],
    })
    cfg = FrontierConfig(enabled=True)
    frontier = FrontierIntegration(cfg, llm_client=fake)
    result = await frontier.arbitrate({"findings": [], "contradictions": []})
    assert result.decision == "respawn"
    assert result.spawn_objectives == ["Re-analyze JWT"]


@pytest.mark.asyncio
async def test_synthesize_returns_report():
    fake = _FakeLLM({
        "summary": "Found weak secrets",
        "findings": [{"kind": "hardcoded_secret", "file": "config.py"}],
        "confidence": 0.95,
        "recommendations": ["Rotate secrets"],
    })
    cfg = FrontierConfig(enabled=True)
    frontier = FrontierIntegration(cfg, llm_client=fake)
    result = await frontier.synthesize({}, [])
    assert result is not None
    assert result.summary == "Found weak secrets"
    assert result.confidence == 0.95
