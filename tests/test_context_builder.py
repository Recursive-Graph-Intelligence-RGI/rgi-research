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
    assert len(ContextBuilder().build(n, g)) <= (
        ContextBuilder.MAX_CHARS + ContextBuilder.SOURCE_MAX_CHARS
    )


def test_source_excerpt_gets_own_budget():
    """Regression (Run 9): reasoning nodes starved when tool-returned
    source competed with chatter for one 16k budget — files past the
    alphabetical cut vanished and the LLM vibed from fragments."""
    g = _graph()
    reasoning = CognitiveNode(type=NodeType.REASONING, content="analyze",
                              parent_graph_id=g.id)
    late_file_source = "===== zebra.py =====\n" + "secret = 'hunter2'\n" * 2000
    tool = CognitiveNode(
        type=NodeType.TOOL, content="parse", parent_graph_id=g.id, activation=0.9,
        result={"findings": [{"classes": [], "functions": [],
                              "source_excerpt": late_file_source}],
                "confidence": 1.0},
    )
    for n in (reasoning, tool):
        g.nodes[n.id] = n
    ctx = ContextBuilder().build(reasoning, g)
    assert "zebra.py" in ctx
    assert "hunter2" in ctx  # source survives even past 16k of chatter
    # source is extracted from the neighbor dump, not duplicated inline
    neighbor_section = ctx.split("NEIGHBORS:")[1].split("SOURCE CODE")[0]
    assert "hunter2" not in neighbor_section
