# RGI Adaptive Spawn Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Note to implementer:** All test snippets in this plan belong in `tests/core/test_spawn_search.py`; add `import os` and `from unittest.mock import SimpleNamespace` at the top of that file once created.

**Goal:** Add a lightweight one-ply search layer to RGI that selects the next spawn/verify/explore/arbitrate/stop action based on expected information gain per cost, replacing the fixed heuristic thresholds in `rgi/core/engine.py`.

**Architecture:** A new `rgi/core/spawn_search.py` module exposes `decide_next_action(graph, harness)` which generates candidate `SpawnAction`s, scores them with a cheap heuristic value estimator, and returns the best. `rgi/core/engine.py` calls this function at the existing spawn decision point and dispatches the returned action to existing subgraph/REPL/frontier machinery. The feature is disabled by default and enabled via `RGI_SPAWN_SEARCH=1`.

**Tech Stack:** Python 3.11+, existing RGI `CognitiveGraph`/`Harness` models, pytest.

## Global Constraints

- Every new Python module must have tests.
- Existing CLI/benchmarks must stay green.
- Feature is disabled by default; no behavior change without `RGI_SPAWN_SEARCH=1`.
- Do not modify `/home/jeff/projects/rlmlocal-site` or FortSignal code.
- Keep changes minimal — no speculative generality.

---

## File Structure

| file | responsibility |
|------|----------------|
| `rgi/core/spawn_search.py` | `SpawnAction`, `SpawnNode`, action generation, value estimator, `decide_next_action`, fallback wrapper. |
| `tests/core/test_spawn_search.py` | Unit tests for action generation, scoring, selection, fallback. |
| `rgi/core/engine.py:172-247` | Integrate `decide_next_action`; dispatch returned actions; keep heuristic fallback. |
| `rgi/cli.py:139-146` | Parse `RGI_SPAWN_SEARCH`, `RGI_SPAWN_SEARCH_MAX_TIME` env vars and pass to `FrontierConfig`/harness (or store on `HarnessConfig`). |
| `rgi/core/harness.py:31` | Add `spawn_search_enabled` and `spawn_search_max_time` fields to `HarnessConfig`. |

---

## Task 1: `SpawnAction` and `SpawnNode` data classes

**Files:**
- Create: `rgi/core/spawn_search.py`
- Test: `tests/core/test_spawn_search.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SpawnAction`, `SpawnNode` dataclasses with fields documented in the spec.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_spawn_search.py
import os
from unittest.mock import SimpleNamespace

from rgi.core.models import (
    CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType,
    NodeState, NodeType,
)
from rgi.core.spawn_search import (
    SpawnAction, SpawnNode, decide_next_action, estimate_value,
    generate_candidate_actions,
)


def test_spawn_action_has_required_fields():
    action = SpawnAction(
        action_type="execution_sweep",
        objective="Analyze db.py",
        target_files=["db.py"],
        reason="coverage_gap",
        estimated_cost=3,
        metadata={"loop_type": "execution"},
    )
    assert action.action_type == "execution_sweep"
    assert action.estimated_cost == 3


def test_spawn_node_defaults():
    action = SpawnAction("stop", "", [], "stop", 0, {})
    node = SpawnNode(state_snapshot={}, action=action, parent=None, children=[])
    assert node.visits == 0
    assert node.total_value == 0.0
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rgi.core.spawn_search'`.

- [ ] **Step 2: Write minimal implementation**

```python
# rgi/core/spawn_search.py
"""Adaptive spawn search for RGI graph action selection."""
from dataclasses import dataclass, field


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
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add rgi/core/spawn_search.py tests/core/test_spawn_search.py
git commit -m "feat(spawn_search): add SpawnAction and SpawnNode dataclasses"
```

---

## Task 2: Candidate action generation

**Files:**
- Modify: `rgi/core/spawn_search.py`
- Test: `tests/core/test_spawn_search.py`

**Interfaces:**
- Consumes: `CognitiveGraph`, `Harness`.
- Produces: `generate_candidate_actions(graph, harness) -> list[SpawnAction]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_spawn_search.py


def _make_graph():
    graph = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="test", max_iterations=10),
        policy=GraphPolicy(auto_spawn=True),
    )
    graph.memory_snapshot["world_model"] = {
        "files": ["a.py", "b.py"],
    }
    return graph


def test_generates_stop_action():
    graph = _make_graph()
    actions = generate_candidate_actions(graph, object())
    assert any(a.action_type == "stop" for a in actions)


def test_generates_execution_sweep_for_uncovered_files():
    graph = _make_graph()
    actions = generate_candidate_actions(graph, object())
    sweep = [a for a in actions if a.action_type == "execution_sweep"]
    assert len(sweep) == 1
    assert "a.py" in sweep[0].target_files
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: FAIL — `generate_candidate_actions` not defined.

- [ ] **Step 2: Write minimal implementation**

```python
# rgi/core/spawn_search.py
from rgi.core.models import CognitiveGraph, NodeState, NodeType


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
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add rgi/core/spawn_search.py tests/core/test_spawn_search.py
git commit -m "feat(spawn_search): generate stop and execution-sweep actions"
```

---

## Task 3: Value estimator and action selection

**Files:**
- Modify: `rgi/core/spawn_search.py`
- Test: `tests/core/test_spawn_search.py`

**Interfaces:**
- Consumes: `CognitiveGraph`, `SpawnAction`.
- Produces: `estimate_value(graph, action) -> float`, `decide_next_action(graph, harness) -> SpawnAction | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_spawn_search.py
from rgi.core.spawn_search import estimate_value, decide_next_action


def test_stop_action_has_zero_value():
    graph = _make_graph()
    stop = SpawnAction("stop", "", [], "stop", 0, {})
    assert estimate_value(graph, stop) == 0.0


def test_decide_next_action_prefers_sweep_over_stop():
    graph = _make_graph()
    action = decide_next_action(graph, object())
    assert action is not None
    assert action.action_type == "execution_sweep"
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: FAIL — `estimate_value` and `decide_next_action` not defined.

- [ ] **Step 2: Write minimal implementation**

```python
# rgi/core/spawn_search.py

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


def decide_next_action(graph: CognitiveGraph, harness: object) -> SpawnAction | None:
    candidates = generate_candidate_actions(graph, harness)
    if not candidates:
        return None
    scored = [(estimate_value(graph, a), a) for a in candidates]
    return max(scored, key=lambda x: x[0])[1]
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add rgi/core/spawn_search.py tests/core/test_spawn_search.py
git commit -m "feat(spawn_search): add value estimator and decide_next_action"
```

---

## Task 4: Generate verify_tool and repl_explore actions

**Files:**
- Modify: `rgi/core/spawn_search.py`
- Test: `tests/core/test_spawn_search.py`

**Interfaces:**
- Consumes: `CognitiveGraph`, `Harness` (tool registry access).
- Produces: expanded `generate_candidate_actions`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/core/test_spawn_search.py


def test_generates_verify_tool_action():
    graph = _make_graph()
    tool_node = CognitiveNode(
        type=NodeType.TOOL,
        content="scan",
        parent_graph_id=graph.id,
        state=NodeState.COMPLETED,
        result={"findings": [{"kind": "sql_injection", "file": "db.py", "line": 5}]},
        metadata={"tool": "security_scan", "verification_queued": False},
    )
    graph.nodes[tool_node.id] = tool_node

    harness = SimpleNamespace(
        tool_registry=SimpleNamespace(
            get_tool=lambda name: SimpleNamespace(verifier={"objective_template": "Verify {kind}"})
        )
    )
    actions = generate_candidate_actions(graph, harness)
    verify = [a for a in actions if a.action_type == "verify_tool"]
    assert len(verify) == 1
    assert verify[0].metadata["target_findings"][0]["kind"] == "sql_injection"


def test_generates_repl_explore_action():
    graph = _make_graph()
    reason_node = CognitiveNode(
        type=NodeType.REASONING,
        content="maybe bad",
        parent_graph_id=graph.id,
        state=NodeState.COMPLETED,
        confidence=0.4,
        result={"finding": {"kind": "suspicious", "detail": "?"}},
    )
    graph.nodes[reason_node.id] = reason_node
    actions = generate_candidate_actions(graph, object())
    repl = [a for a in actions if a.action_type == "repl_explore"]
    assert len(repl) == 1
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: FAIL — verify/repl actions not generated.

- [ ] **Step 2: Update implementation**

Extend `generate_candidate_actions` to include:

```python
# inside generate_candidate_actions, after stop/execution_sweep block

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
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
git add rgi/core/spawn_search.py tests/core/test_spawn_search.py
git commit -m "feat(spawn_search): generate verify_tool and repl_explore actions"
```

---

## Task 5: Config plumbing

**Files:**
- Modify: `rgi/core/harness.py`
- Modify: `rgi/cli.py`
- Test: `tests/core/test_harness.py` and `tests/core/test_spawn_search.py`

**Interfaces:**
- Consumes: env vars `RGI_SPAWN_SEARCH`, `RGI_SPAWN_SEARCH_MAX_TIME`.
- Produces: `HarnessConfig.spawn_search_enabled: bool`, `HarnessConfig.spawn_search_max_time: float`.

- [ ] **Step 1: Inspect current `HarnessConfig`**

Run: `grep -n "class HarnessConfig" rgi/core/harness.py`

- [ ] **Step 2: Add fields**

```python
# rgi/core/harness.py
@dataclass
class HarnessConfig:
    # ... existing fields ...
    spawn_search_enabled: bool = False
    spawn_search_max_time: float = 1.0
```

- [ ] **Step 3: Parse env vars in CLI**

```python
# rgi/cli.py, around line 147
config = HarnessConfig(
    target_path=path,
    max_llm_calls=max_llm_calls,
    # ... existing args ...
    frontier_config=frontier_config,
    spawn_search_enabled=os.environ.get("RGI_SPAWN_SEARCH", "").strip().lower()
                       in ("1", "true", "yes"),
    spawn_search_max_time=float(os.environ.get("RGI_SPAWN_SEARCH_MAX_TIME", "1.0")),
)
```

- [ ] **Step 4: Add test**

```python
# tests/core/test_spawn_search.py
from rgi.core.harness import HarnessConfig


def test_harness_config_defaults():
    cfg = HarnessConfig(target_path=".", max_llm_calls=10)
    assert cfg.spawn_search_enabled is False
    assert cfg.spawn_search_max_time == 1.0


def test_harness_config_from_env(monkeypatch):
    monkeypatch.setenv("RGI_SPAWN_SEARCH", "1")
    monkeypatch.setenv("RGI_SPAWN_SEARCH_MAX_TIME", "2.5")
    # Simulate CLI parsing
    enabled = os.environ.get("RGI_SPAWN_SEARCH", "").strip().lower() in ("1", "true", "yes")
    max_time = float(os.environ.get("RGI_SPAWN_SEARCH_MAX_TIME", "1.0"))
    cfg = HarnessConfig(target_path=".", max_llm_calls=10,
                        spawn_search_enabled=enabled,
                        spawn_search_max_time=max_time)
    assert cfg.spawn_search_enabled is True
    assert cfg.spawn_search_max_time == 2.5
```

Run: `pytest tests/core/test_spawn_search.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add rgi/core/harness.py rgi/cli.py tests/core/test_spawn_search.py
git commit -m "feat(spawn_search): wire RGI_SPAWN_SEARCH env config"
```

---

## Task 6: Integrate spawn search into engine loop

**Files:**
- Modify: `rgi/core/engine.py:172-247`
- Test: `tests/core/test_engine_spawn_search.py` (new)

**Interfaces:**
- Consumes: `decide_next_action`, `SpawnAction`.
- Produces: `execute_action(graph, harness, action)` dispatcher.

- [ ] **Step 1: Import and add dispatcher**

At the top of `rgi/core/engine.py`:

```python
from rgi.core.spawn_search import decide_next_action, SpawnAction
```

Add near the spawn logic:

```python
async def _execute_spawn_action(graph: CognitiveGraph, harness: Harness,
                                action: SpawnAction) -> bool:
    """Dispatch a SpawnAction to existing engine machinery. Returns True if progress."""
    if action.action_type == "stop":
        return False

    if action.action_type == "execution_sweep":
        for fpath in action.target_files[:COVERAGE_SWEEP_MAX]:
            cid = await harness.request_subgraph_spawn(graph.id, {
                "loop_type": LoopType.EXECUTION,
                "objective": f"Coverage sweep: security analysis of {Path(fpath).name}",
                "reason": "coverage_gap",
                "target_path": fpath,
            })
            if cid:
                child = await execute_graph(harness.get_graph(cid), harness)
                merge_subgraph_results(graph, child)
        return True

    if action.action_type == "verify_tool":
        graph.memory_snapshot.setdefault("spawn_suggestions", []).append({
            "loop_type": LoopType.VERIFICATION,
            "objective": action.objective,
            "reason": "tool_verification",
            "target_findings": action.metadata.get("target_findings", []),
            "target_path": harness.config.target_path,
        })
        # Mark tool node as queued
        node_id = action.metadata.get("tool_node")
        if node_id and node_id in graph.nodes:
            graph.nodes[node_id].metadata["verification_queued"] = True
        return True

    if action.action_type == "repl_explore":
        for n in action.metadata.get("target_nodes", []):
            n.metadata["force_fire"] = True
        return True

    if action.action_type == "frontier_arbitrate":
        # Handled separately by existing needs_frontier_arbitration path.
        return False

    return False
```

- [ ] **Step 2: Replace spawn decision block**

Replace lines 176-207:

```python
        if graph.policy.auto_spawn and should_spawn_subgraphs(graph, harness):
            if spawn_rounds >= MAX_SPAWN_ROUNDS:
                # ... existing inhibition ...
            else:
                # ... existing proposal/spawn/merge ...
```

with:

```python
        if graph.policy.auto_spawn and should_spawn_subgraphs(graph, harness):
            if spawn_rounds >= MAX_SPAWN_ROUNDS:
                dropped = graph.memory_snapshot.pop("spawn_suggestions", [])
                for n in graph.nodes.values():
                    if n.type == NodeType.REASONING:
                        n.metadata["spawn_consumed"] = True
                harness.audit.record("spawn_inhibited", graph_id=graph.id,
                                     reason="max_spawn_rounds", dropped=len(dropped))
            elif harness.config.spawn_search_enabled:
                try:
                    action = decide_next_action(graph, harness)
                except Exception as exc:
                    harness.audit.record("spawn_search_fallback", graph_id=graph.id,
                                         error=f"{type(exc).__name__}: {exc}")
                    action = None
                if action is not None and action.action_type != "stop":
                    harness.audit.record("spawn_search_decision", graph_id=graph.id,
                                         action_type=action.action_type,
                                         objective=action.objective,
                                         reason=action.reason)
                    progressed = await _execute_spawn_action(graph, harness, action)
                    if progressed:
                        spawn_rounds += 1

            # Heuristic fallback: if spawn search disabled, returned stop/None,
            # or no progress was made, use the original proposal generator.
            if (graph.policy.auto_spawn
                    and should_spawn_subgraphs(graph, harness)
                    and spawn_rounds < MAX_SPAWN_ROUNDS):
                proposals = generate_spawn_proposals(graph, harness)
                child_ids = []
                for proposal in proposals:
                    child_id = await harness.request_subgraph_spawn(graph.id, proposal)
                    if child_id:
                        child_ids.append(child_id)
                children = [harness.get_graph(cid) for cid in child_ids]
                if children:
                    spawn_rounds += 1
                    results = await asyncio.gather(*(_run_child(c) for c in children))
                    for child in results:
                        merge_subgraph_results(graph, child)
                    progressed = True
```

The original heuristic logic is preserved and runs whenever spawn search does not produce a non-stop action.

- [ ] **Step 3: Write integration test**

```python
# tests/core/test_engine_spawn_search.py
import pytest
from rgi.cli import run_analysis


@pytest.mark.asyncio
async def test_spawn_search_mock_run_completes():
    report = await run_analysis(
        "sample_project", "find security vulnerabilities",
        "/tmp/rgi_spawn_search_mock.json", mock=True,
        provider="ollama", model="qwen2.5:1.5b", max_llm_calls=20,
    )
    assert report["status"] == "completed"
```

Wait — this won't enable spawn_search. We need a way to enable it in tests. Add a helper or set env var in the test.

```python
import os
os.environ["RGI_SPAWN_SEARCH"] = "1"
```

Run: `pytest tests/core/test_engine_spawn_search.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add rgi/core/engine.py tests/core/test_engine_spawn_search.py
git commit -m "feat(engine): integrate adaptive spawn search decision layer"
```

---

## Task 7: Full test suite and benchmark A/B

**Files:**
- None (verification only).

- [ ] **Step 1: Run unit tests**

```bash
pytest tests/core/test_spawn_search.py tests/core/test_engine_spawn_search.py -v
```
Expected: all pass.

- [ ] **Step 2: Run full suite with feature disabled**

```bash
unset RGI_SPAWN_SEARCH
pytest tests -q
```
Expected: 185+ passed, no regressions.

- [ ] **Step 3: Run full suite with feature enabled**

```bash
export RGI_SPAWN_SEARCH=1
pytest tests -q
```
Expected: all pass.

- [ ] **Step 4: Benchmark A/B**

Baseline:
```bash
unset RGI_SPAWN_SEARCH
python -m rgi eval --objective "find security vulnerabilities" --runs 1 \
  --provider ollama --model qwen2.5:1.5b --max-llm-calls 20 \
  --target vuln_app_2 --output /tmp/rgi_baseline_vuln2.json
```

Spawn search:
```bash
export RGI_SPAWN_SEARCH=1
python -m rgi eval --objective "find security vulnerabilities" --runs 1 \
  --provider ollama --model qwen2.5:1.5b --max-llm-calls 20 \
  --target vuln_app_2 --output /tmp/rgi_spawn_search_vuln2.json
```

Expected: spawn search recall ≥ baseline; LLM calls ≤ baseline or recall/call ratio improves.

- [ ] **Step 5: Commit**

```bash
git commit -m "test(spawn_search): A/B benchmark and full regression suite"
```

---

## Spec Coverage Check

| spec requirement | task |
|---|---|
| `SpawnAction` dataclass | Task 1 |
| `SpawnNode` dataclass | Task 1 |
| Candidate action generation | Tasks 2, 4 |
| Value estimator | Task 3 |
| `decide_next_action` | Task 3 |
| Engine integration | Task 6 |
| Config env vars | Task 5 |
| Telemetry/audit | Task 6 |
| Fallback to heuristic | Task 6 |
| Tests | Tasks 1-7 |
| Benchmark A/B | Task 7 |

## Placeholder Scan

No TBD, TODO, "implement later," or vague requirements. Every step includes exact file paths, code, commands, and expected output.
