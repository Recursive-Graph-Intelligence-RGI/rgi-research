"""Adaptive spawn search for RGI graph action selection."""
from dataclasses import dataclass, field

from rgi.core.models import CognitiveGraph, NodeState, NodeType


@dataclass
class SpawnAction:
    action_type: str
    objective: str
    target_files: list[str]
    reason: str
    estimated_cost: int
    metadata: dict = field(default_factory=dict)


@dataclass
class SpawnNode:
    state_snapshot: dict
    action: SpawnAction | None
    parent: "SpawnNode | None"
    children: list["SpawnNode"]
    visits: int = 0
    total_value: float = 0.0


def _coverage_bonus(graph: CognitiveGraph, action: SpawnAction) -> float:
    if action.action_type != "execution_sweep":
        return 0.0
    return float(len(action.target_files))


def _tool_signal(graph: CognitiveGraph, action: SpawnAction) -> float:
    if action.action_type != "verify_tool":
        return 0.0
    findings = action.metadata.get("target_findings", [])
    return float(len(findings))


def _confidence_penalty(graph: CognitiveGraph, action: SpawnAction) -> float:
    if action.action_type != "repl_explore":
        return 0.0
    nodes = action.metadata.get("target_nodes", [])
    if not nodes:
        return 0.0
    confs = [n.confidence for n in nodes if hasattr(n, "confidence")]
    if not confs:
        return 0.0
    return 1.0 - (sum(confs) / len(confs))


def estimate_value(graph: CognitiveGraph, action: SpawnAction) -> float:
    if action.action_type == "stop":
        return 0.0
    coverage = _coverage_bonus(graph, action)
    tool = _tool_signal(graph, action)
    penalty = _confidence_penalty(graph, action)
    cost = max(action.estimated_cost, 1)
    return (coverage + tool) / (cost + penalty + 1e-9)


def _uncovered_files(graph: CognitiveGraph) -> list[str]:
    world_model = graph.memory_snapshot.get("world_model", {})
    files = set(world_model.get("files", []))
    covered = set()
    for n in graph.nodes.values():
        if n.type == NodeType.MEMORY and n.metadata.get("entity_kind") == "module":
            covered.add(n.metadata.get("file", ""))
    return sorted(f for f in files if f not in covered)


def generate_candidate_actions(graph: CognitiveGraph, harness: object) -> list[SpawnAction]:
    actions = [SpawnAction("stop", "", [], "no_action", 0, {})]
    uncovered = _uncovered_files(graph)
    if uncovered:
        actions.append(SpawnAction(
            action_type="execution_sweep",
            objective=f"Coverage sweep: security analysis of {', '.join(uncovered)}",
            target_files=uncovered,
            reason="coverage_gap",
            estimated_cost=3,
            metadata={"loop_type": "execution", "target_path": ""},
        ))
    # Tool verification and REPL exploration actions added in Task 3.
    return actions


async def decide_next_action(graph: CognitiveGraph, harness: object) -> SpawnAction | None:
    candidates = generate_candidate_actions(graph, harness)
    if not candidates:
        return None
    scored = [(estimate_value(graph, a), a) for a in candidates]
    return max(scored, key=lambda x: x[0])[1]
