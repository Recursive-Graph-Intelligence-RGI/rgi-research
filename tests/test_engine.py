from rgi.core.engine import execute_graph
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeState,
)
from rgi.loops import initialize_graph_nodes
from rgi.reasoning.llm_client import MockLLMClient


def _harness(tmp_path):
    return Harness(HarnessConfig(data_dir=str(tmp_path), llm_client=MockLLMClient()))


async def test_execution_graph_runs_tool_then_reasoning(tmp_path):
    h = _harness(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    (target / "auth.py").write_text("import jwt\njwt.decode('t', 'k')\n")
    h.config.target_path = str(target)
    h.gate.allowed_root = target

    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="JWT Security Analysis"),
                       policy=GraphPolicy(auto_spawn=False, require_verification=False))
    initialize_graph_nodes(g, {"objective": "JWT Security Analysis", "target_path": str(target)})
    h.graphs[g.id] = g

    done = await execute_graph(g, h)
    assert done.state.status == "completed"
    states = {n.type.value: n.state for n in done.nodes.values()}
    assert states["tool"] == NodeState.COMPLETED
    assert states["reasoning"] == NodeState.COMPLETED
    reasoning = next(n for n in done.nodes.values() if n.type.value == "reasoning")
    assert reasoning.result["finding"]


async def test_planning_graph_spawns_children_from_suggestions(tmp_path):
    h = _harness(tmp_path)
    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="Analyze authentication security"),
                          policy=GraphPolicy())
    initialize_graph_nodes(root, {"objective": "Analyze authentication security"})
    h.graphs[root.id] = root

    done = await execute_graph(root, h)
    assert len(done.subgraph_ids) == 2   # JWT + Session from mock script
    children = [h.get_graph(sid) for sid in done.subgraph_ids]
    assert all(c.loop_type == LoopType.EXECUTION for c in children)
    assert all(c.state.status in ("completed", "failed") for c in children)
    assert done.memory_snapshot.get("merged_findings")


async def test_stagnation_guard_fails_empty_graph(tmp_path):
    h = _harness(tmp_path)
    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="nothing matches this"),
                       policy=GraphPolicy(auto_spawn=False, require_verification=False))
    h.graphs[g.id] = g
    done = await execute_graph(g, h)
    assert done.state.status == "failed"
    assert done.state.iteration < done.state.max_iterations  # did not spin
