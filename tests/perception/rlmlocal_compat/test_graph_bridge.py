import json
from pathlib import Path

from rgi.perception.rlmlocal_compat.graph_bridge import import_rlmlocal_graph


def test_import_rlmlocal_graph(tmp_path: Path):
    snapshot = {
        "nodes": [
            {
                "id": "n1",
                "kind": "function",
                "name": "main",
                "file": "main.py",
                "line": 1,
                "content": "def main(): pass",
            },
            {
                "id": "n2",
                "kind": "function",
                "name": "helper",
                "file": "helper.py",
                "line": 1,
            },
        ],
        "edges": [
            {"source": "n1", "target": "n2", "kind": "calls", "symbol": "helper", "weight": 0.8},
        ],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(snapshot))
    graph = import_rlmlocal_graph(path)
    assert len(graph.nodes) == 2
    assert "n1" in graph.nodes
    assert graph.nodes["n1"].metadata["name"] == "main"
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.source == "n1"
    assert edge.target == "n2"
    assert edge.edge_type == "dependency"  # "calls" maps to default dependency
    assert edge.weight == 0.8
    assert edge.metadata["symbol"] == "helper"


def test_import_ignores_invalid_edge_kind(tmp_path: Path):
    snapshot = {
        "nodes": [
            {"id": "a", "kind": "module", "name": "a"},
            {"id": "b", "kind": "module", "name": "b"},
        ],
        "edges": [
            {"source": "a", "target": "b", "kind": "contains"},
        ],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(snapshot))
    graph = import_rlmlocal_graph(path)
    assert graph.edges[0].edge_type == "contains"


def test_import_skips_nodes_without_id(tmp_path: Path):
    snapshot = {
        "nodes": [
            {"kind": "function", "name": "orphan"},
        ],
        "edges": [],
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(snapshot))
    graph = import_rlmlocal_graph(path)
    assert len(graph.nodes) == 0
