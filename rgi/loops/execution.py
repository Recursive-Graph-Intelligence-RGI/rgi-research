"""Execution loop: runs tools, reasons over their output."""
from rgi.core.models import CognitiveEdge, CognitiveGraph, CognitiveNode, NodeType


def _pick_tool(objective: str) -> str:
    lowered = objective.lower()
    if "jwt" in lowered:
        return "check_jwt_usage"
    if "secret" in lowered or "config" in lowered:
        return "find_hardcoded_secrets"
    return "grep_security_patterns"


def initialize(graph: CognitiveGraph, proposal: dict) -> None:
    objective = proposal["objective"]
    target_path = proposal.get("target_path", "./sample_project")

    parse_node = CognitiveNode(
        type=NodeType.TOOL,
        content=f"Parse source code for: {objective}",
        parent_graph_id=graph.id,
        metadata={"tool": "parse_python_file", "params": {"path": target_path}},
    )
    security_tool = _pick_tool(objective)
    security_node = CognitiveNode(
        type=NodeType.TOOL,
        content=f"Run {security_tool} for: {objective}",
        parent_graph_id=graph.id,
        metadata={"tool": security_tool,
                  "params": {"path": target_path, "keywords": objective.lower().split()}},
    )
    reasoning_node = CognitiveNode(
        type=NodeType.REASONING,
        content=f"Analyze findings for {objective}",
        parent_graph_id=graph.id,
    )
    for node in (parse_node, security_node, reasoning_node):
        graph.nodes[node.id] = node
    graph.edges.append(CognitiveEdge(source=parse_node.id, target=reasoning_node.id,
                                     edge_type="flow"))
    graph.edges.append(CognitiveEdge(source=security_node.id, target=reasoning_node.id,
                                     edge_type="flow"))
