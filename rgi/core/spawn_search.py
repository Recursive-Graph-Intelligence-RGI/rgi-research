"""Adaptive spawn search for RGI graph action selection."""
import time
from dataclasses import dataclass, field

from rgi.core.models import CognitiveGraph, NodeState, NodeType


class SpawnSearchTimeoutError(TimeoutError):
    """Raised when spawn-search decision logic exceeds its configured budget."""


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


def _deadlock_bonus(action: SpawnAction) -> float:
    if action.action_type != "frontier_arbitrate":
        return 0.0
    return float(len(action.metadata.get("deadlock_signals", [])))


def estimate_value(graph: CognitiveGraph, action: SpawnAction) -> float:
    if action.action_type == "stop":
        return 0.0
    coverage = _coverage_bonus(graph, action)
    tool = _tool_signal(graph, action)
    penalty = _confidence_penalty(graph, action)
    deadlock = _deadlock_bonus(action)
    cost = max(action.estimated_cost, 1)
    return (coverage + tool + deadlock) / (cost + penalty + 1e-9)


def _uncovered_files(graph: CognitiveGraph) -> list[str]:
    world_model = graph.memory_snapshot.get("world_model", {})
    files = set(world_model.get("files", []))
    covered = set()
    for n in graph.nodes.values():
        if n.type == NodeType.MEMORY and n.metadata.get("entity_kind") == "module":
            covered.add(n.metadata.get("file", ""))
    return sorted(f for f in files if f not in covered)


def _avg_confidence_for_deadlock(graph: CognitiveGraph) -> float:
    confs = [n.confidence for n in graph.nodes.values()
             if n.state == NodeState.COMPLETED]
    confs += [float(f.get("confidence", 0.5))
              for f in graph.memory_snapshot.get("merged_findings", [])]
    return sum(confs) / len(confs) if confs else 0.0


def _deadlock_signals(graph: CognitiveGraph, harness: object) -> list[str]:
    signals = []
    avg = _avg_confidence_for_deadlock(graph)
    if (graph.state.iteration >= graph.state.max_iterations - 1
            and avg < graph.state.confidence_threshold):
        signals.append("max_iterations_low_confidence")

    findings = []
    for n in graph.nodes.values():
        if n.state != NodeState.COMPLETED or not isinstance(n.result, dict):
            continue
        if "finding" in n.result:
            findings.append(n.result["finding"])
        elif "findings" in n.result:
            findings.extend(n.result["findings"])
    by_loc: dict[tuple, list[dict]] = {}
    for f in findings:
        if not isinstance(f, dict):
            continue
        loc = (f.get("file"), f.get("line"), f.get("symbol"))
        by_loc.setdefault(loc, []).append(f)
    if any(len(group) > 1 for group in by_loc.values()):
        signals.append("contradictions")

    audit = getattr(harness, "audit", None)
    events = getattr(audit, "events", []) if audit is not None else []
    rejected = sum(
        1 for e in events
        if e.get("event") == "spawn_rejected" and e.get("graph_id") == graph.id
    )
    if rejected >= 3:
        signals.append("repeated_spawn_rejections")
    return signals


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

    # Tool verifications
    for n in graph.nodes.values():
        if (n.type != NodeType.TOOL
                or n.state != NodeState.COMPLETED
                or n.metadata.get("verification_queued")):
            continue
        tool = harness.tool_registry.get_tool(n.metadata.get("tool", ""))
        if not tool or not getattr(tool, "verifier", None):
            continue
        result = n.result if isinstance(n.result, dict) else {}
        findings = result.get("findings", [])
        if not findings:
            continue
        actions.append(SpawnAction(
            action_type="verify_tool",
            objective=f"Verify findings from {n.metadata.get('tool', 'tool')}",
            target_files=[f.get("file", "") for f in findings if f.get("file")],
            reason="tool_verification",
            estimated_cost=max(len(findings), 1),
            metadata={"target_findings": findings, "tool_node": n.id},
        ))

    # REPL exploration for ungrounded low-confidence reasoning
    threshold = getattr(graph.state, "confidence_threshold", 0.7)
    weak_reasoning = [
        n for n in graph.nodes.values()
        if n.type == NodeType.REASONING
        and n.state == NodeState.COMPLETED
        and n.confidence < threshold
        and isinstance(n.result, dict)
        and n.result.get("finding")
    ]
    if weak_reasoning:
        actions.append(SpawnAction(
            action_type="repl_explore",
            objective="Explore weak reasoning findings with REPL",
            target_files=[],
            reason="low_confidence_ungrounded",
            estimated_cost=2,
            metadata={"target_nodes": weak_reasoning},
        ))

    # Frontier arbitration when deadlock signals are present
    deadlock = _deadlock_signals(graph, harness)
    if deadlock:
        actions.append(SpawnAction(
            action_type="frontier_arbitrate",
            objective="Request frontier arbitration to resolve deadlock",
            target_files=[],
            reason="deadlock:" + ",".join(deadlock),
            estimated_cost=1,
            metadata={"deadlock_signals": deadlock},
        ))

    return actions


async def decide_next_action(graph: CognitiveGraph, harness: object,
                             max_time: float | None = None) -> SpawnAction | None:
    start = time.monotonic()
    candidates = generate_candidate_actions(graph, harness)
    if max_time is not None and (time.monotonic() - start) >= max_time:
        raise SpawnSearchTimeoutError(
            f"spawn_search decision exceeded max_time={max_time}s"
        )
    if not candidates:
        return None
    scored = [(estimate_value(graph, a), a) for a in candidates]
    return max(scored, key=lambda x: x[0])[1]
