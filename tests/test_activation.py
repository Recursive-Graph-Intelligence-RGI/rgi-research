from rgi.core.models import (
    CognitiveEdge, CognitiveGraph, CognitiveNode, GraphPolicy, GraphState,
    LoopType, NodeType,
)
from rgi.memory.activation import ActivationEngine


def _graph():
    g = CognitiveGraph(
        loop_type=LoopType.KNOWLEDGE,
        state=GraphState(objective="x"),
        policy=GraphPolicy(),
    )
    a = CognitiveNode(type=NodeType.MEMORY, content="JWTManager handles authentication security tokens",
                      parent_graph_id=g.id)
    b = CognitiveNode(type=NodeType.MEMORY, content="SessionStore keeps session data",
                      parent_graph_id=g.id)
    c = CognitiveNode(type=NodeType.MEMORY, content="PaymentGateway processes payments",
                      parent_graph_id=g.id)
    for n in (a, b, c):
        g.nodes[n.id] = n
    g.edges.append(CognitiveEdge(source=a.id, target=b.id, edge_type="dependency"))
    return g, a, b, c


def test_keyword_seeding_and_threshold():
    g, a, b, c = _graph()
    scores = ActivationEngine().propagate(g, "authentication security")
    assert scores[a.id] > 0.5          # directly relevant
    assert scores[c.id] < 0.5          # unrelated stays dark
    assert scores[a.id] > scores[c.id]


def test_one_hop_propagation():
    g, a, b, c = _graph()
    scores = ActivationEngine().propagate(g, "authentication tokens")
    assert scores[b.id] > 0.0          # lit up via edge from a
    assert scores[b.id] < scores[a.id] or scores[b.id] <= 1.0


def test_history_bonus():
    g, a, b, c = _graph()
    c.history.append({"correction_success": True})
    scores = ActivationEngine().propagate(g, "unrelated query")
    assert scores[c.id] == 0.1
