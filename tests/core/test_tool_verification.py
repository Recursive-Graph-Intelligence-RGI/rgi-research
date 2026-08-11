import pytest

from rgi.core.engine import (
    _queue_tool_verifications,
    generate_spawn_proposals,
    should_spawn_subgraphs,
)
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType, NodeState, NodeType,
)
from rgi.reasoning.llm_client import MockLLMClient
from rgi.tools.registry import ToolRegistry


def _make_graph_with_tool_finding() -> CognitiveGraph:
    graph = CognitiveGraph(
        loop_type=LoopType.EXECUTION,
        state=GraphState(objective="find security vulnerabilities"),
        policy=GraphPolicy(),
    )
    tool_node = CognitiveNode(
        type=NodeType.TOOL,
        content="security_scan",
        parent_graph_id=graph.id,
        metadata={"tool": "security_scan", "params": {"path": "sample_project"}},
    )
    tool_node.state = NodeState.COMPLETED
    tool_node.result = {
        "findings": [
            {
                "kind": "hardcoded_secret",
                "severity": "critical",
                "file": "auth.py",
                "line": 4,
                "symbol": "SECRET_KEY",
                "confidence": 0.99,
            }
        ],
        "confidence": 0.95,
    }
    graph.nodes[tool_node.id] = tool_node
    return graph


def test_tool_verification_queued():
    registry = ToolRegistry()
    harness = Harness(HarnessConfig(data_dir="/tmp/rgi-tv", llm_client=MockLLMClient()))
    harness.tool_registry = registry  # ensure harness sees same registry
    graph = _make_graph_with_tool_finding()

    assert should_spawn_subgraphs(graph, harness)
    proposals = generate_spawn_proposals(graph, harness)

    assert len(proposals) == 1
    assert proposals[0]["loop_type"] == LoopType.VERIFICATION
    assert proposals[0]["reason"] == "tool_verification"
    assert "hardcoded_secret" in proposals[0]["objective"]
    assert "auth.py:4" in proposals[0]["objective"]
    assert proposals[0]["target_findings"][0]["file"] == "auth.py"


def test_tool_verification_not_queued_twice():
    registry = ToolRegistry()
    harness = Harness(HarnessConfig(data_dir="/tmp/rgi-tv", llm_client=MockLLMClient()))
    harness.tool_registry = registry
    graph = _make_graph_with_tool_finding()

    generate_spawn_proposals(graph, harness)
    assert not should_spawn_subgraphs(graph, harness)
    proposals = generate_spawn_proposals(graph, harness)
    assert proposals == []


def test_non_verifier_tool_does_not_queue():
    registry = ToolRegistry()
    harness = Harness(HarnessConfig(data_dir="/tmp/rgi-tv", llm_client=MockLLMClient()))
    harness.tool_registry = registry
    graph = CognitiveGraph(
        loop_type=LoopType.EXECUTION,
        state=GraphState(objective="find x"),
        policy=GraphPolicy(),
    )
    tool_node = CognitiveNode(
        type=NodeType.TOOL,
        content="grep",
        parent_graph_id=graph.id,
        metadata={"tool": "grep", "params": {"root": ".", "pattern": "x"}},
    )
    tool_node.state = NodeState.COMPLETED
    tool_node.result = {"findings": [], "confidence": 1.0}
    graph.nodes[tool_node.id] = tool_node

    assert not should_spawn_subgraphs(graph, harness)
