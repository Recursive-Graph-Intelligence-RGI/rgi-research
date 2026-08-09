from rgi.core.engine import execute_graph
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeState,
)
from rgi.loops import initialize_graph_nodes
from rgi.reasoning.llm_client import MockLLMClient


def _harness(tmp_path):
    return Harness(HarnessConfig(data_dir=str(tmp_path), llm_client=MockLLMClient()))


async def test_execution_graph_runs_tool_then_reasoning(tmp_path):
    h = _harness(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    (target / "auth.py").write_text("import jwt\njwt.decode('t', 'k')\n")
    h.config.target_path = str(target)
    h.gate.allowed_root = target

    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="JWT Security Analysis"),
                       policy=GraphPolicy(auto_spawn=False, require_verification=False))
    initialize_graph_nodes(g, {"objective": "JWT Security Analysis", "target_path": str(target)})
    h.graphs[g.id] = g

    done = await execute_graph(g, h)
    assert done.state.status == "completed"
    states = {n.type.value: n.state for n in done.nodes.values()}
    assert states["tool"] == NodeState.COMPLETED
    assert states["reasoning"] == NodeState.COMPLETED
    reasoning = next(n for n in done.nodes.values() if n.type.value == "reasoning")
    assert reasoning.result["finding"]


async def test_planning_graph_spawns_children_from_suggestions(tmp_path):
    h = _harness(tmp_path)
    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="Analyze authentication security"),
                          policy=GraphPolicy())
    initialize_graph_nodes(root, {"objective": "Analyze authentication security"})
    h.graphs[root.id] = root

    done = await execute_graph(root, h)
    assert len(done.subgraph_ids) == 2   # JWT + Session from mock script
    children = [h.get_graph(sid) for sid in done.subgraph_ids]
    assert all(c.loop_type == LoopType.EXECUTION for c in children)
    assert all(c.state.status in ("completed", "failed") for c in children)
    assert done.memory_snapshot.get("merged_findings")


async def test_stagnation_guard_fails_empty_graph(tmp_path):
    h = _harness(tmp_path)
    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="nothing matches this"),
                       policy=GraphPolicy(auto_spawn=False, require_verification=False))
    h.graphs[g.id] = g
    done = await execute_graph(g, h)
    assert done.state.status == "failed"
    assert done.state.iteration < done.state.max_iterations  # did not spin


async def test_spawn_round_cap_completes_chatty_graph(tmp_path):
    """Regression (live Run 5): a chatty model suggests subgraphs on every
    response, and merged children re-seed spawn_suggestions. Without a
    spawn-round cap the graph spawns until max_iterations and dies 'failed'
    without consolidating. With the cap it must stop spawning, consolidate,
    and complete — recording a spawn_inhibited audit event."""
    chatty = {"finding": "something", "confidence": 0.9,
              "suggested_subgraphs": ["look deeper"]}
    h = Harness(HarnessConfig(data_dir=str(tmp_path),
                              llm_client=MockLLMClient(script={"": [chatty]})))
    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="analyze anything"),
                          policy=GraphPolicy(require_verification=False))
    initialize_graph_nodes(root, {"objective": "analyze anything"})
    h.graphs[root.id] = root

    done = await execute_graph(root, h)

    assert done.state.status == "completed"
    inhibited = [e for e in h.audit.events if e["event"] == "spawn_inhibited"]
    assert inhibited, "expected spawn_inhibited audit event once cap hit"
    assert inhibited[0]["reason"] == "max_spawn_rounds"


async def test_coverage_sweep_spawns_for_unread_files(tmp_path):
    """Root must not consolidate while target files went unread — the
    coverage gate fires on the audit trail, not on model self-doubt."""
    from rgi.core.models import CognitiveNode, NodeType

    target = tmp_path / "target"
    target.mkdir()
    (target / "a.py").write_text("x = 1\n")
    (target / "b.py").write_text("import pickle\npickle.loads(b'')\n")
    h = Harness(HarnessConfig(data_dir=str(tmp_path), target_path=str(target),
                              llm_client=MockLLMClient()))
    h.gate.allowed_root = target

    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="security analysis"),
                          policy=GraphPolicy(require_verification=False))
    # Simulate prior work that only ever read a.py
    tool = CognitiveNode(type=NodeType.TOOL, content="parse", parent_graph_id=root.id,
                         state=NodeState.COMPLETED, confidence=1.0,
                         result={"findings": [{"source_excerpt": "===== a.py =====\nx = 1"}]})
    thinker = CognitiveNode(type=NodeType.REASONING, content="analyze",
                            parent_graph_id=root.id, state=NodeState.COMPLETED,
                            confidence=0.9, result={"finding": "a.py looks fine"})
    for n in (tool, thinker):
        root.nodes[n.id] = n
    h.graphs[root.id] = root

    done = await execute_graph(root, h)

    sweeps = [e for e in h.audit.events if e["event"] == "coverage_sweep"]
    assert sweeps and sweeps[0]["missing"] == ["b.py"]
    children = [h.get_graph(sid) for sid in done.subgraph_ids]
    assert any("b.py" in c.state.objective for c in children)
    assert done.state.status == "completed"
