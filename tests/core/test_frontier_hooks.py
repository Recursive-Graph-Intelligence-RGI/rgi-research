import pytest
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import CognitiveGraph, GraphPolicy, GraphState, LoopType
from rgi.reasoning.frontier_integration import (
    ArbitrationResult, FrontierConfig, FrontierIntegration, PlanResult,
)
from rgi.loops import initialize_graph_nodes


class _FakeFrontier:
    def __init__(self):
        self.plan_calls = []

    async def plan_root(self, objective, world_model):
        self.plan_calls.append((objective, world_model))
        return PlanResult(
            strategy="test",
            initial_subgraph_objectives=["Sub-objective A"],
            focus_areas=["auth.py"],
        )


class _FakeLLM:
    async def reason(self, task: str, context: str) -> dict:
        return {
            "finding": {
                "kind": "summary",
                "severity": "info",
                "detail": "test finding",
                "file": "auth.py",
                "line": 1,
                "symbol": "test",
            },
            "confidence": 1.0,
            "reasoning": "test",
            "recommended_action": "none",
            "suggested_subgraphs": [],
        }


@pytest.mark.asyncio
async def test_engine_seeds_frontier_plan_subgraphs():
    from rgi.core.engine import execute_graph

    cfg = HarnessConfig(
        target_path="sample_project",
        frontier_config=FrontierConfig(enabled=True),
        llm_client=_FakeLLM(),
    )
    harness = Harness(cfg)
    harness.frontier = _FakeFrontier()
    root = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="Analyze auth"),
        policy=GraphPolicy(),
    )
    initialize_graph_nodes(root, {"objective": "Analyze auth"})
    root.memory_snapshot["world_model"] = {"auth.py": "jwt code"}
    harness.graphs[root.id] = root
    result = await execute_graph(root, harness)
    assert result.state.status in ("completed", "failed")
    assert len(harness.frontier.plan_calls) == 1


@pytest.mark.asyncio
async def test_arbitration_triggers_on_low_confidence_stall():
    from rgi.core.engine import execute_graph, needs_frontier_arbitration

    cfg = HarnessConfig(
        target_path="sample_project",
        max_llm_calls=100,
        frontier_config=FrontierConfig(enabled=True),
    )
    harness = Harness(cfg)
    arb_calls = []

    class _ArbFrontier:
        async def plan_root(self, objective, world_model):
            return PlanResult(strategy="test", initial_subgraph_objectives=[], focus_areas=[])

        async def arbitrate(self, state):
            arb_calls.append(state)
            return ArbitrationResult(decision="respawn", reasoning="low confidence", spawn_objectives=["Retry"])

    harness.frontier = _ArbFrontier()
    root = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="x", max_iterations=1, confidence_threshold=0.99),
        policy=GraphPolicy(),
    )
    initialize_graph_nodes(root, {"objective": "x"})
    harness.graphs[root.id] = root
    assert needs_frontier_arbitration(root, harness)
    await execute_graph(root, harness)
    assert len(arb_calls) == 1
