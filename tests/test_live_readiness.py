import asyncio
import pytest
from rgi.core.engine import execute_graph, verify_findings
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeState, NodeType,
)
from rgi.loops import initialize_graph_nodes
from rgi.reasoning.llm_client import LLMClient, MockLLMClient


async def test_verify_findings_sends_challenged_finding_in_context():
    """The challenge prompt must carry the finding text — the live LLM
    cannot challenge what it cannot see."""
    seen = {}

    class SpyClient(MockLLMClient):
        async def reason(self, task, context):
            seen["context"] = context
            return await super().reason(task, context)

    h = Harness(HarnessConfig(data_dir="/tmp/rgi-readiness", llm_client=SpyClient()))
    g = CognitiveGraph(loop_type=LoopType.VERIFICATION,
                       state=GraphState(objective="Verify: jwt security analysis"),
                       policy=GraphPolicy())
    initialize_graph_nodes(g, {"objective": "Verify: jwt security analysis",
                               "target_findings": [{"finding": "missing exp check", "confidence": 0.6}]})
    h.graphs[g.id] = g
    verifier = next(n for n in g.nodes.values() if n.type == NodeType.VERIFICATION)
    targets = [g.nodes[e.target] for e in g.edges if e.edge_type == "verifies"]
    await verify_findings(verifier, targets, h)
    assert "missing exp check" in seen["context"]


def test_confidence_clamped_both_clients():
    bad = {"finding": "x", "confidence": 7.5, "reasoning": "",
           "recommended_action": "", "suggested_subgraphs": []}
    mock = MockLLMClient(script={"jwt": [bad]})
    result = asyncio.run(mock.reason("jwt task", ""))
    assert 0.0 <= result["confidence"] <= 1.0

    real = LLMClient(api_key="k")
    assert real._validate({"finding": "x", "confidence": -3})["confidence"] == 0.0
    assert real._validate({"finding": "x"})["confidence"] == 0.5  # default


async def test_raising_child_does_not_lose_sibling_merges():
    """A child that raises mid-execution must not escape gather or eat
    the sibling's merged findings."""
    h = Harness(HarnessConfig(data_dir="/tmp/rgi-readiness2", llm_client=MockLLMClient()))
    root = CognitiveGraph(loop_type=LoopType.PLANNING,
                          state=GraphState(objective="Analyze authentication security"),
                          policy=GraphPolicy())
    initialize_graph_nodes(root, {"objective": "Analyze authentication security"})
    h.graphs[root.id] = root

    original = h.tool_registry.execute

    async def exploding_execute(tool_name, params):
        if tool_name == "check_jwt_usage":
            raise RuntimeError("tool exploded")
        if tool_name == "grep_security_patterns":
            # Give the session child a grounded, high-confidence finding so the
            # new grounding gate still lets it merge despite the JWT sibling failing.
            return {
                "findings": [{
                    "kind": "session_timeout_missing",
                    "severity": "high",
                    "detail": "SessionStore never checks age",
                    "file": "session.py",
                    "line": 10,
                }],
                "confidence": 0.9,
            }
        return await original(tool_name, params)

    h.tool_registry.execute = exploding_execute
    done = await execute_graph(root, h)

    # Exception contained: JWT's tool node failed, but session child still
    # completed and merged; root terminated instead of raising
    assert done.state.status in ("completed", "failed")
    children = [h.get_graph(s) for s in done.subgraph_ids]
    jwt_child = next(c for c in children if "JWT" in c.state.objective)
    session_child = next(c for c in children if "Session" in c.state.objective)
    jwt_tool = next(n for n in jwt_child.nodes.values()
                    if n.type == NodeType.TOOL and n.metadata["tool"] == "check_jwt_usage")
    assert jwt_tool.state == NodeState.FAILED
    assert session_child.state.status == "completed"
    assert done.memory_snapshot.get("merged_findings")
