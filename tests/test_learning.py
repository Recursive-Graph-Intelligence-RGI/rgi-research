import json
from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType, NodeState, NodeType,
)
from rgi.loops.learning import LearningEngine


def test_records_pathway(tmp_path):
    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="jwt analysis"),
                       policy=GraphPolicy())
    n = CognitiveNode(type=NodeType.REASONING, content="t", parent_graph_id=g.id,
                      state=NodeState.COMPLETED, confidence=0.9)
    g.nodes[n.id] = n
    g.state.status = "completed"
    engine = LearningEngine(tmp_path / "pathways.json")
    entry = engine.record_pathway(g)
    assert entry["outcome"] == "completed"
    assert entry["topology"]["node_types"] == ["reasoning"]
    data = json.loads((tmp_path / "pathways.json").read_text())
    assert len(data) == 1
    assert data[0]["avg_confidence"] == 0.9
