"""The RGI execution loop — the heart of the system. Five phases per
iteration: activation, node execution, recursive spawning, verification &
consolidation, learning. The LLM is called inside nodes only; every
orchestration decision is made here and in the Harness, and is audited."""
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from rgi.core.harness import Harness
from rgi.core.models import (
    CognitiveEdge, CognitiveGraph, CognitiveNode, LoopType, NodeState, NodeType,
)

ACTIVATION_THRESHOLD = 0.5
MAX_SPAWN_ROUNDS = 2  # per-graph; chatty models re-seed suggestions every merge
MAX_REPL_ROUNDS = 2   # per-node; bounded model-driven corpus exploration


async def execute_graph(graph: CognitiveGraph, harness: Harness) -> CognitiveGraph:
    spawn_rounds = 0
    while graph.state.status == "running" and graph.state.iteration < graph.state.max_iterations:
        if harness.time_exceeded():
            graph.state.status = "failed"
            harness.audit.record("time_limit_exceeded", graph_id=graph.id)
            break
        progressed = False

        # PHASE 1: ACTIVATION — attention, not retrieval
        scores = await harness.activation_engine.a_propagate(graph, graph.state.objective)
        for node_id, score in scores.items():
            if node_id in graph.nodes:
                graph.nodes[node_id].activation = score
        threshold = getattr(harness.activation_engine, "threshold", ACTIVATION_THRESHOLD)
        active = [n for n in graph.nodes.values() if n.activation > threshold]
        active.sort(key=lambda n: n.activation, reverse=True)
        executable = {NodeType.REASONING, NodeType.TOOL, NodeType.VERIFICATION,
                      NodeType.GOVERNANCE}
        ordered = [n for n in _dependency_order(active, graph.edges)
                   if n.type in executable]  # MEMORY/SIMULATION: inert data, never executed

        # PHASE 2: NODE EXECUTION (topological: tool output feeds reasoning)
        for node in ordered:
            if node.state in (NodeState.COMPLETED, NodeState.FAILED):
                continue
            if not harness.governance_check(graph, node):
                node.state = NodeState.FAILED
                node.history.append({"reason": "governance_violation",
                                     "timestamp": datetime.now().isoformat()})
                continue
            node.state = NodeState.ACTIVE

            try:
                if node.type == NodeType.REASONING:
                    context = harness.context_builder.build(node, graph)
                    result = await harness.llm_client.reason(node.content, context)
                    repl_code = result.get("repl_code")
                    if (isinstance(repl_code, str) and repl_code.strip()
                            and node.metadata.get("repl_rounds", 0) < MAX_REPL_ROUNDS):
                        # RLM-style exploration, graph-native: the model asks
                        # for compute, the topology grows a REPL node with a
                        # flow edge back, and the reasoning node re-fires next
                        # iteration with the output as a neighbor.
                        node.metadata["repl_rounds"] = node.metadata.get("repl_rounds", 0) + 1
                        repl_node = CognitiveNode(
                            type=NodeType.TOOL,
                            content=f"REPL round {node.metadata['repl_rounds']}: {node.content[:60]}",
                            parent_graph_id=graph.id,
                            metadata={"tool": "explore_corpus",
                                      "params": {"path": harness.config.target_path,
                                                 "code": repl_code}},
                        )
                        if harness.governance_check(graph, repl_node):
                            repl_node.state = NodeState.ACTIVE
                            repl_node.result = await harness.tool_registry.execute(
                                "explore_corpus", repl_node.metadata["params"])
                            repl_node.confidence = float(repl_node.result.get("confidence", 0.9))
                            repl_node.state = NodeState.COMPLETED
                        else:
                            repl_node.state = NodeState.FAILED
                        graph.nodes[repl_node.id] = repl_node
                        graph.edges.append(CognitiveEdge(source=repl_node.id, target=node.id,
                                                         edge_type="flow"))
                        node.result = result
                        node.state = NodeState.PENDING  # re-reason with REPL output
                        node.history.append({"state": NodeState.PENDING.value,
                                             "timestamp": datetime.now().isoformat(),
                                             "reason": "repl_exploration",
                                             "round": node.metadata["repl_rounds"]})
                        harness.audit.record("repl_exploration", graph_id=graph.id,
                                             node_id=node.id,
                                             round=node.metadata["repl_rounds"])
                        progressed = True
                        continue
                    node.result = result
                    node.confidence = float(result.get("confidence", 0.5))
                    node.state = NodeState.COMPLETED

                elif node.type == NodeType.TOOL:
                    result = await harness.tool_registry.execute(
                        node.metadata["tool"], node.metadata.get("params", {}))
                    node.result = result
                    node.confidence = float(result.get("confidence", 0.8))
                    node.state = NodeState.COMPLETED

                elif node.type == NodeType.VERIFICATION:
                    targets = [graph.nodes[e.target] for e in graph.edges
                               if e.source == node.id and e.edge_type == "verifies"
                               and e.target in graph.nodes]
                    challenge = await verify_findings(node, targets, harness)
                    node.result = challenge
                    node.confidence = float(challenge.get("confidence", 0.5))
                    node.state = NodeState.COMPLETED
                    if challenge.get("finding_valid", True) is False:
                        await trigger_correction(graph, node, challenge, harness)

                elif node.type == NodeType.GOVERNANCE:
                    node.result = {"compliant": True, "checks": []}
                    node.confidence = 1.0
                    node.state = NodeState.COMPLETED
            except Exception as exc:  # containment: failed node, not lost run
                node.state = NodeState.FAILED
                node.history.append({"reason": "execution_error",
                                     "error": str(exc),
                                     "timestamp": datetime.now().isoformat()})
                harness.audit.record("node_execution_error", graph_id=graph.id,
                                     node_id=node.id, error=str(exc))
                continue

            node.history.append({
                "state": node.state.value,
                "timestamp": datetime.now().isoformat(),
                "confidence": node.confidence,
            })
            progressed = True

        # PHASE 3: GRAPH EVOLUTION — recursive spawning, siblings concurrent
        # Chatty models suggest subgraphs on every response; merged children
        # lift more. Without a round cap the graph spawns until max_iterations
        # and dies "failed" without consolidating (live Run 5 diagnosis).
        if graph.policy.auto_spawn and should_spawn_subgraphs(graph):
            if spawn_rounds >= MAX_SPAWN_ROUNDS:
                dropped = graph.memory_snapshot.pop("spawn_suggestions", [])
                for n in graph.nodes.values():
                    if n.type == NodeType.REASONING:
                        n.metadata["spawn_consumed"] = True
                harness.audit.record("spawn_inhibited", graph_id=graph.id,
                                     reason="max_spawn_rounds", dropped=len(dropped))
            else:
                proposals = generate_spawn_proposals(graph, harness)
                child_ids = []
                for proposal in proposals:
                    child_id = await harness.request_subgraph_spawn(graph.id, proposal)
                    if child_id:
                        child_ids.append(child_id)

                async def _run_child(child):
                    try:
                        return await execute_graph(child, harness)
                    except Exception as exc:  # containment: failed child, not lost run
                        child.state.status = "failed"
                        harness.audit.record("child_execution_error", graph_id=child.id,
                                             error=str(exc))
                        return child

                children = [harness.get_graph(cid) for cid in child_ids]
                if children:
                    spawn_rounds += 1
                    results = await asyncio.gather(*(_run_child(c) for c in children))
                    for child in results:
                        merge_subgraph_results(graph, child)
                    progressed = True

        # PHASE 4: VERIFICATION & CONSOLIDATION (verification spawn = Task 13)
        # NOTE: maybe_spawn_verification + correction can leave NEW pending
        # spawn suggestions in memory_snapshot, so the completion decision
        # must re-check should_spawn_subgraphs AFTER it runs.
        if all_subgraphs_completed(graph, harness):
            if not should_spawn_subgraphs(graph):
                await maybe_spawn_verification(graph, harness)
            if should_spawn_subgraphs(graph) and graph.policy.auto_spawn:
                pass  # pending suggestions: next iteration's phase 3 handles them
            elif _pending_work(graph):
                pass  # executable nodes still queued (e.g. a REPL re-fire
                      # or a freshly wired tool): do not consolidate yet
            else:
                # Coverage gate (root only): don't consolidate while target
                # files went unread. Confidence-triggered verification asks
                # the model to doubt itself; this asks the AUDIT TRAIL what
                # was never looked at. Prediction-error, not vibes.
                missing = (_uncovered_files(harness)
                           if graph.parent_graph_id is None else [])
                if (missing and graph.policy.auto_spawn
                        and "coverage_swept" not in graph.memory_snapshot):
                    graph.memory_snapshot["coverage_swept"] = [f.name for f in missing]
                    harness.audit.record("coverage_sweep", graph_id=graph.id,
                                         missing=[f.name for f in missing])
                    for f in missing[:3]:
                        cid = await harness.request_subgraph_spawn(graph.id, {
                            "loop_type": LoopType.EXECUTION,
                            "objective": f"Coverage sweep: security analysis of {f.name}",
                            "reason": "coverage_gap",
                            "target_path": str(f),
                        })
                        if cid:
                            child = await execute_graph(harness.get_graph(cid), harness)
                            merge_subgraph_results(graph, child)
                            progressed = True
                else:
                    avg = _avg_confidence(graph)
                    if avg >= graph.state.confidence_threshold:
                        graph.state.status = "completed"
                    elif graph.state.iteration >= graph.state.max_iterations - 1:
                        graph.state.status = "failed"

        # PHASE 5: LEARNING
        harness.learning_engine.record_pathway(graph)

        # Stagnation guard: never spin without progress
        if not progressed and graph.state.status == "running":
            avg = _avg_confidence(graph)
            graph.state.status = ("completed" if avg >= graph.state.confidence_threshold
                                  else "failed")
            harness.audit.record("stagnation_stop", graph_id=graph.id, avg_confidence=avg)

        graph.state.iteration += 1

    graph.state.completed_at = datetime.now()
    return graph


async def maybe_spawn_verification(graph: CognitiveGraph, harness: Harness) -> None:
    """Under-confident findings get challenged by a dedicated VERIFICATION
    subgraph — the ACC firing on conflict. Trigger: any COMPLETED reasoning
    node below the confidence threshold (deterministic, auditable)."""
    if not graph.policy.require_verification:
        return
    if any(n.type == NodeType.VERIFICATION for n in graph.nodes.values()):
        return
    for sid in graph.subgraph_ids:
        child = harness.get_graph(sid)
        if child is not None and child.loop_type == LoopType.VERIFICATION:
            return
    weak_reasoning = any(
        n.type == NodeType.REASONING and n.state == NodeState.COMPLETED
        and n.confidence < graph.state.confidence_threshold
        for n in graph.nodes.values()
    )
    if not weak_reasoning:
        return
    findings = _collect_findings(graph)
    if not findings:
        return
    v_id = await harness.request_subgraph_spawn(graph.id, {
        "loop_type": LoopType.VERIFICATION,
        "objective": f"Verify: {graph.state.objective}",
        "reason": "low_confidence_verification",
        "target_findings": findings,
    })
    if v_id:
        v_graph = await execute_graph(harness.get_graph(v_id), harness)
        merge_subgraph_results(graph, v_graph)


async def trigger_correction(graph: CognitiveGraph, node: CognitiveNode,
                             challenge: dict, harness: Harness) -> None:
    """Topological correction: a NEW execution graph with stricter
    parameters is born under the challenged graph's parent. The original
    pathway is marked CORRECTING, then strengthened on success."""
    parent = harness.get_graph(graph.parent_graph_id)
    if parent is None:
        return
    child_id = await harness.request_subgraph_spawn(parent.id, {
        "loop_type": LoopType.EXECUTION,
        "objective": f"STRICT RE-ANALYSIS: {parent.state.objective}",
        "reason": "correction",
        "target_path": harness.config.target_path,
    })
    if not child_id:
        harness.audit.record("correction_rejected", graph_id=parent.id)
        return
    corrected = await execute_graph(harness.get_graph(child_id), harness)
    corrected_confidence = _avg_confidence(corrected)

    now = datetime.now().isoformat()
    for n in parent.nodes.values():
        if (n.type == NodeType.REASONING and n.state == NodeState.COMPLETED
                and n.confidence < parent.state.confidence_threshold):
            n.state = NodeState.CORRECTING
            n.history.append({"state": NodeState.CORRECTING.value, "timestamp": now,
                              "reason": "verification_challenged"})
            n.confidence = corrected_confidence
            n.state = NodeState.COMPLETED
            n.history.append({"state": NodeState.COMPLETED.value, "timestamp": now,
                              "correction_success": True,
                              "confidence": corrected_confidence})
    parent.state.correction_count += 1
    merge_subgraph_results(parent, corrected)
    harness.audit.record("correction_completed", graph_id=parent.id,
                         corrected_graph=child_id,
                         new_confidence=corrected_confidence)


async def verify_findings(node: CognitiveNode, target_nodes: list,
                          harness: Harness) -> dict:
    challenged = [t for t in target_nodes if t.metadata.get("challenged_finding")]
    if not challenged:
        return {"finding_valid": True, "confidence": 0.5, "detail": "no_targets"}
    decision = harness.gate.check("llm_call", {"calls_so_far": harness.total_llm_calls})
    if not decision.allowed:
        harness.audit.record("governance_denied", graph_id=node.parent_graph_id,
                             node_id=node.id, reason=decision.reason)
        return {"finding_valid": True, "confidence": 0.0, "detail": "budget_exhausted"}
    challenged_text = "\n".join(
        f"- {t.metadata['challenged_finding']}" for t in challenged
    )
    result = await harness.llm_client.reason(
        f"Challenge finding: {node.content}",
        f"FINDINGS UNDER CHALLENGE:\n{challenged_text}",
    )
    result.setdefault("finding_valid", True)
    return result


def should_spawn_subgraphs(graph: CognitiveGraph) -> bool:
    if graph.memory_snapshot.get("spawn_suggestions"):
        return True
    return any(
        n.type == NodeType.REASONING
        and n.state == NodeState.COMPLETED
        and n.confidence >= graph.state.confidence_threshold
        and isinstance(n.result, dict)
        and n.result.get("suggested_subgraphs")
        and not n.metadata.get("spawn_consumed")
        for n in graph.nodes.values()
    )


def generate_spawn_proposals(graph: CognitiveGraph, harness: Harness) -> list[dict]:
    suggestions = list(graph.memory_snapshot.pop("spawn_suggestions", []))
    for n in graph.nodes.values():
        if (n.type == NodeType.REASONING and n.state == NodeState.COMPLETED
                and n.confidence >= graph.state.confidence_threshold
                and isinstance(n.result, dict) and n.result.get("suggested_subgraphs")
                and not n.metadata.get("spawn_consumed")):
            suggestions.extend(n.result["suggested_subgraphs"])
            n.metadata["spawn_consumed"] = True
    return [
        {"loop_type": LoopType.EXECUTION, "objective": s,
         "reason": "decomposition", "target_path": harness.config.target_path}
        for s in suggestions[:3]
    ]


def merge_subgraph_results(parent: CognitiveGraph, child: CognitiveGraph) -> None:
    findings = _collect_findings(child)
    if findings:
        parent.memory_snapshot.setdefault("merged_findings", []).extend(
            {"from_graph": child.id, **f} for f in findings)
    suggestions = [
        s for n in child.nodes.values()
        if isinstance(n.result, dict) and n.confidence >= child.state.confidence_threshold
        for s in n.result.get("suggested_subgraphs", [])
    ]
    if suggestions:
        parent.memory_snapshot.setdefault("spawn_suggestions", []).extend(suggestions)
    if child.state.correction_count:
        parent.state.correction_count += child.state.correction_count


def _pending_work(graph: CognitiveGraph) -> bool:
    """Executable nodes still queued. Consolidating over a PENDING
    reasoning node (e.g. one mid-REPL-loop) silently discards its work."""
    return any(
        n.type in (NodeType.REASONING, NodeType.TOOL, NodeType.VERIFICATION,
                   NodeType.GOVERNANCE)
        and n.state in (NodeState.PENDING, NodeState.ACTIVE)
        for n in graph.nodes.values()
    )


def _uncovered_files(harness: Harness) -> list:
    """Target files that never appeared in any node's tool output.
    Deterministic coverage accounting from the audit substrate — the
    signal verification should fire on when the model won't doubt itself."""
    target = Path(harness.config.target_path)
    if not target.is_dir():
        return []
    seen = set()
    for g in harness.graphs.values():
        for n in g.nodes.values():
            if isinstance(n.result, dict):
                seen.update(re.findall(r"===== (\S+\.py) =====", json.dumps(n.result)))
    return [f for f in sorted(target.glob("*.py")) if f.name not in seen]


def all_subgraphs_completed(graph: CognitiveGraph, harness: Harness) -> bool:
    for sid in graph.subgraph_ids:
        child = harness.get_graph(sid)
        if child is not None and child.state.status not in ("completed", "failed"):
            return False
    return True


def _avg_confidence(graph: CognitiveGraph) -> float:
    completed = [n for n in graph.nodes.values() if n.state == NodeState.COMPLETED]
    return (sum(n.confidence for n in completed) / len(completed)) if completed else 0.0


def _collect_findings(graph: CognitiveGraph) -> list[dict]:
    out = []
    for n in graph.nodes.values():
        if n.state != NodeState.COMPLETED or not isinstance(n.result, dict):
            continue
        if "finding" in n.result:
            out.append({"finding": n.result["finding"], "confidence": n.confidence,
                        "node": n.id})
        elif "findings" in n.result:
            out.extend({"finding": f, "confidence": n.confidence, "node": n.id}
                       for f in n.result["findings"])
    return out


def _dependency_order(nodes: list, edges: list) -> list:
    """Active nodes sorted so flow/dependency sources execute first;
    activation order preserved within a level; cycles fall back safely."""
    ids = {n.id for n in nodes}
    deps = {n.id: set() for n in nodes}
    for e in edges:
        if e.source in ids and e.target in ids and e.edge_type in ("flow", "dependency"):
            deps[e.target].add(e.source)
    remaining = {n.id: n for n in nodes}
    ordered = []
    while remaining:
        ready = [nid for nid in remaining if not (deps[nid] & set(remaining))]
        if not ready:
            ready = list(remaining)
        for nid in ready:
            ordered.append(remaining.pop(nid))
    return ordered
