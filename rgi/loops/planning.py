"""Planning loop: decomposes objectives, proposes subgraphs."""
from rgi.core.models import CognitiveGraph, CognitiveNode, NodeType


def initialize(graph: CognitiveGraph, proposal: dict) -> None:
    objective = proposal["objective"]
    node = CognitiveNode(
        type=NodeType.REASONING,
        content=f"Decompose objective into specialized analysis subgraphs: {objective}",
        parent_graph_id=graph.id,
    )
    graph.nodes[node.id] = node
