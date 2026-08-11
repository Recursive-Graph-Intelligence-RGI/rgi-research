"""Adaptive spawn search for RGI graph action selection."""
from dataclasses import dataclass, field

from rgi.core.models import CognitiveGraph


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


def generate_candidate_actions(graph: CognitiveGraph) -> list[SpawnAction]:
    """Generate candidate actions from graph state; reserved for Task 1."""
    raise NotImplementedError


async def decide_next_action(graph: CognitiveGraph, harness) -> SpawnAction | None:
    """Select the best next action; reserved for Task 1."""
    raise NotImplementedError
