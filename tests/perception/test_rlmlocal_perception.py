import pytest
from pathlib import Path

from rgi.artifacts import temp_cache
from rgi.perception.rlmlocal_perception import RlmlocalPerceptionLayer


@pytest.mark.asyncio
async def test_builds_graph_with_edges(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper():\n    pass\n")
    (tmp_path / "a.py").write_text("from b import helper\n\ndef main():\n    helper()\n")
    layer = RlmlocalPerceptionLayer()
    graph = await layer.ingest_codebase(str(tmp_path))
    # 2 modules + 2 functions = 4 nodes
    assert len(graph.nodes) == 4
    edge_types = {e.edge_type for e in graph.edges}
    assert "contains" in edge_types
    assert "imports" in edge_types


@pytest.mark.asyncio
async def test_empty_directory():
    layer = RlmlocalPerceptionLayer()
    graph = await layer.ingest_codebase("/tmp/empty_rgi_test_dir_that_does_not_exist_12345")
    assert len(graph.nodes) == 0
    assert len(graph.edges) == 0


@pytest.mark.asyncio
async def test_multi_language_world_model(tmp_path: Path):
    (tmp_path / "b.py").write_text("def py_helper():\n    pass\n")
    (tmp_path / "a.ts").write_text(
        "import { helper } from './c'\n\nexport function main() { return helper() }\n"
    )
    (tmp_path / "c.ts").write_text("export function helper() { return 1 }\n")
    (tmp_path / "d.rs").write_text("pub fn rust_fn() -> i32 { 1 }\n")
    layer = RlmlocalPerceptionLayer()
    graph = await layer.ingest_codebase(str(tmp_path))

    # Modules for all supported languages.
    modules = {n.metadata["name"] for n in graph.nodes.values()
               if n.metadata.get("entity_kind") == "module"}
    assert {"a", "b", "c", "d"} == modules, f"got {modules}"

    # Language metadata present on modules.
    langs = {n.metadata.get("language") for n in graph.nodes.values()
             if n.metadata.get("entity_kind") == "module"}
    assert {"python", "js", "rust"} == langs, f"got {langs}"

    # Functions extracted across languages.
    functions = {n.metadata["name"] for n in graph.nodes.values()
                 if n.metadata.get("entity_kind") == "function"}
    assert {"py_helper", "main", "helper", "rust_fn"} == functions, f"got {functions}"

    # JS relative import edge a.ts -> c.ts.
    edge_types = {e.edge_type for e in graph.edges}
    assert "imports" in edge_types
    import_edges = [e for e in graph.edges if e.edge_type == "imports"]
    assert any(
        graph.nodes[e.source].metadata.get("name") == "a"
        and graph.nodes[e.target].metadata.get("name") == "c"
        for e in import_edges
    )


@pytest.mark.asyncio
async def test_ingest_cached_is_o1_lookup(tmp_path: Path):
    (tmp_path / "b.py").write_text("def helper():\n    pass\n")
    (tmp_path / "a.py").write_text("from b import helper\n\ndef main():\n    helper()\n")
    cache = temp_cache()
    layer = RlmlocalPerceptionLayer()

    g1 = await layer.ingest_codebase_cached(str(tmp_path), cache)
    assert g1.memory_snapshot.get("artifact_cached") is False  # first build

    g2 = await layer.ingest_codebase_cached(str(tmp_path), cache)
    assert g2.memory_snapshot.get("artifact_cached") is True  # O(1) hit
    assert len(g2.nodes) == len(g1.nodes) == 4
    assert cache.layers() == ["world-model"]


@pytest.mark.asyncio
async def test_ingest_cached_recomputes_on_change(tmp_path: Path):
    (tmp_path / "a.py").write_text("def main():\n    return 1\n")
    cache = temp_cache()
    layer = RlmlocalPerceptionLayer()

    g1 = await layer.ingest_codebase_cached(str(tmp_path), cache)
    assert g1.memory_snapshot.get("artifact_cached") is False

    # Change the source → new inputs hash → recompute, not stale cache.
    (tmp_path / "a.py").write_text("def main():\n    return 2\n\ndef extra():\n    pass\n")
    g2 = await layer.ingest_codebase_cached(str(tmp_path), cache)
    assert g2.memory_snapshot.get("artifact_cached") is False
    assert len(g2.nodes) > len(g1.nodes)
