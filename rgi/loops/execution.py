"""Execution loop: runs tools, reasons over their output."""
from rgi.core.models import CognitiveEdge, CognitiveGraph, CognitiveNode, NodeType


def _pick_tool(objective: str) -> str:
    return "check_jwt_usage" if "jwt" in objective.lower() else "grep_security_patterns"


def initialize(graph: CognitiveGraph, proposal: dict) -> None:
    objective = proposal["objective"]
    target_path = proposal.get("target_path", "./sample_project")
    tool = _pick_tool(objective)

    tool_node = CognitiveNode(
        type=NodeType.TOOL,
        content=f"Run {tool} for: {objective}",
        parent_graph_id=graph.id,
        metadata={"tool": tool, "params": {"path": target_path, "keywords": objective.lower().split()}},
    )
    reasoning_node = CognitiveNode(
        type=NodeType.REASONING,
        content=f"Analyze findings for {objective}",
        parent_graph_id=graph.id,
    )
    graph.nodes[tool_node.id] = tool_node
    graph.nodes[reasoning_node.id] = reasoning_node
    graph.edges.append(CognitiveEdge(source=tool_node.id, target=reasoning_node.id,
                                     edge_type="flow"))
