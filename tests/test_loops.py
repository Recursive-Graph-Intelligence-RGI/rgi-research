from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeType,
)
from rgi.loops import initialize_graph_nodes


def _graph(loop_type):
    return CognitiveGraph(loop_type=loop_type,
                          state=GraphState(objective="o"), policy=GraphPolicy())


def test_planning_initializer():
    g = _graph(LoopType.PLANNING)
    initialize_graph_nodes(g, {"objective": "Analyze authentication security"})
    reasoning = [n for n in g.nodes.values() if n.type == NodeType.REASONING]
    assert len(reasoning) == 1
    assert "Analyze authentication security" in reasoning[0].content


def test_execution_initializer_picks_jwt_tool():
    g = _graph(LoopType.EXECUTION)
    initialize_graph_nodes(g, {"objective": "JWT Security Analysis", "target_path": "./sample_project"})
    tools = [n for n in g.nodes.values() if n.type == NodeType.TOOL]
    tool_names = {t.metadata["tool"] for t in tools}
    assert "check_jwt_usage" in tool_names
    assert "parse_python_file" in tool_names  # always-on: reasoning must see code
    flow = [e for e in g.edges if e.edge_type == "flow"]
    assert len(flow) == 2  # both tools -> reasoning


def test_verification_initializer_builds_evidence():
    g = _graph(LoopType.VERIFICATION)
    initialize_graph_nodes(g, {
        "objective": "Verify: JWT Security Analysis",
        "target_findings": [{"finding": "missing exp", "confidence": 0.6}],
    })
    verifiers = [n for n in g.nodes.values() if n.type == NodeType.VERIFICATION]
    evidence = [n for n in g.nodes.values() if n.type == NodeType.MEMORY]
    assert len(verifiers) == 1 and len(evidence) == 1
    verifies = [e for e in g.edges if e.edge_type == "verifies"]
    assert verifies[0].source == verifiers[0].id
    assert verifies[0].target == evidence[0].id
