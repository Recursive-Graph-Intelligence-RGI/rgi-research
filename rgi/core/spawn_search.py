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


def estimate_value(graph: CognitiveGraph, action: SpawnAction) -> float:
    """Estimate expected value of an action; reserved for Task 1."""
    raise NotImplementedError


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


async def decide_next_action(graph: CognitiveGraph, harness) -> SpawnAction | None:
    """Select the best next action; reserved for Task 1."""
    raise NotImplementedError
