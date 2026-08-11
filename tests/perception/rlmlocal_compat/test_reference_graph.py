from pathlib import Path

from rgi.perception.rlmlocal_compat.reference_graph import build_reference_graph
from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


def _structs(root: Path):
    return {p: extract_structure(p) for p in sorted(root.glob("*.py"))}


def test_route_to_fetch_edge(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        'from flask import Flask\napp = Flask(__name__)\n\n'
        '@app.route("/api/items")\ndef items():\n    return []\n'
    )
    (tmp_path / "client.py").write_text(
        'def load():\n    return fetch("/api/items")\n'
    )
    graph = build_reference_graph(tmp_path, _structs(tmp_path))
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge["source_file"].endswith("client.py")
    assert edge["target_file"].endswith("app.py")
    assert edge["url"] == "/api/items"
    assert edge["verified"] is True


def test_route_params_prefix_match(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        'from fastapi import FastAPI\napp = FastAPI()\n\n'
        '@app.get("/api/items/<item_id>")\ndef get_item(item_id: str):\n    return {}\n'
    )
    (tmp_path / "client.py").write_text(
        'def load():\n    return requests.get("/api/items")\n'
    )
    graph = build_reference_graph(tmp_path, _structs(tmp_path))
    assert len(graph.edges) == 1
    assert graph.edges[0]["target_file"].endswith("app.py")


def test_unmatched_client_call_is_dropped(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        'from flask import Flask\napp = Flask(__name__)\n\n'
        '@app.route("/api/known")\ndef known():\n    return []\n'
    )
    (tmp_path / "client.py").write_text(
        'def load():\n    return fetch("/api/unknown")\n'
    )
    graph = build_reference_graph(tmp_path, _structs(tmp_path))
    assert graph.edges == []


def test_trailing_slash_normalized(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        'from flask import Flask\napp = Flask(__name__)\n\n'
        '@app.route("/api/items/")\ndef items():\n    return []\n'
    )
    (tmp_path / "client.py").write_text(
        'def load():\n    return fetch("/api/items")\n'
    )
    graph = build_reference_graph(tmp_path, _structs(tmp_path))
    assert len(graph.edges) == 1
