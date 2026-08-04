from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType,
    NodeType,
)
from rgi.reasoning.llm_client import MockLLMClient


def _harness(tmp_path, **overrides):
    config = HarnessConfig(data_dir=str(tmp_path), llm_client=MockLLMClient(), **overrides)
    h = Harness(config)
    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="root"), policy=GraphPolicy())
    h.graphs[root.id] = root
    return h, root


async def test_spawn_approved_within_limits(tmp_path):
    h, root = _harness(tmp_path)
    child_id = await h.request_subgraph_spawn(root.id, {
        "loop_type": LoopType.EXECUTION, "objective": "child task",
    })
    assert child_id is not None
    assert child_id in h.graphs
    assert h.graphs[child_id].parent_graph_id == root.id
    assert root.subgraph_ids == [child_id]
    assert any(e["event"] == "spawn_approved" for e in h.audit.events)


async def test_spawn_rejected_at_depth_limit(tmp_path):
    h, root = _harness(tmp_path, max_depth=2)
    # root is depth 0; child depth 1 (allowed); grandchild depth 2 (rejected)
    child_id = await h.request_subgraph_spawn(root.id, {
        "loop_type": LoopType.EXECUTION, "objective": "depth 1"})
    assert child_id is not None
    grandchild_id = await h.request_subgraph_spawn(child_id, {
        "loop_type": LoopType.EXECUTION, "objective": "depth 2"})
    assert grandchild_id is None
    rejections = [e for e in h.audit.events if e["event"] == "spawn_rejected"]
    assert rejections[-1]["reason"] == "depth_limit"


async def test_spawn_rejected_at_node_limit(tmp_path):
    h, root = _harness(tmp_path, max_total_nodes=1)
    # root itself has no nodes yet, but limit=1 is reached after first spawn init
    child_id = await h.request_subgraph_spawn(root.id, {
        "loop_type": LoopType.EXECUTION, "objective": "fills budget"})
    second = await h.request_subgraph_spawn(root.id, {
        "loop_type": LoopType.EXECUTION, "objective": "over budget"})
    assert second is None
    assert any(e.get("reason") == "node_limit" for e in h.audit.events)


async def test_governance_blocks_llm_over_budget(tmp_path):
    h, root = _harness(tmp_path, max_llm_calls=0)
    node = CognitiveNode(type=NodeType.REASONING, content="t", parent_graph_id=root.id)
    assert h.governance_check(root, node) is False
    assert any(e["event"] == "governance_denied" for e in h.audit.events)


async def test_spawn_from_unknown_parent_rejected(tmp_path):
    h, root = _harness(tmp_path)
    assert await h.request_subgraph_spawn("nope", {"loop_type": LoopType.EXECUTION,
                                                   "objective": "x"}) is None
