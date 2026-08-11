import os
from types import SimpleNamespace

from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType,
    NodeState, NodeType,
)
from rgi.core.spawn_search import (
    SpawnAction, SpawnNode, decide_next_action, estimate_value,
    generate_candidate_actions,
)


def test_spawn_action_has_required_fields():
    action = SpawnAction(
        action_type="execution_sweep",
        objective="Analyze db.py",
        target_files=["db.py"],
        reason="coverage_gap",
        estimated_cost=3,
        metadata={"loop_type": "execution"},
    )
    assert action.action_type == "execution_sweep"
    assert action.estimated_cost == 3


def test_spawn_node_defaults():
    action = SpawnAction("stop", "", [], "stop", 0, {})
    node = SpawnNode(state_snapshot={}, action=action, parent=None, children=[])
    assert node.visits == 0
    assert node.total_value == 0.0


def _make_graph():
    graph = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="test", max_iterations=10),
        policy=GraphPolicy(auto_spawn=True),
    )
    graph.memory_snapshot["world_model"] = {
        "files": ["a.py", "b.py"],
    }
    return graph


def test_generates_stop_action():
    graph = _make_graph()
    actions = generate_candidate_actions(graph, object())
    assert any(a.action_type == "stop" for a in actions)


def test_generates_execution_sweep_for_uncovered_files():
    graph = _make_graph()
    actions = generate_candidate_actions(graph, object())
    sweep = [a for a in actions if a.action_type == "execution_sweep"]
    assert len(sweep) == 1
    assert "a.py" in sweep[0].target_files


def test_stop_action_has_zero_value():
    graph = _make_graph()
    stop = SpawnAction("stop", "", [], "stop", 0, {})
    assert estimate_value(graph, stop) == 0.0


async def test_decide_next_action_prefers_sweep_over_stop():
    graph = _make_graph()
    action = await decide_next_action(graph, object())
    assert action is not None
    assert action.action_type == "execution_sweep"


def test_generates_verify_tool_action():
    graph = _make_graph()
    tool_node = CognitiveNode(
        type=NodeType.TOOL,
        content="scan",
        parent_graph_id=graph.id,
        state=NodeState.COMPLETED,
        result={"findings": [{"kind": "sql_injection", "file": "db.py", "line": 5}]},
        metadata={"tool": "security_scan", "verification_queued": False},
    )
    graph.nodes[tool_node.id] = tool_node

    harness = SimpleNamespace(
        tool_registry=SimpleNamespace(
            get_tool=lambda name: SimpleNamespace(verifier={"objective_template": "Verify {kind}"})
        )
    )
    actions = generate_candidate_actions(graph, harness)
    verify = [a for a in actions if a.action_type == "verify_tool"]
    assert len(verify) == 1
    assert verify[0].metadata["target_findings"][0]["kind"] == "sql_injection"


def test_generates_repl_explore_action():
    graph = _make_graph()
    reason_node = CognitiveNode(
        type=NodeType.REASONING,
        content="maybe bad",
        parent_graph_id=graph.id,
        state=NodeState.COMPLETED,
        confidence=0.4,
        result={"finding": {"kind": "suspicious", "detail": "?"}},
    )
    graph.nodes[reason_node.id] = reason_node
    actions = generate_candidate_actions(graph, object())
    repl = [a for a in actions if a.action_type == "repl_explore"]
    assert len(repl) == 1
