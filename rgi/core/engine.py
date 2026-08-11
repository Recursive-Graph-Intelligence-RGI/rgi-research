"""The RGI execution loop — the heart of the system. Five phases per
iteration: activation, node execution, recursive spawning, verification &
consolidation, learning. The LLM is called inside nodes only; every
orchestration decision is made here and in the Harness, and is audited."""
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from rgi.core.findings import format_finding_for_prompt, normalize_finding
from rgi.core.harness import Harness
from rgi.core.models import (
    CognitiveEdge, CognitiveGraph, CognitiveNode, LoopType, NodeState, NodeType,
)

ACTIVATION_THRESHOLD = 0.5
MAX_SPAWN_ROUNDS = int(os.environ.get("RGI_MAX_SPAWN_ROUNDS", "2"))  # per-graph; chatty models re-seed suggestions every merge
MAX_REPL_ROUNDS = 2   # per-node; bounded model-driven corpus exploration
MAX_SPAWN_PER_ROUND = int(os.environ.get("RGI_MAX_SPAWN_PER_ROUND", "3"))  # suggestions[:N]
COVERAGE_SWEEP_MAX = int(os.environ.get("RGI_COVERAGE_SWEEP_MAX", "3"))    # missing[:N] per sweep


async def execute_graph(graph: CognitiveGraph, harness: Harness) -> CognitiveGraph:
    spawn_rounds = 0
    frontier_plan = None
    if (graph.parent_graph_id is None
            and harness.frontier_config.enabled
            and harness.frontier_config.plan_at_start):
        world_model = graph.memory_snapshot.get("world_model", {})
        frontier_plan = await harness.frontier.plan_root(graph.state.objective, world_model)
        if frontier_plan:
            harness.audit.record("frontier_plan", graph_id=graph.id,
                                 strategy=frontier_plan.strategy,
                                 objectives=len(frontier_plan.initial_subgraph_objectives))
            suggestions = graph.memory_snapshot.setdefault("spawn_suggestions", [])
            for obj in frontier_plan.initial_subgraph_objectives:
                if isinstance(obj, str) and obj.strip():
                    suggestions.append({
                        "loop_type": LoopType.EXECUTION,
                        "objective": obj,
                        "reason": "frontier_plan",
                        "target_path": harness.config.target_path,
                    })
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
        for n in graph.nodes.values():  # replan lift survives re-scoring
            if n.metadata.pop("force_fire", False):
                n.activation = 1.0
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
                    context = harness.context_builder.build(
                        node, graph,
                        tools=harness.tool_registry.list_tools_for_prompt())
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
                                     "error": f"{type(exc).__name__}: {exc}",
                                     "timestamp": datetime.now().isoformat()})
                harness.audit.record("node_execution_error", graph_id=graph.id,
                                     node_id=node.id,
                                     error=f"{type(exc).__name__}: {exc}")
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
        if graph.policy.auto_spawn and should_spawn_subgraphs(graph, harness):
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
            if needs_frontier_arbitration(graph, harness):
                state_pkg = {
                    "objective": graph.state.objective,
                    "iteration": graph.state.iteration,
                    "max_iterations": graph.state.max_iterations,
                    "avg_confidence": _avg_confidence(graph),
                    "findings": _collect_findings(graph),
                    "contradictions": _detect_contradictions(_collect_findings(graph)),
                }
                try:
                    arb = await harness.frontier.arbitrate(state_pkg)
                except Exception as exc:
                    harness.audit.record("frontier_fallback", graph_id=graph.id,
                                         phase="arbitrate", error=str(exc))
                    arb = None
                graph.memory_snapshot["frontier_arbitration_count"] = graph.memory_snapshot.get("frontier_arbitration_count", 0) + 1
                if arb:
                    harness.audit.record("frontier_arbitration", graph_id=graph.id,
                                         decision=arb.decision, reasoning=arb.reasoning)
                    if arb.decision == "respawn":
                        for obj in arb.spawn_objectives:
                            if isinstance(obj, str) and obj.strip():
                                graph.memory_snapshot.setdefault("spawn_suggestions", []).append({
                                    "loop_type": LoopType.EXECUTION,
                                    "objective": obj,
                                    "reason": "frontier_arbitration",
                                    "target_path": harness.config.target_path,
                                })
                    elif arb.decision == "drop":
                        graph.memory_snapshot["dropped_findings"] = set(arb.findings_to_drop)
            if not should_spawn_subgraphs(graph, harness):
                await maybe_spawn_verification(graph, harness)
            if should_spawn_subgraphs(graph, harness) and graph.policy.auto_spawn:
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
                    for f in missing[:COVERAGE_SWEEP_MAX]:
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

        # Stagnation guard: stall → REPLAN once (Magentic-style), then stop.
        # A stall with queued nodes is an attention failure — activation
        # cooled them — not a work failure. Force-fire them once; if the
        # graph stalls again with nothing learned, then stop.
        if not progressed and graph.state.status == "running":
            cooled = [n for n in graph.nodes.values()
                      if n.type in (NodeType.REASONING, NodeType.TOOL,
                                    NodeType.VERIFICATION, NodeType.GOVERNANCE)
                      and n.state == NodeState.PENDING]
            if cooled and not graph.memory_snapshot.get("replanned"):
                graph.memory_snapshot["replanned"] = True
                for n in cooled:
                    n.metadata["force_fire"] = True
                harness.audit.record("replan", graph_id=graph.id,
                                     lifted=[n.id for n in cooled])
            else:
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
        "confidence_threshold": graph.state.confidence_threshold,
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


async def _read_source_for_finding(harness: Harness, finding: dict) -> str:
    """Read the cited file/line for a finding to ground verification."""
    path = finding.get("file")
    line = finding.get("line")
    if not path:
        return ""
    try:
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            return ""
        lines = p.read_text(errors="replace").splitlines()
        if line is None or line < 1 or line > len(lines):
            return "\n".join(lines[:20])
        start = max(0, line - 3)
        end = min(len(lines), line + 2)
        return "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, end))
    except Exception as exc:
        return f"[could not read source: {exc}]"


async def verify_findings(node: CognitiveNode, target_nodes: list,
                          harness: Harness) -> dict:
    # Challenge any completed reasoning node that is ungrounded or below threshold.
    challenged = [t for t in target_nodes if t.metadata.get("challenged_finding")]
    threshold = node.metadata.get("confidence_threshold", 0.7)
    challenged_ids = {t.id for t in challenged}
    auto_challenge = [
        t for t in target_nodes
        if t.type == NodeType.REASONING
        and t.state == NodeState.COMPLETED
        and t.confidence < threshold
        and not _is_grounded(t.result)
        and t.id not in challenged_ids
    ]
    for t in auto_challenge:
        if isinstance(t.result, dict):
            t.metadata["challenged_finding"] = t.result.get("finding", t.result)
        else:
            t.metadata["challenged_finding"] = t.result
        challenged.append(t)
    if not challenged:
        return {"finding_valid": True, "confidence": 0.5, "detail": "no_targets"}
    decision = harness.gate.check("llm_call", {"calls_so_far": harness.total_llm_calls})
    if not decision.allowed:
        harness.audit.record("governance_denied", graph_id=node.parent_graph_id,
                             node_id=node.id, reason=decision.reason)
        return {"finding_valid": True, "confidence": 0.0, "detail": "budget_exhausted"}

    # Build grounded evidence by reading the source for each finding.
    items = []
    for t in challenged:
        finding = t.metadata["challenged_finding"]
        source = await _read_source_for_finding(harness, finding)
        items.append({"finding": format_finding_for_prompt(finding), "source": source})

    challenged_text = "\n\n".join(
        f"FINDING: {it['finding']}\nSOURCE:\n{it['source']}" for it in items
    )
    result = await harness.llm_client.reason(
        f"Challenge finding: {node.content}",
        f"Determine whether each finding is valid based on the actual source code. "
        f"Return finding_valid: bool and reasoning.\n\n{challenged_text}",
    )
    result.setdefault("finding_valid", True)
    return result


def _tool_has_pending_verification(n: CognitiveNode, harness: Harness) -> bool:
    if n.type != NodeType.TOOL or n.state != NodeState.COMPLETED:
        return False
    if n.metadata.get("verification_queued"):
        return False
    tool = harness.tool_registry.get_tool(n.metadata.get("tool", ""))
    return bool(tool and tool.verifier)


def should_spawn_subgraphs(graph: CognitiveGraph, harness: Harness | None = None) -> bool:
    if graph.memory_snapshot.get("spawn_suggestions"):
        return True
    if harness is not None and any(
        _tool_has_pending_verification(n, harness) for n in graph.nodes.values()
    ):
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


def _queue_tool_verifications(graph: CognitiveGraph, harness: Harness) -> None:
    """Auto-spawn verification subgraphs for findings from tools that declare a verifier."""
    for n in graph.nodes.values():
        if (n.type != NodeType.TOOL or n.state != NodeState.COMPLETED
                or n.metadata.get("verification_queued")):
            continue
        tool = harness.tool_registry.get_tool(n.metadata.get("tool", ""))
        if not tool or not tool.verifier:
            continue
        verifier = tool.verifier
        result = n.result if isinstance(n.result, dict) else {}
        findings = result.get("findings", [])
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            template = verifier.get("objective_template",
                                    "Verify {kind} finding at {file}:{line}")
            try:
                objective = template.format(**finding)
            except Exception:
                objective = (
                    f"Verify {finding.get('kind', 'finding')} at "
                    f"{finding.get('file', '?')}:{finding.get('line', '?')}"
                )
            graph.memory_snapshot.setdefault("spawn_suggestions", []).append({
                "loop_type": verifier.get("loop_type", LoopType.VERIFICATION),
                "objective": objective,
                "reason": "tool_verification",
                "target_findings": [finding],
                "target_path": harness.config.target_path,
            })
        n.metadata["verification_queued"] = True


def generate_spawn_proposals(graph: CognitiveGraph, harness: Harness) -> list[dict]:
    _queue_tool_verifications(graph, harness)
    raw_suggestions = list(graph.memory_snapshot.pop("spawn_suggestions", []))
    proposals = []
    for s in raw_suggestions[:MAX_SPAWN_PER_ROUND]:
        if isinstance(s, dict):
            proposals.append(s)
        elif isinstance(s, str) and s.strip():
            proposals.append({
                "loop_type": LoopType.EXECUTION,
                "objective": s,
                "reason": "decomposition",
                "target_path": harness.config.target_path,
            })
    for n in graph.nodes.values():
        if (n.type == NodeType.REASONING and n.state == NodeState.COMPLETED
                and n.confidence >= graph.state.confidence_threshold
                and isinstance(n.result, dict) and n.result.get("suggested_subgraphs")
                and not n.metadata.get("spawn_consumed")):
            for sg in n.result["suggested_subgraphs"][:MAX_SPAWN_PER_ROUND]:
                if isinstance(sg, str) and sg.strip():
                    proposals.append({
                        "loop_type": LoopType.EXECUTION,
                        "objective": sg,
                        "reason": "decomposition",
                        "target_path": harness.config.target_path,
                    })
            n.metadata["spawn_consumed"] = True
    return proposals[:MAX_SPAWN_PER_ROUND]


def _keep_finding(f: dict) -> bool:
    return bool(f.get("grounded") or f.get("confidence", 0) >= 0.85)


def merge_subgraph_results(parent: CognitiveGraph, child: CognitiveGraph) -> None:
    findings = [f for f in _collect_findings(child) if _keep_finding(f)]
    if findings:
        parent.memory_snapshot.setdefault("merged_findings", []).extend(
            {"from_graph": child.id, **f} for f in findings
        )
        ledger = parent.memory_snapshot.get("ledger")
        if isinstance(ledger, dict):
            ledger.setdefault("facts", []).extend(
                f"{f['kind']} in {f.get('file', '?')}:{f.get('line', '?')} — {f.get('detail', '')}"
                for f in findings
                if f.get("confidence", 0) >= child.state.confidence_threshold)
    suggestions = [
        s for n in child.nodes.values()
        if isinstance(n.result, dict) and n.confidence >= child.state.confidence_threshold
        # null/malformed suggestions (models emit null at higher complexity) —
        # unguarded iteration here crashed 4b L4 cells in the C1 matrix
        for s in (n.result.get("suggested_subgraphs") or [])
        if isinstance(s, str) and s.strip()
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
    return [f for f in sorted(target.rglob("*.py")) if f.name not in seen]


def all_subgraphs_completed(graph: CognitiveGraph, harness: Harness) -> bool:
    for sid in graph.subgraph_ids:
        child = harness.get_graph(sid)
        if child is not None and child.state.status not in ("completed", "failed"):
            return False
    return True


def _avg_confidence(graph: CognitiveGraph) -> float:
    """Aggregate confidence for the completion gate. Must include merged
    subgraph findings — Run 11 showed roots 'failing' at 0.6 while their
    own report scored 0.9: the gate counted only the root's own nodes
    (planning + a REPL-error node), the report counted everything."""
    confs = [n.confidence for n in graph.nodes.values() if n.state == NodeState.COMPLETED]
    confs += [float(f.get("confidence", 0.5))
              for f in graph.memory_snapshot.get("merged_findings", [])]
    return sum(confs) / len(confs) if confs else 0.0


def _is_grounded(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    finding = result.get("finding", result)
    if not isinstance(finding, dict):
        return False
    return bool(finding.get("file") or finding.get("line") or finding.get("symbol"))


def _collect_findings(graph: CognitiveGraph) -> list[dict]:
    out = []
    for n in graph.nodes.values():
        if n.state != NodeState.COMPLETED or not isinstance(n.result, dict):
            continue
        candidates = []
        if "finding" in n.result:
            candidates.append(n.result["finding"])
        elif "findings" in n.result:
            candidates.extend(n.result["findings"])
        for raw in candidates:
            normalized = normalize_finding(raw)
            if normalized is not None:
                normalized.update({"confidence": n.confidence, "node": n.id})
                out.append(normalized)
    return out


def _detect_contradictions(findings: list[dict]) -> list[dict]:
    """Find groups of findings at the same location."""
    by_loc: dict[tuple, list[dict]] = {}
    for f in findings:
        loc = (f.get("file"), f.get("line"), f.get("symbol"))
        by_loc.setdefault(loc, []).append(f)
    return [{"location": loc, "findings": group}
            for loc, group in by_loc.items() if len(group) > 1]


def needs_frontier_arbitration(graph: CognitiveGraph, harness: Harness) -> bool:
    if not harness.frontier_config.enabled or not harness.frontier_config.arbitrate_on_deadlock:
        return False
    arbitration_count = graph.memory_snapshot.get("frontier_arbitration_count", 0)
    if arbitration_count >= harness.frontier_config.max_arbitration_calls:
        return False
    avg = _avg_confidence(graph)
    if graph.state.iteration >= graph.state.max_iterations - 1 and avg < graph.state.confidence_threshold:
        return True
    contradictions = _detect_contradictions(_collect_findings(graph))
    if contradictions:
        return True
    rejected = sum(1 for e in harness.audit.events
                   if e.get("event") == "spawn_rejected" and e.get("graph_id") == graph.id)
    if rejected >= 3:
        return True
    return False


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
