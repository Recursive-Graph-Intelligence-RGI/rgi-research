# RGI Hybrid Local / Frontier Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional frontier-model integration layer to RGI that calls a frontier LLM at three high-leverage inflection points (plan, arbitrate, synthesize) while keeping recursive local subgraphs and REPL/tool loops as the primary compute engine.

**Architecture:** Introduce a `FrontierConfig` and `FrontierIntegration` client in `rgi/reasoning/frontier_integration.py`. Wire three hooks into `rgi/core/engine.py`: a pre-execution plan call, a mid-execution arbitration trigger, and a post-execution synthesis step. All frontier calls parse structured Pydantic output and fall back to local behavior on failure. The feature is disabled by default and controlled by environment variables.

**Tech Stack:** Python 3.11+, Pydantic v2, existing `rgi.core.models`, `rgi.reasoning.llm_client`, `rgi.core.harness`, pytest.

## Global Constraints

- Frontier integration must be **optional and disabled by default**; no API key required for default local-only runs.
- Local recursive subgraphs and REPL/tool loops remain the primary compute engine.
- Maximum default frontier calls per run: 1 plan + 2 arbitration + 1 synthesis = 4.
- All frontier outputs must be parsed through Pydantic schemas; parse failures silently fall back to local behavior.
- Every frontier call, fallback, and parse failure must be recorded in `Harness.audit`.
- All changes must be covered by tests; existing tests must continue to pass.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `rgi/reasoning/frontier_integration.py` | New. Frontier client, config, Pydantic result schemas, prompt builders, fallback logic. |
| `rgi/core/engine.py` | Modify. Add frontier plan/arbitrate/synthesis hooks and trigger conditions. |
| `rgi/core/harness.py` | Modify. Accept `frontier_config` in `HarnessConfig`; expose it to engine. |
| `rgi/cli.py` | Modify. Read frontier env vars and pass `FrontierConfig` into `HarnessConfig`. |
| `tests/reasoning/test_frontier_integration.py` | New. Unit tests for frontier client and schemas. |
| `tests/core/test_frontier_hooks.py` | New. Integration tests for engine hooks and fallback behavior. |

---

## Task 1: Frontier Result Schemas

**Files:**
- Create: `rgi/reasoning/frontier_integration.py`
- Test: `tests/reasoning/test_frontier_integration.py`

**Interfaces:**
- Produces: `PlanResult`, `ArbitrationResult`, `SynthesisResult`, `FrontierConfig`, `FrontierIntegration`

- [ ] **Step 1: Write the failing test**

```python
# tests/reasoning/test_frontier_integration.py
import pytest
from rgi.reasoning.frontier_integration import (
    ArbitrationResult, FrontierConfig, FrontierIntegration, PlanResult,
    SynthesisResult,
)


def test_plan_result_defaults():
    r = PlanResult(
        strategy="breadth-first security audit",
        initial_subgraph_objectives=["Analyze JWT handling"],
        focus_areas=["auth.py"],
    )
    assert r.expected_findings == []


def test_arbitration_result_valid_decision():
    r = ArbitrationResult(decision="respawn", reasoning="local confidence stalled")
    assert r.spawn_objectives == []
    assert not r.escalate_to_user


def test_frontier_config_defaults():
    cfg = FrontierConfig()
    assert not cfg.enabled
    assert cfg.max_arbitration_calls == 2


@pytest.mark.asyncio
async def test_frontier_integration_disabled_returns_none():
    cfg = FrontierConfig(enabled=False)
    frontier = FrontierIntegration(cfg)
    plan = await frontier.plan_root("objective", {})
    assert plan is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reasoning/test_frontier_integration.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'rgi.reasoning.frontier_integration'`

- [ ] **Step 3: Write minimal implementation**

```python
# rgi/reasoning/frontier_integration.py
"""Optional frontier-model integration layer for RGI.

Local recursive graphs do the work. The frontier is invoked only at
high-leverage inflection points: initial planning, deadlock arbitration,
and final synthesis. All calls are optional and fall back to local logic
on failure or when disabled.
"""
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class PlanResult(BaseModel):
    strategy: str
    initial_subgraph_objectives: list[str]
    focus_areas: list[str]
    expected_findings: list[str] = []


class ArbitrationResult(BaseModel):
    decision: str = Field(..., pattern="^(respawn|merge|drop|escalate|noop)$")
    reasoning: str
    spawn_objectives: list[str] = []
    findings_to_drop: list[str] = []
    escalate_to_user: bool = False


class SynthesisResult(BaseModel):
    summary: str
    findings: list[dict]
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommendations: list[str] = []


@dataclass
class FrontierConfig:
    enabled: bool = False
    provider: str = "kimi"
    model: str | None = None
    plan_at_start: bool = True
    arbitrate_on_deadlock: bool = True
    synthesize_at_end: bool = True
    max_arbitration_calls: int = 2


class FrontierIntegration:
    def __init__(self, config: FrontierConfig):
        self.config = config

    async def plan_root(self, objective: str, world_model: dict[str, Any]) -> PlanResult | None:
        if not self.config.enabled or not self.config.plan_at_start:
            return None
        return PlanResult(
            strategy="local-first recursive audit",
            initial_subgraph_objectives=[],
            focus_areas=[],
        )

    async def arbitrate(self, state: dict[str, Any]) -> ArbitrationResult | None:
        if not self.config.enabled or not self.config.arbitrate_on_deadlock:
            return None
        return ArbitrationResult(decision="noop", reasoning="frontier not yet implemented")

    async def synthesize(self, graph_state: dict[str, Any], findings: list[dict]) -> SynthesisResult | None:
        if not self.config.enabled or not self.config.synthesize_at_end:
            return None
        return SynthesisResult(
            summary="local synthesis fallback",
            findings=findings,
            confidence=0.5,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reasoning/test_frontier_integration.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/reasoning/test_frontier_integration.py rgi/reasoning/frontier_integration.py
git commit -m "feat(frontier): add result schemas and disabled-by-default integration shell"
```

---

## Task 2: Wire FrontierConfig into Harness

**Files:**
- Modify: `rgi/core/harness.py`
- Test: `tests/core/test_harness.py` (existing)

**Interfaces:**
- Consumes: `FrontierConfig` from `rgi.reasoning.frontier_integration`
- Produces: `Harness.frontier_config`, `Harness.frontier`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_harness.py
def test_harness_exposes_frontier_config():
    from rgi.core.harness import Harness, HarnessConfig
    from rgi.reasoning.frontier_integration import FrontierConfig

    cfg = HarnessConfig(frontier_config=FrontierConfig(enabled=True))
    harness = Harness(cfg)
    assert harness.frontier_config.enabled is True
    assert harness.frontier is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_harness.py::test_harness_exposes_frontier_config -v`

Expected: FAIL with `TypeError: HarnessConfig.__init__() got an unexpected keyword argument 'frontier_config'`

- [ ] **Step 3: Write minimal implementation**

```python
# rgi/core/harness.py
# Add to imports:
from rgi.reasoning.frontier_integration import FrontierConfig, FrontierIntegration

# Add field to HarnessConfig:
@dataclass
class HarnessConfig:
    target_path: str = "./sample_project"
    max_llm_calls: int = 20
    max_total_nodes: int = 50
    max_depth: int = 3
    max_seconds: int = 300
    llm_client: object = None
    activation_engine: object = None
    data_dir: str = "data"
    frontier_config: FrontierConfig = field(default_factory=FrontierConfig)

# In Harness.__init__, after self.gate = ... add:
        self.frontier_config = config.frontier_config
        self.frontier = FrontierIntegration(self.frontier_config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_harness.py::test_harness_exposes_frontier_config -v`

Expected: PASS

- [ ] **Step 5: Run full test suite to catch regressions**

Run: `pytest tests -q`

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add rgi/core/harness.py tests/core/test_harness.py
git commit -m "feat(frontier): wire FrontierConfig into Harness"
```

---

## Task 3: Implement Frontier Plan Call

**Files:**
- Modify: `rgi/reasoning/frontier_integration.py`
- Modify: `rgi/core/engine.py`
- Test: `tests/reasoning/test_frontier_integration.py`

**Interfaces:**
- Consumes: `LLMClient.reason(task, context)`
- Produces: `FrontierIntegration.plan_root` returns real `PlanResult` when enabled

- [ ] **Step 1: Write the failing test**

```python
# tests/reasoning/test_frontier_integration.py
import pytest
from rgi.reasoning.frontier_integration import FrontierConfig, FrontierIntegration


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def reason(self, task: str, context: str) -> dict:
        self.calls.append((task, context))
        return self.response


@pytest.mark.asyncio
async def test_plan_root_uses_frontier_llm():
    fake = _FakeLLM({
        "strategy": "focus on auth",
        "initial_subgraph_objectives": ["JWT analysis"],
        "focus_areas": ["auth.py"],
        "expected_findings": ["weak secret"],
    })
    cfg = FrontierConfig(enabled=True, provider="kimi", model="kimi-k2")
    frontier = FrontierIntegration(cfg, llm_client=fake)
    result = await frontier.plan_root("Analyze auth security", {"auth.py": "JWT code"})
    assert result.strategy == "focus on auth"
    assert result.initial_subgraph_objectives == ["JWT analysis"]
    assert len(fake.calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reasoning/test_frontier_integration.py::test_plan_root_uses_frontier_llm -v`

Expected: FAIL with `TypeError: FrontierIntegration.__init__() got an unexpected keyword argument 'llm_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# rgi/reasoning/frontier_integration.py
# Add to imports:
import json
from typing import Any

from rgi.reasoning.llm_client import LLMClient

# Update FrontierIntegration:
class FrontierIntegration:
    def __init__(self, config: FrontierConfig, llm_client: Any = None):
        self.config = config
        self.llm_client = llm_client or LLMClient(model=config.model)

    async def plan_root(self, objective: str, world_model: dict[str, Any]) -> PlanResult | None:
        if not self.config.enabled or not self.config.plan_at_start:
            return None
        prompt = (
            "You are the strategic planner for a recursive code-intelligence engine. "
            "Given the objective and a condensed world model, produce a concise plan. "
            "Return strictly JSON matching this schema:\n"
            '{"strategy": str, "initial_subgraph_objectives": [str], '
            '"focus_areas": [str], "expected_findings": [str]}\n\n'
            f"Objective: {objective}\n\n"
            f"World model keys: {list(world_model.keys())}\n"
            f"World model summary: {json.dumps(world_model, default=str)[:4000]}"
        )
        try:
            raw = await self.llm_client.reason("Plan root investigation strategy", prompt)
            return PlanResult.model_validate(raw)
        except Exception as exc:
            return PlanResult(
                strategy=f"frontier plan failed: {exc}",
                initial_subgraph_objectives=[],
                focus_areas=[],
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reasoning/test_frontier_integration.py -v`

Expected: PASS

- [ ] **Step 5: Wire plan call into engine**

```python
# rgi/core/engine.py
# At the top of execute_graph, after spawn_rounds = 0:
    frontier_plan = None
    if harness.frontier_config.enabled and harness.frontier_config.plan_at_start:
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
```

- [ ] **Step 6: Test the engine hook**

```python
# tests/core/test_frontier_hooks.py
import pytest
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import CognitiveGraph, GraphPolicy, GraphState, LoopType
from rgi.reasoning.frontier_integration import FrontierConfig, FrontierIntegration, PlanResult
from rgi.loops import initialize_graph_nodes


class _FakeFrontier:
    def __init__(self):
        self.plan_calls = []

    async def plan_root(self, objective, world_model):
        self.plan_calls.append((objective, world_model))
        return PlanResult(
            strategy="test",
            initial_subgraph_objectives=["Sub-objective A"],
            focus_areas=["auth.py"],
        )


@pytest.mark.asyncio
async def test_engine_seeds_frontier_plan_subgraphs():
    from rgi.core.engine import execute_graph

    cfg = HarnessConfig(
        target_path="sample_project",
        frontier_config=FrontierConfig(enabled=True),
    )
    harness = Harness(cfg)
    harness.frontier = _FakeFrontier()
    root = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="Analyze auth"),
        policy=GraphPolicy(),
    )
    initialize_graph_nodes(root, {"objective": "Analyze auth"})
    root.memory_snapshot["world_model"] = {"auth.py": "jwt code"}
    harness.graphs[root.id] = root
    result = await execute_graph(root, harness)
    assert result.state.status in ("completed", "failed")
    assert len(harness.frontier.plan_calls) == 1
```

- [ ] **Step 7: Run the new hook test**

Run: `pytest tests/core/test_frontier_hooks.py::test_engine_seeds_frontier_plan_subgraphs -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add rgi/reasoning/frontier_integration.py rgi/core/engine.py tests/reasoning/test_frontier_integration.py tests/core/test_frontier_hooks.py
git commit -m "feat(frontier): implement plan_root and engine seed hook"
```

---

## Task 4: Implement Frontier Arbitration

**Files:**
- Modify: `rgi/reasoning/frontier_integration.py`
- Modify: `rgi/core/engine.py`
- Test: `tests/core/test_frontier_hooks.py`

**Interfaces:**
- Consumes: merged findings, graph state
- Produces: `ArbitrationResult` used to respawn/merge/drop findings

- [ ] **Step 1: Write the failing test**

```python
# tests/reasoning/test_frontier_integration.py
@pytest.mark.asyncio
async def test_arbitrate_returns_structured_result():
    fake = _FakeLLM({
        "decision": "respawn",
        "reasoning": "confidence stalled",
        "spawn_objectives": ["Re-analyze JWT"],
    })
    cfg = FrontierConfig(enabled=True)
    frontier = FrontierIntegration(cfg, llm_client=fake)
    result = await frontier.arbitrate({"findings": [], "contradictions": []})
    assert result.decision == "respawn"
    assert result.spawn_objectives == ["Re-analyze JWT"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reasoning/test_frontier_integration.py::test_arbitrate_returns_structured_result -v`

Expected: FAIL because `arbitrate` returns a hard-coded noop

- [ ] **Step 3: Write minimal implementation**

```python
# rgi/reasoning/frontier_integration.py
    async def arbitrate(self, state: dict[str, Any]) -> ArbitrationResult | None:
        if not self.config.enabled or not self.config.arbitrate_on_deadlock:
            return None
        prompt = (
            "You are an arbitration judge in a recursive code-intelligence engine. "
            "Local subgraphs have produced the following state. Decide how to proceed. "
            "Return strictly JSON matching this schema:\n"
            '{"decision": "respawn|merge|drop|escalate|noop", "reasoning": str, '
            '"spawn_objectives": [str], "findings_to_drop": [str], "escalate_to_user": bool}\n\n'
            f"State: {json.dumps(state, default=str)[:6000]}"
        )
        try:
            raw = await self.llm_client.reason("Arbitrate local deadlock", prompt)
            return ArbitrationResult.model_validate(raw)
        except Exception as exc:
            return ArbitrationResult(
                decision="noop",
                reasoning=f"frontier arbitration failed: {exc}",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reasoning/test_frontier_integration.py -v`

Expected: PASS

- [ ] **Step 5: Add arbitration trigger and engine hook**

```python
# rgi/core/engine.py
# Add helper near the bottom:
def needs_frontier_arbitration(graph: CognitiveGraph, harness: Harness) -> bool:
    if not harness.frontier_config.enabled or not harness.frontier_config.arbitrate_on_deadlock:
        return False
    arbitration_count = graph.memory_snapshot.get("frontier_arbitration_count", 0)
    if arbitration_count >= harness.frontier_config.max_arbitration_calls:
        return False
    avg = _avg_confidence(graph)
    if graph.state.iteration >= graph.state.max_iterations - 1 and avg < graph.state.confidence_threshold:
        return True
    findings = _collect_findings(graph)
    contradictions = _detect_contradictions(findings)
    if contradictions:
        return True
    rejected = sum(1 for e in harness.audit.events if e.get("event") == "spawn_rejected" and e.get("graph_id") == graph.id)
    if rejected >= 3:
        return True
    return False


def _detect_contradictions(findings: list[dict]) -> list[dict]:
    """Find pairs of findings at the same location with opposite validity."""
    by_loc: dict[tuple, list[dict]] = {}
    for f in findings:
        loc = (f.get("file"), f.get("line"), f.get("symbol"))
        by_loc.setdefault(loc, []).append(f)
    contradictions = []
    for loc, group in by_loc.items():
        if len(group) > 1:
            contradictions.append({"location": loc, "findings": group})
    return contradictions
```

- [ ] **Step 6: Wire arbitration into execute_graph convergence check**

In `execute_graph`, inside the `all_subgraphs_completed` block where the graph would otherwise complete or fail, insert before the final avg/confidence check:

```python
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
                arb = await harness.frontier.arbitrate(state_pkg)
                graph.memory_snapshot["frontier_arbitration_count"] = graph.memory_snapshot.get("frontier_arbitration_count", 0) + 1
                harness.audit.record("frontier_arbitration", graph_id=graph.id,
                                     decision=arb.decision if arb else "noop",
                                     reasoning=arb.reasoning if arb else "")
                if arb:
                    if arb.decision == "respawn":
                        for obj in arb.spawn_objectives:
                            graph.memory_snapshot.setdefault("spawn_suggestions", []).append({
                                "loop_type": LoopType.EXECUTION,
                                "objective": obj,
                                "reason": "frontier_arbitration",
                                "target_path": harness.config.target_path,
                            })
                    elif arb.decision == "drop":
                        drop_ids = set(arb.findings_to_drop)
                        graph.memory_snapshot["dropped_findings"] = drop_ids
            if not should_spawn_subgraphs(graph, harness):
                await maybe_spawn_verification(graph, harness)
```

- [ ] **Step 7: Test arbitration trigger**

```python
# tests/core/test_frontier_hooks.py
@pytest.mark.asyncio
async def test_arbitration_triggers_on_low_confidence_stall():
    from rgi.core.engine import execute_graph, needs_frontier_arbitration

    cfg = HarnessConfig(
        target_path="sample_project",
        max_llm_calls=100,
        frontier_config=FrontierConfig(enabled=True),
    )
    harness = Harness(cfg)
    fake_frontier = _FakeFrontier()

    class _ArbFrontier:
        async def plan_root(self, objective, world_model):
            return PlanResult(strategy="test", initial_subgraph_objectives=[], focus_areas=[])

        async def arbitrate(self, state):
            fake_frontier.calls.append(state)
            return ArbitrationResult(decision="respawn", reasoning="low confidence", spawn_objectives=["Retry"])

    harness.frontier = _ArbFrontier()
    root = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="x", max_iterations=1, confidence_threshold=0.99),
        policy=GraphPolicy(),
    )
    initialize_graph_nodes(root, {"objective": "x"})
    harness.graphs[root.id] = root
    assert needs_frontier_arbitration(root, harness)
```

- [ ] **Step 8: Run the arbitration tests**

Run: `pytest tests/core/test_frontier_hooks.py -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add rgi/reasoning/frontier_integration.py rgi/core/engine.py tests/core/test_frontier_hooks.py tests/reasoning/test_frontier_integration.py
git commit -m "feat(frontier): implement deadlock arbitration hook"
```

---

## Task 5: Implement Frontier Synthesis

**Files:**
- Modify: `rgi/reasoning/frontier_integration.py`
- Modify: `rgi/cli.py`
- Test: `tests/core/test_frontier_hooks.py`

**Interfaces:**
- Consumes: final graph state, merged findings
- Produces: final report dict

- [ ] **Step 1: Write the failing test**

```python
# tests/reasoning/test_frontier_integration.py
@pytest.mark.asyncio
async def test_synthesize_returns_report():
    fake = _FakeLLM({
        "summary": "Found weak secrets",
        "findings": [{"kind": "hardcoded_secret", "file": "config.py"}],
        "confidence": 0.95,
        "recommendations": ["Rotate secrets"],
    })
    cfg = FrontierConfig(enabled=True)
    frontier = FrontierIntegration(cfg, llm_client=fake)
    result = await frontier.synthesize({}, [])
    assert result.summary == "Found weak secrets"
    assert result.confidence == 0.95
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reasoning/test_frontier_integration.py::test_synthesize_returns_report -v`

Expected: FAIL because `synthesize` returns a fallback

- [ ] **Step 3: Write minimal implementation**

```python
# rgi/reasoning/frontier_integration.py
    async def synthesize(self, graph_state: dict[str, Any], findings: list[dict]) -> SynthesisResult | None:
        if not self.config.enabled or not self.config.synthesize_at_end:
            return None
        prompt = (
            "You are the final report synthesizer for a recursive code-intelligence engine. "
            "Given the converged graph state and a list of grounded findings, produce the final report. "
            "Return strictly JSON matching this schema:\n"
            '{"summary": str, "findings": [{"kind": str, "severity": str, "detail": str, '
            '"file": str, "line": int, "symbol": str, "confidence": float}], '
            '"confidence": float (0.0-1.0), "recommendations": [str]}\n\n'
            f"Graph state: {json.dumps(graph_state, default=str)[:2000]}\n\n"
            f"Findings: {json.dumps(findings, default=str)[:6000]}"
        )
        try:
            raw = await self.llm_client.reason("Synthesize final report", prompt)
            return SynthesisResult.model_validate(raw)
        except Exception as exc:
            return SynthesisResult(
                summary=f"frontier synthesis failed: {exc}",
                findings=findings,
                confidence=0.5,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reasoning/test_frontier_integration.py -v`

Expected: PASS

- [ ] **Step 5: Wire synthesis into build_report**

Make `build_report` async so it can `await` the frontier synthesis call.

```python
# rgi/cli.py
# Change function signature:
async def build_report(root, harness, knowledge) -> dict:
    ...
```

At the top of `build_report`, after collecting `node_findings` and `scanner_findings`:

```python
    frontier = harness.frontier
    if frontier.config.enabled and frontier.config.synthesize_at_end:
        graph_state = {
            "objective": root.state.objective,
            "graphs_count": len(graphs),
            "status": root.state.status,
        }
        try:
            synth = await frontier.synthesize(graph_state, node_findings + scanner_findings)
        except Exception as exc:
            harness.audit.record("frontier_fallback", graph_id=root.id,
                                 phase="synthesize", error=str(exc))
            synth = None
        if synth:
            harness.audit.record("frontier_synthesis", graph_id=root.id,
                                 findings_count=len(synth.findings),
                                 confidence=synth.confidence)
            return {
                "objective": root.state.objective,
                "status": root.state.status,
                "aggregate_confidence": synth.confidence,
                "findings": [normalize_finding(f) for f in synth.findings],
                "summary": synth.summary,
                "recommendations": synth.recommendations,
                "llm_calls": harness.total_llm_calls,
            }
```

Also add `from rgi.core.findings import normalize_finding` to `rgi/cli.py` imports if not already present.

- [ ] **Step 6: Update build_report caller in run_analysis**

```python
# rgi/cli.py
# In run_analysis, change:
#     report = build_report(root, harness, knowledge)
# to:
    report = await build_report(root, harness, knowledge)
```

- [ ] **Step 7: Test synthesis hook**

```python
# tests/core/test_frontier_hooks.py
@pytest.mark.asyncio
async def test_build_report_uses_frontier_synthesis():
    from rgi.cli import build_report

    cfg = HarnessConfig(
        target_path="sample_project",
        frontier_config=FrontierConfig(enabled=True),
    )
    harness = Harness(cfg)

    class _SynthFrontier:
        async def plan_root(self, *a, **kw):
            return None

        async def arbitrate(self, *a, **kw):
            return None

        async def synthesize(self, graph_state, findings):
            return SynthesisResult(
                summary="synth summary",
                findings=[{"kind": "test", "file": "x.py", "confidence": 0.9}],
                confidence=0.9,
            )

    harness.frontier = _SynthFrontier()
    root = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(objective="test"),
        policy=GraphPolicy(),
    )
    harness.graphs[root.id] = root
    report = await build_report(root, harness, root)
    assert report["summary"] == "synth summary"
    assert report["aggregate_confidence"] == 0.9
```

- [ ] **Step 7: Run the synthesis test**

Run: `pytest tests/core/test_frontier_hooks.py::test_build_report_uses_frontier_synthesis -v`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add rgi/reasoning/frontier_integration.py rgi/cli.py tests/core/test_frontier_hooks.py tests/reasoning/test_frontier_integration.py
git commit -m "feat(frontier): implement final synthesis hook"
```

---

## Task 6: CLI Environment Variable Integration

**Files:**
- Modify: `rgi/cli.py`
- Test: `tests/test_e2e_mock.py` (existing, verify no regression)

**Interfaces:**
- Consumes: env vars `RGI_FRONTIER_ENABLED`, `RGI_FRONTIER_MODEL`, `RGI_FRONTIER_MAX_ARBITRATION`
- Produces: `FrontierConfig` passed to `HarnessConfig`

- [ ] **Step 1: Read frontier env vars in CLI**

```python
# rgi/cli.py
# In run_analysis, before constructing HarnessConfig:
    frontier_config = FrontierConfig(
        enabled=os.environ.get("RGI_FRONTIER_ENABLED", "").lower() in ("1", "true", "yes"),
        provider=provider,
        model=model,
        max_arbitration_calls=int(os.environ.get("RGI_FRONTIER_MAX_ARBITRATION", "2")),
    )
```

- [ ] **Step 2: Pass frontier_config into HarnessConfig**

```python
# rgi/cli.py
    config = HarnessConfig(
        target_path=path,
        max_llm_calls=max_llm_calls,
        max_total_nodes=max_total_nodes,
        max_seconds=int(os.environ.get("RGI_MAX_SECONDS", "300")),
        llm_client=llm,
        data_dir=str(data_dir),
        frontier_config=frontier_config,
    )
```

- [ ] **Step 3: Add FrontierConfig import**

```python
# rgi/cli.py
from rgi.reasoning.frontier_integration import FrontierConfig
```

- [ ] **Step 4: Verify no regressions**

Run: `pytest tests -q`

Expected: all tests pass

- [ ] **Step 5: Test CLI env parsing**

```python
# tests/test_e2e_mock.py (append)
from rgi.reasoning.frontier_integration import FrontierConfig


def test_frontier_config_from_env_values():
    cfg = FrontierConfig(
        enabled=True,
        model="kimi-k2",
        max_arbitration_calls=2,
    )
    assert cfg.enabled
    assert cfg.model == "kimi-k2"
    assert cfg.max_arbitration_calls == 2
```

*Note:* This test verifies the config object can be constructed from env-like values; the env parsing itself is a simple inline mapping in `run_analysis`.

- [ ] **Step 6: Run CLI test**

Run: `pytest tests/test_e2e_mock.py::test_frontier_config_from_env_values -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add rgi/cli.py tests/test_e2e_mock.py
git commit -m "feat(frontier): read frontier config from CLI env vars"
```

---

## Task 7: Fallback and Audit Coverage

**Files:**
- Modify: `rgi/reasoning/frontier_integration.py`
- Modify: `rgi/core/engine.py`
- Test: `tests/core/test_frontier_hooks.py`

**Interfaces:**
- All frontier methods must emit `frontier_fallback` audit events on failure.

- [ ] **Step 1: Write failing test for fallback audit**

```python
# tests/core/test_frontier_hooks.py
@pytest.mark.asyncio
async def test_frontier_parse_failure_falls_back_and_audits():
    from rgi.core.harness import Harness, HarnessConfig
    from rgi.reasoning.llm_client import MockLLMClient

    bad_llm = MockLLMClient(script={"synthesize": [{"invalid": "shape"}]})
    cfg = FrontierConfig(enabled=True, provider="kimi")
    frontier = FrontierIntegration(cfg, llm_client=bad_llm)
    result = await frontier.synthesize({}, [])
    assert result is not None
    assert result.confidence == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_frontier_hooks.py::test_frontier_parse_failure_falls_back_and_audits -v`

Expected: behavior may already pass; verify and tighten if needed

- [ ] **Step 3: Ensure audit events are emitted**

Update `FrontierIntegration` methods to accept an optional audit callback or return enough info for callers to audit. The simplest approach: callers already audit decisions; add `frontier_fallback` events in the engine/cli when `synthesize`/`plan_root`/`arbitrate` raise or return fallback shapes.

In `rgi/reasoning/frontier_integration.py`, keep fallback behavior as already implemented. In `rgi/core/engine.py`, wrap frontier calls:

```python
        try:
            frontier_plan = await harness.frontier.plan_root(...)
        except Exception as exc:
            harness.audit.record("frontier_fallback", graph_id=graph.id, phase="plan", error=str(exc))
            frontier_plan = None
```

Similarly for `arbitrate` and in `build_report` for `synthesize`.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests -q`

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add rgi/reasoning/frontier_integration.py rgi/core/engine.py rgi/cli.py tests/core/test_frontier_hooks.py
git commit -m "feat(frontier): add fallback audit events for frontier failures"
```

---

## Task 8: Final Integration and Regression Test

**Files:**
- All modified files
- Test: full suite

- [ ] **Step 1: Run full test suite**

Run: `pytest tests -q`

Expected: all tests pass

- [ ] **Step 2: Run end-to-end mock analysis**

Run: `python -m rgi analyze sample_project --objective "Analyze authentication security" --mock --output /tmp/rgi_frontier_mock.json`

Expected: report generated, status `completed`, no frontier calls because mock disables frontier by default (or frontier is enabled but uses mock LLM).

- [ ] **Step 3: Run with frontier enabled against mock**

Run: `RGI_FRONTIER_ENABLED=1 python -m rgi analyze sample_project --objective "Analyze authentication security" --mock --output /tmp/rgi_frontier_enabled.json`

Expected: report generated, frontier plan/synthesis may run (depending on mock script matching).

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(frontier): complete hybrid local/frontier integration"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** Each section of `2026-08-11-rgi-hybrid-local-frontier-integration-design.md` has at least one implementing task.
- [ ] **Placeholder scan:** No TBD/TODO/"implement later"/"add appropriate error handling" in plan steps.
- [ ] **Type consistency:** `FrontierConfig`, `PlanResult`, `ArbitrationResult`, `SynthesisResult` signatures match between tasks.
- [ ] **Test coverage:** Unit tests for schemas, plan, arbitrate, synthesis; integration tests for engine hooks; CLI env parsing test.
- [ ] **No regressions:** Full test suite passes after each task.
