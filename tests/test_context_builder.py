from rgi.core.context_builder import ContextBuilder
from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType, NodeType,
)


def _graph():
    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="Analyze authentication security"),
                       policy=GraphPolicy())
    return g


def test_context_includes_objective_and_content():
    g = _graph()
    n = CognitiveNode(type=NodeType.REASONING, content="analyze jwt", parent_graph_id=g.id)
    g.nodes[n.id] = n
    ctx = ContextBuilder().build(n, g)
    assert "Analyze authentication security" in ctx
    assert "analyze jwt" in ctx


def test_context_selects_only_activated_neighbors():
    g = _graph()
    target = CognitiveNode(type=NodeType.REASONING, content="main task", parent_graph_id=g.id)
    hot = CognitiveNode(type=NodeType.TOOL, content="hot neighbor", parent_graph_id=g.id, activation=0.9)
    cold = CognitiveNode(type=NodeType.TOOL, content="cold neighbor", parent_graph_id=g.id, activation=0.1)
    for n in (target, hot, cold):
        g.nodes[n.id] = n
    ctx = ContextBuilder().build(target, g)
    assert "hot neighbor" in ctx
    assert "cold neighbor" not in ctx


def test_history_only_when_correcting():
    g = _graph()
    n = CognitiveNode(type=NodeType.REASONING, content="task", parent_graph_id=g.id)
    n.history.append({"state": "failed", "reason": "low_confidence"})
    g.nodes[n.id] = n
    ctx = ContextBuilder().build(n, g)
    assert "low_confidence" in ctx
    fresh = CognitiveNode(type=NodeType.REASONING, content="task2", parent_graph_id=g.id)
    g.nodes[fresh.id] = fresh
    assert "HISTORY" not in ContextBuilder().build(fresh, g)


def test_context_capped():
    g = _graph()
    n = CognitiveNode(type=NodeType.REASONING, content="x" * 50000, parent_graph_id=g.id)
    g.nodes[n.id] = n
    assert len(ContextBuilder().build(n, g)) <= ContextBuilder.MAX_CHARS
