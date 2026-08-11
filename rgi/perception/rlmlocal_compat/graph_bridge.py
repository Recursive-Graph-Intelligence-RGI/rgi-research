"""Import a rlmlocal-style graph snapshot into a CognitiveGraph.

The snapshot format mirrors the output of rlmlocal-site's VectorStore / graph
layer: a JSON object with ``nodes`` and ``edges`` arrays. Each node carries
structural metadata (kind, name, file, line) and optional content; each edge
carries a relationship kind and optional symbol/weight.
"""
import json
from pathlib import Path

from rgi.core.models import (
    CognitiveEdge,
    CognitiveGraph,
    CognitiveNode,
    GraphPolicy,
    GraphState,
    LoopType,
    NodeType,
)


def import_rlmlocal_graph(path: Path) -> CognitiveGraph:
    """Load a rlmlocal graph snapshot and return a CognitiveGraph.

    Args:
        path: Path to the JSON snapshot file.

    Returns:
        A CognitiveGraph whose nodes are MEMORY entities and whose edges
        preserve the relationship kinds from the snapshot.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    graph = CognitiveGraph(
        loop_type=LoopType.KNOWLEDGE,
        state=GraphState(objective=f"Imported rlmlocal graph from {path}"),
        policy=GraphPolicy(auto_spawn=False, require_verification=False),
    )

    for n in data.get("nodes", []):
        node_id = n.get("id")
        if not node_id:
            continue
        kind = n.get("kind", "entity")
        name = n.get("name", "")
        content = n.get("content", f"{kind} {name}").strip()
        node = CognitiveNode(
            id=node_id,
            type=NodeType.MEMORY,
            content=content,
            confidence=1.0,
            parent_graph_id=graph.id,
            metadata={
                "kind": kind,
                "name": name,
                "file": n.get("file"),
                "line": n.get("line"),
                "span": n.get("span"),
            },
        )
        graph.nodes[node.id] = node

    valid_kinds = {"dependency", "flow", "feedback", "triggers", "verifies", "activates", "contains", "imports"}
    for e in data.get("edges", []):
        source = e.get("source")
        target = e.get("target")
        if source not in graph.nodes or target not in graph.nodes:
            continue
        kind = e.get("kind", "dependency")
        if kind not in valid_kinds:
            kind = "dependency"
        graph.edges.append(
            CognitiveEdge(
                source=source,
                target=target,
                edge_type=kind,
                weight=e.get("weight", 0.9),
                metadata={
                    "symbol": e.get("symbol"),
                    "line": e.get("line"),
                },
            )
        )

    return graph
