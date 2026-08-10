from rgi.core.engine import merge_subgraph_results
from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType,
    NodeState, NodeType,
)


def _make_graphs():
    parent = CognitiveGraph(loop_type=LoopType.PLANNING,
                            state=GraphState(objective="test"),
                            policy=GraphPolicy())
    child = CognitiveGraph(loop_type=LoopType.EXECUTION,
                           state=GraphState(objective="child"),
                           policy=GraphPolicy())
    return parent, child


def test_merge_drops_ungrounded_low_confidence_findings():
    """Legacy integration test: one kept, one dropped."""
    parent, child = _make_graphs()

    real = CognitiveNode(
        type=NodeType.VERIFICATION,
        content="real finding",
        parent_graph_id=child.id,
        state=NodeState.COMPLETED,
        confidence=0.9,
        result={"finding": {"kind": "real", "file": "x.py", "line": 1}},
    )
    noise = CognitiveNode(
        type=NodeType.REASONING,
        content="noise finding",
        parent_graph_id=child.id,
        state=NodeState.COMPLETED,
        confidence=0.6,
        result={"finding": {"kind": "noise"}},
    )
    child.nodes[real.id] = real
    child.nodes[noise.id] = noise

    merge_subgraph_results(parent, child)

    assert len(parent.memory_snapshot["merged_findings"]) == 1
    assert parent.memory_snapshot["merged_findings"][0]["kind"] == "real"


def test_merge_keeps_grounded_low_confidence_finding():
    """grounded=True is sufficient even when confidence < 0.85."""
    parent, child = _make_graphs()

    grounded = CognitiveNode(
        type=NodeType.VERIFICATION,
        content="grounded finding",
        parent_graph_id=child.id,
        state=NodeState.COMPLETED,
        confidence=0.6,
        result={"finding": {"kind": "grounded", "file": "x.py", "line": 1}},
    )
    child.nodes[grounded.id] = grounded

    merge_subgraph_results(parent, child)

    assert len(parent.memory_snapshot["merged_findings"]) == 1
    assert parent.memory_snapshot["merged_findings"][0]["kind"] == "grounded"


def test_merge_keeps_ungrounded_high_confidence_finding():
    """confidence >= 0.85 is sufficient even when grounded=False."""
    parent, child = _make_graphs()

    high_confidence = CognitiveNode(
        type=NodeType.REASONING,
        content="high confidence finding",
        parent_graph_id=child.id,
        state=NodeState.COMPLETED,
        confidence=0.9,
        result={"finding": {"kind": "high_confidence"}},
    )
    child.nodes[high_confidence.id] = high_confidence

    merge_subgraph_results(parent, child)

    assert len(parent.memory_snapshot["merged_findings"]) == 1
    assert parent.memory_snapshot["merged_findings"][0]["kind"] == "high_confidence"


def test_merge_drops_ungrounded_low_confidence_finding():
    """grounded=False and confidence < 0.85 means the finding is dropped."""
    parent, child = _make_graphs()

    low_confidence = CognitiveNode(
        type=NodeType.REASONING,
        content="low confidence finding",
        parent_graph_id=child.id,
        state=NodeState.COMPLETED,
        confidence=0.6,
        result={"finding": {"kind": "low_confidence"}},
    )
    child.nodes[low_confidence.id] = low_confidence

    merge_subgraph_results(parent, child)

    assert parent.memory_snapshot.get("merged_findings", []) == []
