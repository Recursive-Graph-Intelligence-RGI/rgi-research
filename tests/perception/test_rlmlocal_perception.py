import pytest
from pathlib import Path

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
