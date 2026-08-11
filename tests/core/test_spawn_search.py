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


def test_decide_next_action_prefers_sweep_over_stop():
    graph = _make_graph()
    action = decide_next_action(graph, object())
    assert action is not None
    assert action.action_type == "execution_sweep"
