"""Snapshot validation and import into a CognitiveGraph.

The snapshot format is the shared ``rgi-graph-snapshot-v1`` schema used between
RGI and rlmlocal-site.
"""
from typing import Any

from rgi.api.project_store import STORE, Project
from rgi.core.models import (
    CognitiveEdge,
    CognitiveGraph,
    CognitiveNode,
    GraphPolicy,
    GraphState,
    LoopType,
    NodeType,
)


SNAPSHOT_VERSION = "rgi-graph-snapshot-v1"


def _map_edge_kind(kind: str) -> str:
    """Map rlmlocal-site edge kinds to RGI CognitiveGraph edge types."""
    mapping = {
        "import": "imports",
        "call": "flow",
        "dataFlow": "flow",
        "reference": "dependency",
        "coChange": "feedback",
        "contains": "contains",
        "depends": "dependency",
    }
    return mapping.get(kind, "dependency")


def import_snapshot(data: dict[str, Any], project_id: str, path: str | None = None) -> Project:
    """Validate and import a snapshot, creating or updating a project.

    Raises:
        ValueError: If the snapshot version is unsupported or paths are absolute.
    """
    if data.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported snapshot version: {data.get('version')!r}")

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_ids = {n["id"] for n in nodes if "id" in n}

    graph = CognitiveGraph(
        loop_type=LoopType.KNOWLEDGE,
        state=GraphState(objective=f"Imported snapshot for {project_id}"),
        policy=GraphPolicy(auto_spawn=False, require_verification=False),
    )

    for n in nodes:
        node_id = n.get("id")
        if not node_id:
            continue
        content = n.get("content") or f"{n.get('kind', 'entity')} {n.get('label', '')}".strip()
        graph.nodes[node_id] = CognitiveNode(
            id=node_id,
            type=NodeType.MEMORY,
            content=content,
            confidence=float(n.get("confidence", 1.0)),
            parent_graph_id=graph.id,
            metadata={
                "kind": n.get("kind"),
                "label": n.get("label"),
                "name": n.get("name"),
                "file": n.get("path"),
                "line": n.get("line"),
                "span": n.get("span"),
                "language": n.get("language"),
                "embedding": n.get("embedding"),
            },
        )

    for e in edges:
        source = e.get("source")
        target = e.get("target")
        if source not in node_ids or target not in node_ids:
            continue
        kind = _map_edge_kind(e.get("kind", "dependency"))
        graph.edges.append(
            CognitiveEdge(
                source=source,
                target=target,
                edge_type=kind,
                weight=float(e.get("weight", 0.9)),
                metadata={
                    "original_kind": e.get("kind"),
                    "line": e.get("line"),
                    "snippet": e.get("snippet"),
                    "verified": e.get("verified"),
                },
            )
        )

    return STORE.create(project_id, graph, path=path)
