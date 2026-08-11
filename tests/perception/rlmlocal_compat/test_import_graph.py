from pathlib import Path

from rgi.perception.rlmlocal_compat.import_graph import build_import_graph
from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


def test_builds_import_edge(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper(): pass\n")
    (tmp_path / "a.py").write_text("from b import helper\n\ndef main():\n    helper()\n")
    py_files = sorted(tmp_path.glob("*.py"))
    structs = {p: extract_structure(p) for p in py_files}
    graph = build_import_graph(tmp_path, structs)
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge["source_file"].endswith("a.py")
    assert edge["target_file"].endswith("b.py")
    assert edge["symbol"] == "helper"


def test_import_statement_edge(tmp_path: Path):
    (tmp_path / "utils.py").write_text("def util(): pass\n")
    (tmp_path / "main.py").write_text("import utils\n\ndef main():\n    utils.util()\n")
    py_files = sorted(tmp_path.glob("*.py"))
    structs = {p: extract_structure(p) for p in py_files}
    graph = build_import_graph(tmp_path, structs)
    assert len(graph.edges) == 1
    assert graph.edges[0]["target_file"].endswith("utils.py")


def test_symbol_defs_indexed(tmp_path: Path):
    (tmp_path / "a.py").write_text("def helper(): pass\n")
    structs = {tmp_path / "a.py": extract_structure(tmp_path / "a.py")}
    graph = build_import_graph(tmp_path, structs)
    assert "helper" in graph.symbol_defs
    assert graph.symbol_defs["helper"][0]["kind"] == "function"
