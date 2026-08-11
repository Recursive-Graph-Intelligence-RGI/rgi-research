import pytest

from rgi.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_grounded_repl_tools_registered():
    registry = ToolRegistry()
    for name in ("read_file", "grep", "callers"):
        assert name in registry.tools
        result = await registry.execute(name, _sample_params(name))
        assert "findings" in result


def _sample_params(name: str) -> dict:
    if name == "read_file":
        return {"path": __file__, "line_start": 1, "line_end": 1}
    if name == "grep":
        return {"pattern": "def test", "root": __file__}
    if name == "callers":
        return {"symbol": "x", "import_graph_edges": []}
    return {}
