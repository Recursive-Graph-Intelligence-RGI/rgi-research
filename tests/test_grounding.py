from rgi.core.engine import generate_spawn_proposals, should_spawn_subgraphs
from rgi.core.models import (
    CognitiveGraph, GraphPolicy, GraphState, LoopType, NodeState, NodeType, CognitiveNode,
)
from rgi.core.harness import Harness, HarnessConfig
from rgi.loops import initialize_graph_nodes
from rgi.reasoning.llm_client import MockLLMClient
from rgi.tools.registry import ToolRegistry


async def test_parse_result_includes_source_excerpt(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n" * 100)
    result = await ToolRegistry().execute("parse_python_file", {"path": str(f)})
    assert "source_excerpt" in result["findings"][0]
    excerpt = result["findings"][0]["source_excerpt"]
    assert excerpt.startswith("===== m.py =====")  # labeled per-file sections
    assert "x = 1" in excerpt


def _graph_with_suggestion(confidence):
    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="jwt security analysis"),
                       policy=GraphPolicy())
    n = CognitiveNode(type=NodeType.REASONING, content="analyze jwt security analysis",
                      parent_graph_id=g.id, state=NodeState.COMPLETED,
                      confidence=confidence,
                      result={"finding": "x", "confidence": confidence,
                              "suggested_subgraphs": ["more analysis"]})
    g.nodes[n.id] = n
    return g


def test_low_confidence_suggestions_are_ignored():
    h = Harness(HarnessConfig(data_dir="/tmp/rgi-ground", llm_client=MockLLMClient()))
    g = _graph_with_suggestion(0.4)  # below 0.7 threshold
    assert not should_spawn_subgraphs(g)
    assert generate_spawn_proposals(g, h) == []


def test_high_confidence_suggestions_pass_and_cap():
    h = Harness(HarnessConfig(data_dir="/tmp/rgi-ground", llm_client=MockLLMClient()))
    g = _graph_with_suggestion(0.9)
    g.nodes[list(g.nodes)[0]].result["suggested_subgraphs"] = [f"topic {i}" for i in range(6)]
    assert should_spawn_subgraphs(g)
    proposals = generate_spawn_proposals(g, h)
    assert len(proposals) == 3  # capped


def test_secret_routing():
    g = CognitiveGraph(loop_type=LoopType.EXECUTION,
                       state=GraphState(objective="o"), policy=GraphPolicy())
    initialize_graph_nodes(g, {"objective": "Audit config for hardcoded secrets"})
    names = {n.metadata["tool"] for n in g.nodes.values() if n.type == NodeType.TOOL}
    assert "find_hardcoded_secrets" in names


def test_planning_prompt_still_matches_mock_and_grounds():
    g = CognitiveGraph(loop_type=LoopType.PLANNING,
                       state=GraphState(objective="o"), policy=GraphPolicy())
    initialize_graph_nodes(g, {"objective": "Analyze authentication security"})
    content = list(g.nodes.values())[0].content
    assert "decompose" in content.lower()           # mock script key
    assert "world-model" in content                  # grounding instruction
    assert "Analyze authentication security" in content
