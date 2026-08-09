"""REPL exploration (RLM-style, graph-native): a reasoning node emits
repl_code, the engine grows an explore_corpus node wired back by a flow
edge, and the reasoning node re-fires with the output as an input."""
from rgi.core.engine import execute_graph
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeState, NodeType,
)
from rgi.loops import initialize_graph_nodes
from rgi.reasoning.llm_client import MockLLMClient
from rgi.tools.registry import ToolRegistry


async def test_explore_corpus_sandbox(tmp_path):
    (tmp_path / "a.py").write_text("import pickle\npickle.loads(b'')\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    result = await ToolRegistry().execute("explore_corpus", {
        "path": str(tmp_path),
        "code": "hits = [n for n, s in FILES.items() if 'pickle' in s]\n"
                "RESULT = hits",
    })
    assert "a.py" in result["findings"][0]["output"]
    assert "RESULT" in result["findings"][0]["output"]


async def test_explore_corpus_blocks_unsafe_builtins(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    result = await ToolRegistry().execute("explore_corpus", {
        "path": str(tmp_path),
        "code": "open('/etc/passwd')",
    })
    assert result["findings"][0]["kind"] == "repl_error"


async def test_reasoning_node_repl_round_rewires_graph(tmp_path):
    """The model asks for compute; the topology grows a REPL node with a
    flow edge back; the reasoning node re-fires and completes."""
    target = tmp_path / "target"
    target.mkdir()
    (target / "auth.py").write_text("import jwt\njwt.decode('t', 'k')\n")
    script = {"": [
        {"repl_code": "RESULT = [n for n in FILES if 'jwt' in FILES[n]]"},
        {"finding": "jwt.decode without exp verification", "confidence": 0.85,
         "reasoning": "REPL confirmed jwt usage in auth.py",
         "recommended_action": "report", "suggested_subgraphs": []},
    ]}
    h = Harness(HarnessConfig(data_dir=str(tmp_path), target_path=str(target),
                              llm_client=MockLLMClient(script=script)))
    h.gate.allowed_root = target

    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="JWT Security Analysis"),
                       policy=GraphPolicy(auto_spawn=False, require_verification=False))
    initialize_graph_nodes(g, {"objective": "JWT Security Analysis",
                               "target_path": str(target)})
    h.graphs[g.id] = g

    done = await execute_graph(g, h)

    assert done.state.status == "completed"
    repl_nodes = [n for n in done.nodes.values()
                  if n.metadata.get("tool") == "explore_corpus"]
    assert len(repl_nodes) == 1 and repl_nodes[0].state == NodeState.COMPLETED
    assert "auth.py" in repl_nodes[0].result["findings"][0]["output"]
    reasoning = next(n for n in done.nodes.values() if n.type == NodeType.REASONING)
    assert reasoning.state == NodeState.COMPLETED
    assert reasoning.confidence == 0.85
    assert reasoning.metadata["repl_rounds"] == 1
    assert any(e.source == repl_nodes[0].id and e.target == reasoning.id
               and e.edge_type == "flow" for e in done.edges)
    assert any(e["event"] == "repl_exploration" for e in h.audit.events)
