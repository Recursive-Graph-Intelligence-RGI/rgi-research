# RGI Adaptive Spawn Search — Design Spec

> **Date:** 2026-08-11  
> **Status:** design approved, ready for implementation plan  
> **Related:** `docs/superpowers/specs/2026-08-11-rgi-hybrid-local-frontier-integration-design.md`, `docs/superpowers/plans/2026-08-10-rgi-v0.3-noise-reduction.md`, `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md`

## 1. Motivation

RGI's core architecture is recursive graph intelligence: a root graph spawns planning, execution, verification, and knowledge subgraphs, each of which can spawn further subgraphs. Today the decision of *what* to spawn next is governed by fixed heuristic thresholds in `rgi/core/engine.py`:

- `should_spawn_subgraphs`
- `_queue_tool_verifications`
- `needs_frontier_arbitration`

These thresholds work on small targets but do not adapt to target size, vulnerability distribution, model capacity, or remaining budget. They are not learning and they are not search.

Recent work in AI-discovered algorithms — [AlphaDev](https://www.nature.com/articles/s41586-023-06004-9) (assembly-game search), [FunSearch](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/Mathematical-discoveries-from-program-search-with-large-language-models.pdf) (LLM + evolutionary program search), [AlphaEvolve](https://arxiv.org/abs/2506.13131) (evolutionary coding agent), [DiscoRL](https://www.nature.com/articles/s41586-025-09761-x) (discovered RL rules), and [ERA](https://arxiv.org/html/2509.06503v1) (LLM + tree search for empirical software) — shows that the highest-leverage move is often to treat computation itself as a search space:

> generate candidate → execute/evaluate → select best → mutate/recombine → repeat.

For RGI, the natural search space is not Python source code but **graph action selection**: which subgraph to spawn, verify, explore, or stop. This spec adds a lightweight tree-search layer over RGI's spawn decisions while leaving the existing spawn/REPL/verify execution substrate unchanged.

## 2. Goal

Replace fixed heuristic spawn thresholds with a one-ply search that, at each decision point, evaluates candidate next actions and picks the one with the highest expected information gain per estimated cost. The recursive graph remains the execution engine; only the *decision policy* becomes adaptive.

## 3. Non-goals

- This spec does not evolve Python source code (that is a later milestone).
- It does not change LLM prompts, scanners, or tools.
- It does not replace the frontier integration; it decides when to invoke it.
- It does not require training data from past runs in v1 (value estimator is heuristic).

## 4. Architecture

### 4.1 New module: `rgi/core/spawn_search.py`

Responsibilities:
- Generate candidate actions from the current graph state.
- Score each action with a cheap value estimator.
- Select the best action using UCT (initially one-ply).
- Provide a fallback to the existing heuristic logic.

### 4.2 Action model

```python
@dataclass
class SpawnAction:
    action_type: str   # "verify_tool", "execution_sweep", "repl_explore",
                       # "frontier_arbitrate", "stop"
    objective: str     # human-readable objective passed to subgraph
    target_files: list[str]
    reason: str        # why this action was generated
    estimated_cost: int  # estimated LLM calls
    metadata: dict     # loop_type, target findings, etc.
```

### 4.3 Search node

```python
@dataclass
class SpawnNode:
    state_snapshot: dict  # {covered_files, pending_findings, avg_confidence,
                          #  remaining_budget, contradictions}
    action: SpawnAction | None  # action that led to this node
    parent: SpawnNode | None
    children: list[SpawnNode]
    visits: int = 0
    total_value: float = 0.0
```

### 4.4 Value estimator

```python
def estimate_value(graph: CognitiveGraph, action: SpawnAction) -> float:
    coverage_bonus = coverage_gap_after_action(graph, action)
    tool_signal = tool_verifier_expected_yield(graph, action)
    confidence_penalty = avg_confidence_risk(graph, action)
    cost = action.estimated_cost
    return (coverage_bonus + tool_signal) / (cost + confidence_penalty + 1e-9)
```

Heuristic components (v1):
- `coverage_bonus(graph, action)`: count of files in `target_files` not already covered by a completed execution subgraph. Returns 0 for non-sweep actions.
- `tool_signal(graph, action)`: count of tool findings in the action's metadata that have a registered verifier and have not yet triggered a verification subgraph. Returns 0 for non-verify actions.
- `confidence_penalty(graph, action)`: for `repl_explore`, `1 - mean(confidence of target reasoning nodes)`; for other actions, 0.
- `cost`: see defaults above.

A learned value function may replace or augment these heuristics in a future spec.

### 4.5 Decision entry point

```python
async def decide_next_action(
    graph: CognitiveGraph,
    harness: Harness,
) -> SpawnAction | None:
    """Return the best next action or None if the engine should stop."""
```

Called from the main engine loop instead of `should_spawn_subgraphs`.

## 5. Integration with existing engine

Current engine flow:

```
execute_graph
  → run nodes
  → if should_spawn_subgraphs: spawn children
  → if needs_frontier_arbitration: arbitrate
  → repeat
```

New flow:

```
execute_graph
  → run nodes
  → action = decide_next_action(graph, harness)
  → if action is None or action.action_type == "stop": break
  → execute_action(graph, harness, action)
  → repeat
```

`execute_action(graph, harness, action)` dispatches to existing machinery without duplicating logic:
- `verify_tool` → calls `_queue_tool_verifications(graph, harness)` restricted to the findings in `action.metadata["target_findings"]`; then spawns verification subgraphs through the existing `request_subgraph_spawn` path.
- `execution_sweep` → builds an execution subgraph objective for `action.target_files` and calls the existing execution-spawn path.
- `repl_explore` → marks the target reasoning nodes in `action.metadata["target_nodes"]` for REPL exploration and invokes the existing REPL handler.
- `frontier_arbitrate` → calls `harness.frontier.arbitrate(...)` using the existing deadlock state package.
- `stop` → returns without spawning; the main loop exits.

Existing subgraph execution, verification, and frontier code is reused unchanged.

## 6. Candidate action generation

From the current graph state, generate actions of each type:

| action_type | trigger |
|-------------|---------|
| `verify_tool` | Completed tool nodes with `findings` and a registered `verifier`. |
| `execution_sweep` | Files in the world model not yet covered by a completed execution subgraph. |
| `repl_explore` | Completed reasoning nodes with confidence below threshold and ungrounded findings. |
| `frontier_arbitrate` | Deadlock signals: max iterations, contradictions, repeated spawn rejections. |
| `stop` | Always included; selected when no other action has positive value. |

## 7. Selection algorithm (v1)

One-ply search:

1. Generate candidate actions.
2. Score each with `estimate_value`.
3. Select `argmax`.

UCT formula is reserved for v2 if multi-ply expansion proves useful:

```python
uct = mean_value + c * sqrt(log(parent_visits) / child_visits)
```

The selection is deterministic by default; optional temperature may be added later for exploration.

## 8. Configuration and enablement

Feature is disabled by default. Enable with:

```bash
export RGI_SPAWN_SEARCH=1
```

Optional tuning:
- `RGI_SPAWN_SEARCH_MAX_TIME=1` — seconds per decision (default 1).
- `RGI_SPAWN_SEARCH_EXPLORATION=1.414` — UCT exploration constant (unused in v1 one-ply mode).

## 9. Safety and fallback

- If `decide_next_action` raises or returns no actions, fall back to the existing `should_spawn_subgraphs` heuristic.
- The fallback is logged in the audit trail.
- Maximum search time per decision is capped (default 1 second).
- Existing tests must pass with the feature disabled.

## 10. Telemetry

Each decision records:
- candidate actions and scores
- selected action and reason
- fallback usage, if any

Records go to `harness.audit` under event name `spawn_search_decision`.

## 11. Validation plan

| test | how |
|------|-----|
| Unit | `tests/core/test_spawn_search.py`: action generation, value estimator, selection. |
| Mock integration | Enable `RGI_SPAWN_SEARCH=1` with mock LLM; run must complete. |
| Benchmark A/B | Compare `RGI_SPAWN_SEARCH=1` vs baseline on `sample_project` and `vuln_app_2`. |
| Regression | Existing test suite passes with feature disabled. |

## 12. Success criteria

- `RGI_SPAWN_SEARCH=1` completes without errors on all benchmark targets.
- Recall on `vuln_app_2` and `sample_project` is ≥ baseline.
- LLM calls are ≤ baseline or the recall/call ratio improves.
- No regressions in the 185-test suite.

## 13. Future directions

- **Multi-ply MCTS:** expand the tree multiple steps with learned value estimates.
- **Learned value function:** train a small model on past RGI runs to predict which actions lead to findings.
- **Evolved tools:** combine with FunSearch-style tool evolution so the action space itself improves.
- **Meta-policy (DiscoRL-style):** learn a control policy for when to search deeply vs stop.

## 14. Relation to RGI vision

This spec keeps the recursive graph, REPL, local models, and frontier exactly where they are. It adds an adaptive decision layer on top — the first step toward RGI discovering how its own computation should be organized.
