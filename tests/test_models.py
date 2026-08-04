from rgi.core.models import (
    CognitiveGraph, CognitiveNode, CognitiveEdge, GraphState, GraphPolicy,
    NodeType, LoopType, NodeState,
)


def test_node_defaults_and_validation():
    node = CognitiveNode(
        type=NodeType.REASONING, content="analyze auth", parent_graph_id="g1"
    )
    assert node.state == NodeState.PENDING
    assert node.confidence == 0.0
    assert len(node.id) == 8


def test_confidence_bounds():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CognitiveNode(
            type=NodeType.TOOL, content="x", parent_graph_id="g1",
            confidence=1.5,
        )


def test_graph_roundtrip_json():
    graph = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="test objective"),
        policy=GraphPolicy(),
    )
    node = CognitiveNode(
        type=NodeType.MEMORY, content="entity", parent_graph_id=graph.id
    )
    graph.nodes[node.id] = node
    graph.edges.append(CognitiveEdge(source=node.id, target=node.id, edge_type="flow"))
    restored = CognitiveGraph.model_validate_json(graph.model_dump_json())
    assert restored.state.objective == "test objective"
    assert restored.nodes[node.id].content == "entity"
    assert restored.edges[0].edge_type == "flow"
