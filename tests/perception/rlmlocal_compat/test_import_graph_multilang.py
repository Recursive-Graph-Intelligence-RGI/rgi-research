from pathlib import Path

from rgi.perception.rlmlocal_compat.import_graph import build_import_graph, source_files
from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


def _structs(root: Path):
    return {p: extract_structure(p) for p in source_files(root)}


def test_source_files_includes_multi_language(tmp_path: Path):
    (tmp_path / "a.py").write_text("def f():\n    pass\n")
    (tmp_path / "b.ts").write_text("export function g() { return 1 }\n")
    (tmp_path / "c.js").write_text("function h() { return 2 }\n")
    (tmp_path / "d.go").write_text("package d\nfunc F() {}\n")
    (tmp_path / "e.rs").write_text("fn main() {}\n")
    (tmp_path / "README.md").write_text("not source")
    files = source_files(tmp_path)
    names = {f.name for f in files}
    assert {"a.py", "b.ts", "c.js", "d.go", "e.rs"} == names
    assert "README.md" not in names


def test_js_relative_import_resolves(tmp_path: Path):
    (tmp_path / "b.ts").write_text("export function helper() { return 1 }\n")
    (tmp_path / "a.ts").write_text(
        "import { helper } from './b'\n\nexport function main() { return helper() }\n"
    )
    structs = _structs(tmp_path)
    graph = build_import_graph(tmp_path, structs)
    edges = [(e["source_file"].endswith("a.ts"), e["target_file"].endswith("b.ts")) for e in graph.edges]
    assert edges == [(True, True)], f"expected a.ts -> b.ts, got {graph.edges}"


def test_js_directory_import_resolves_index(tmp_path: Path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "index.ts").write_text("export const x = 1\n")
    (tmp_path / "main.ts").write_text(
        "import { x } from './lib'\n\nexport function m() { return x }\n"
    )
    structs = _structs(tmp_path)
    graph = build_import_graph(tmp_path, structs)
    assert len(graph.edges) == 1
    assert graph.edges[0]["target_file"].endswith("lib/index.ts")


def test_bare_specifier_import_is_skipped(tmp_path: Path):
    (tmp_path / "a.ts").write_text(
        "import react from 'react'\n\nexport function m() { return react }\n"
    )
    structs = _structs(tmp_path)
    graph = build_import_graph(tmp_path, structs)
    assert graph.edges == []


def test_rust_crate_import_resolves(tmp_path: Path):
    (tmp_path / "utils.rs").write_text("pub fn helper() -> i32 { 1 }\n")
    (tmp_path / "main.rs").write_text(
        "use crate::utils::helper;\n\nfn main() { helper(); }\n"
    )
    structs = _structs(tmp_path)
    graph = build_import_graph(tmp_path, structs)
    assert len(graph.edges) == 1
    assert graph.edges[0]["target_file"].endswith("utils.rs")


def test_python_import_still_works(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "a.py").write_text("from b import helper\n\ndef main():\n    return helper()\n")
    structs = _structs(tmp_path)
    graph = build_import_graph(tmp_path, structs)
    assert len(graph.edges) == 1
    assert graph.edges[0]["target_file"].endswith("b.py")
