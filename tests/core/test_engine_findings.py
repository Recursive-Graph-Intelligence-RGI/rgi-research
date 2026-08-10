from rgi.core.engine import merge_subgraph_results
from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType,
    NodeState, NodeType,
)


def test_merge_drops_ungrounded_low_confidence_findings():
    parent = CognitiveGraph(loop_type=LoopType.PLANNING,
                            state=GraphState(objective="test"),
                            policy=GraphPolicy())
    child = CognitiveGraph(loop_type=LoopType.EXECUTION,
                           state=GraphState(objective="child"),
                           policy=GraphPolicy())

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
