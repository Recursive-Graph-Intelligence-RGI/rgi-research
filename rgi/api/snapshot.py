"""Snapshot validation and import into a CognitiveGraph.

The snapshot format is the shared ``rgi-graph-snapshot-v1`` schema used between
RGI and rlmlocal-site.
"""
import re
from pathlib import Path
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

# Windows drive-letter paths (C:\\foo) are not caught by Path.is_absolute on
# POSIX, so reject them explicitly alongside leading-slash and parent-relative
# paths. rlmlocal exports project-relative paths only; anything else is a
# security violation, not a feature.
_ABS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _path_ok(path: Any) -> bool:
    """A snapshot node path must be a relative, in-project path."""
    if not isinstance(path, str) or not path:
        return False
    if path.startswith("/") or path.startswith("..") or _ABS_DRIVE_RE.match(path):
        return False
    return True


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
        ValueError: If the snapshot version is unsupported, a node path is
            absolute/parent-relative, or the project path is not absolute.
    """
    if data.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported snapshot version: {data.get('version')!r}")

    # Operator-supplied filesystem path for the project (desktop/Tauri mode).
    # The PWA has no server-side path; when absent the project is snapshot-only.
    project_path = data.get("project_path")
    if project_path is not None:
        if not isinstance(project_path, str) or not Path(project_path).is_absolute():
            raise ValueError("project_path must be an absolute filesystem path")
        path = project_path

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    for n in nodes:
        p = n.get("path")
        if p is not None and not _path_ok(p):
            raise ValueError(f"absolute or parent-relative path rejected: {p!r}")
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
