from pathlib import Path

from rgi.perception.rlmlocal_compat.call_graph import build_call_graph
from rgi.perception.rlmlocal_compat.import_graph import build_import_graph
from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


def _structs(root: Path):
    return {p: extract_structure(p) for p in sorted(root.glob("*.py"))}


def test_call_edge_resolves_single_definition(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "a.py").write_text("from b import helper\n\ndef main():\n    return helper()\n")
    graph = build_call_graph(tmp_path, _structs(tmp_path))
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge["source_file"].endswith("a.py")
    assert edge["target_file"].endswith("b.py")
    assert edge["symbol"] == "helper"
    assert edge["kind"] == "call"


def test_call_edge_dotted_callee_resolves_module(tmp_path: Path):
    (tmp_path / "utils.py").write_text("def util():\n    return 1\n")
    (tmp_path / "main.py").write_text(
        "import utils\n\ndef main():\n    return utils.util()\n"
    )
    graph = build_call_graph(tmp_path, _structs(tmp_path))
    assert len(graph.edges) == 1
    assert graph.edges[0]["target_file"].endswith("utils.py")
    assert graph.edges[0]["symbol"] == "utils.util"


def test_call_edge_ambiguous_definition_is_dropped(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "c.py").write_text("def helper():\n    return 2\n")
    (tmp_path / "a.py").write_text(
        "def main():\n    return helper()\n"
    )
    graph = build_call_graph(tmp_path, _structs(tmp_path))
    assert graph.edges == []


def test_call_edge_same_file_is_ignored(tmp_path: Path):
    (tmp_path / "a.py").write_text(
        "def helper():\n    return 1\n\ndef main():\n    return helper()\n"
    )
    graph = build_call_graph(tmp_path, _structs(tmp_path))
    assert graph.edges == []


def test_call_graph_reuses_import_symbol_index(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "a.py").write_text("from b import helper\n\ndef main():\n    return helper()\n")
    structs = _structs(tmp_path)
    import_graph = build_import_graph(tmp_path, structs)
    graph = build_call_graph(tmp_path, structs, import_graph.symbol_defs)
    assert len(graph.edges) == 1
