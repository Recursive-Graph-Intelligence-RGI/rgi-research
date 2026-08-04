"""Self-correction is TOPOLOGICAL: verification spawns a NEW execution
graph; the original node passes through CORRECTING; confidence rises."""
from rgi.core.engine import execute_graph
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeState, NodeType,
)
from rgi.loops import initialize_graph_nodes
from rgi.reasoning.llm_client import MockLLMClient


async def test_correction_changes_topology_and_raises_confidence(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "auth.py").write_text("import jwt\njwt.decode('t', 'k')\n")
    h = Harness(HarnessConfig(data_dir=str(tmp_path / "data"), target_path=str(target),
                              llm_client=MockLLMClient()))

    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="Analyze authentication security"),
                          policy=GraphPolicy())
    initialize_graph_nodes(root, {"objective": "Analyze authentication security"})
    h.graphs[root.id] = root

    graphs_before = set(h.graphs)
    done = await execute_graph(root, h)

    # New graphs were born: verification + correction + deep dive
    new_graphs = [h.graphs[gid] for gid in set(h.graphs) - graphs_before]
    verification = [g for g in new_graphs if g.loop_type == LoopType.VERIFICATION]
    corrections = [g for g in new_graphs if g.spawn_reason == "correction"]
    assert len(verification) == 1
    assert len(corrections) == 1

    # The original under-confident node passed through CORRECTING
    jwt_graph = next(g for g in new_graphs
                     if g.loop_type == LoopType.EXECUTION
                     and g.state.objective == "JWT Security Analysis")
    original = next(n for n in jwt_graph.nodes.values() if n.type == NodeType.REASONING)
    states_seen = [h_.get("state") for h_ in original.history]
    assert "correcting" in states_seen
    assert any(h_.get("correction_success") for h_ in original.history)

    # Confidence rose above the original 0.6
    assert original.confidence >= 0.8

    # Correction count is observable
    assert jwt_graph.state.correction_count >= 1
    assert any(e["event"] == "correction_completed" for e in h.audit.events)

    # Whole system stayed within limits
    assert all(h.depth_of(g) <= 2 for g in h.graphs.values())
    assert h.total_llm_calls <= 20
