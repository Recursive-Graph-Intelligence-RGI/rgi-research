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


async def test_verification_challenge_refused_when_budget_exhausted(tmp_path):
    """The LLM hard cap binds verification challenges too: no gate bypass."""
    from rgi.core.models import (
        CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeType,
    )
    from rgi.core.engine import execute_graph
    from rgi.core.harness import Harness, HarnessConfig
    from rgi.reasoning.llm_client import MockLLMClient

    h = Harness(HarnessConfig(data_dir=str(tmp_path), max_llm_calls=0,
                              llm_client=MockLLMClient()))
    g = CognitiveGraph(loop_type=LoopType.VERIFICATION,
                       state=GraphState(objective="Verify: jwt security analysis"),
                       policy=GraphPolicy(auto_spawn=False, require_verification=False))
    from rgi.loops import initialize_graph_nodes
    initialize_graph_nodes(g, {"objective": "Verify: jwt security analysis",
                               "target_findings": [{"finding": "missing exp", "confidence": 0.6}]})
    h.graphs[g.id] = g
    await execute_graph(g, h)
    verifier = next(n for n in g.nodes.values() if n.type == NodeType.VERIFICATION)
    assert h.llm_client.calls == 0  # challenge never reached the LLM
    assert verifier.result.get("detail") == "budget_exhausted"
    assert any(e["event"] == "governance_denied" for e in h.audit.events)
