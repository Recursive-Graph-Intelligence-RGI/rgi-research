"""Safety proof: a chain of 5 spawn attempts with max_depth=2 creates only
depth 0 and depth 1 graphs; the rest are rejected and logged."""
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import CognitiveGraph, GraphPolicy, GraphState, LoopType
from rgi.reasoning.llm_client import MockLLMClient


async def test_spawn_chain_stops_at_max_depth(tmp_path):
    h = Harness(HarnessConfig(data_dir=str(tmp_path), max_depth=2,
                              llm_client=MockLLMClient()))
    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="root"), policy=GraphPolicy())
    h.graphs[root.id] = root

    parent_id, created = root.id, 0
    for i in range(5):
        child_id = await h.request_subgraph_spawn(parent_id, {
            "loop_type": LoopType.EXECUTION, "objective": f"chain {i}"})
        if child_id is None:
            break
        created += 1
        parent_id = child_id

    assert created == 1  # only depth 1 got created
    depths = [h.depth_of(g) for g in h.graphs.values()]
    assert max(depths) <= 1
    rejections = [e for e in h.audit.events if e["event"] == "spawn_rejected"]
    assert len(rejections) == 1
    assert rejections[0]["reason"] == "depth_limit"
