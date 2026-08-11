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
