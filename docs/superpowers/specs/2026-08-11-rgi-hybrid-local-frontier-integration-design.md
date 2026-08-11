# RGI Hybrid Local / Frontier Integration Design

**Date:** 2026-08-11  
**Status:** Design  
**Scope:** Add an optional frontier-model integration layer to RGI that calls a frontier LLM only at high-leverage inflection points, while keeping recursive local subgraphs and REPL/tool loops as the primary compute engine.

---

## 1. Problem Statement

RGI's recursive graph engine can already plan, spawn, verify, and correct using small local models. The architecture is sound, but two gaps remain:

1. **Strategic planning:** A 4B/7B local model can miss the big picture at the start of a complex investigation, spawning subgraphs down low-value paths.
2. **Final synthesis:** Local models can produce noisy or contradictory findings; a frontier model is better at integrating diverse evidence into a coherent, ranked report.

The naive fix — run the whole pipeline on a frontier model — destroys the cost advantage of local recursion. The right fix is a **hybrid**: local models do the breadth work, frontier models do the high-leverage integration.

---

## 2. Design Principle

> **Local graphs organize the computation; frontier models make the expensive decisions cheap because the data is already structured.**

The recursive graph is the compression format. Every subgraph returns a typed, confidence-scored, grounded result. The frontier never reads raw source files unless the local engine explicitly flags a contradiction it cannot resolve.

---

## 3. Architecture

### 3.1 Topology

```
Objective + World Model
          │
          ▼
   ┌─────────────────────┐
   │  Frontier Plan Call │  (inflection point 1)
   └─────────────────────┘
          │
          ▼
   Root Planning Graph
          │
          ├──────────────────────────────────────┐
          │                                      │
          ▼                                      ▼
   Execution Subgraphs                Verification Subgraphs
   (local LLM + tools + REPL)         (local LLM + tools)
          │                                      │
          └──────────────────┬───────────────────┘
                             │
                             ▼
                  Merged Findings Graph
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   confidence OK?    contradiction?     budget exhausted?
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                             ▼
              ┌─────────────────────────┐
              │ Frontier Arbitration    │  (inflection point 2, optional)
              │ (only if triggered)     │
              └─────────────────────────┘
                             │
                             ▼
              ┌─────────────────────────┐
              │ Frontier Synthesis Call │  (inflection point 3)
              └─────────────────────────┘
                             │
                             ▼
                        report.json
```

### 3.2 Inflection Points

| # | Point | Input | Output | Trigger |
|---|-------|-------|--------|---------|
| 1 | **Plan** | objective, world model, target metadata | root strategy, initial subgraph objectives | always at run start if frontier enabled |
| 2 | **Arbitrate** | merged findings, contradictions, stalled confidence | resolution: respawn, merge, escalate, or drop | only when local convergence fails |
| 3 | **Synthesize** | converged graph + all grounded findings | final report with ranked findings | always at run end if frontier enabled |

### 3.3 Local-First Default

If frontier integration is disabled, the engine behaves exactly as it does today:

- `execute_graph` runs local recursive subgraphs.
- `build_report` synthesizes the final output from the graph.
- No frontier keys or network calls are required.

---

## 4. Components

### 4.1 New: `rgi/reasoning/frontier_integration.py`

A thin client layer with three entry points:

```python
class FrontierIntegration:
    async def plan_root(self, objective: str, world_model: dict) -> PlanResult: ...
    async def arbitrate(self, state: ArbitrationState) -> ArbitrationResult: ...
    async def synthesize(self, graph: CognitiveGraph, findings: list[dict]) -> Report: ...
```

Each method:
- Builds a compact, schema-bound prompt from graph state.
- Calls the frontier LLM through the existing `LLMClient` abstraction.
- Parses the response with Pydantic models.
- Falls back to local behavior on parse failure or timeout.

### 4.2 New: `FrontierConfig`

```python
@dataclass
class FrontierConfig:
    enabled: bool = False
    provider: str = "kimi"          # or openai, anthropic, ollama, etc.
    model: str | None = None
    base_url: str | None = None     # local/edge endpoint, e.g. http://localhost:11434/v1
    api_key: str | None = None      # optional; local providers often use "ollama" or none
    plan_at_start: bool = True
    arbitrate_on_deadlock: bool = True
    synthesize_at_end: bool = True
    max_arbitration_calls: int = 2
```

Controlled by environment variables (works in any terminal / VS Code terminal):
- `RGI_FRONTIER_ENABLED=1`
- `RGI_FRONTIER_PROVIDER=kimi`          # or ollama, openai, etc.
- `RGI_FRONTIER_MODEL=kimi-k2`
- `RGI_FRONTIER_BASE_URL=http://localhost:11434/v1`
- `RGI_FRONTIER_API_KEY=ollama`
- `RGI_FRONTIER_MAX_ARBITRATION=2`

The "frontier" can be a cloud API, a local Ollama instance, or any OpenAI-compatible endpoint.

### 4.3 Engine Hooks

Extend `rgi/core/engine.py` with three hooks inside `execute_graph`:

1. **Pre-execution plan:** If frontier is enabled, call `plan_root` before the first iteration and seed `spawn_suggestions` with its output.
2. **Mid-execution arbitration:** After each convergence check, call `needs_frontier_arbitration(graph)`. If true and budget remains, call `arbitrate` and apply the result.
3. **Post-execution synthesis:** In `build_report`, if frontier synthesis is enabled, call `synthesize` instead of the local report builder.

### 4.4 Trigger: `needs_frontier_arbitration`

Returns true when any of:

- Max local iterations reached and aggregate confidence < threshold.
- Two or more grounded findings contradict each other (e.g., same file/line marked both vulnerable and safe).
- A verification subgraph returns `challenge: true` for its parent finding and the local model cannot resolve it.
- `spawn_rejected` rate exceeds a threshold (local model is thrashing).

---

## 5. Data Contracts

### 5.1 Plan Result

```python
class PlanResult(BaseModel):
    strategy: str
    initial_subgraph_objectives: list[str]
    focus_areas: list[str]
    expected_findings: list[str] = []
```

### 5.2 Arbitration Result

```python
class ArbitrationResult(BaseModel):
    decision: Literal["respawn", "merge", "drop", "escalate"]
    reasoning: str
    spawn_objectives: list[str] = []
    findings_to_drop: list[str] = []
    escalate_to_user: bool = False
```

### 5.3 Synthesis Result

```python
class SynthesisResult(BaseModel):
    summary: str
    findings: list[dict]
    confidence: float
    recommendations: list[str] = []
```

---

## 6. Error Handling and Degradation

| Failure | Behavior |
|---------|----------|
| Frontier timeout | Retry once, then fall back to local behavior. |
| Frontier parse error | Log the raw response, fall back to local. |
| Frontier rate limit / quota | Disable frontier for remainder of run, continue local-only. |
| Frontier disabled or endpoint unreachable | Skip all frontier calls; pure local execution. |
| Arbitration returns invalid decision | Treat as "no-op" and continue local convergence. |

All fallbacks are auditable events in `Harness.audit`.

---

## 7. Testing

### 7.1 Unit Tests

- Mock frontier client returns deterministic plan/arbitrate/synthesize results.
- Verify `needs_frontier_arbitration` triggers on contradiction.
- Verify fallback to local report when frontier parse fails.

### 7.2 Integration Tests

- Mock end-to-end: frontier-enabled run on `sample_project` completes.
- Local-only run and frontier-enabled run produce comparable findings; frontier run should have cleaner synthesis.

### 7.3 Optional Frontier Shadow Mode

Run local-only and frontier-augmented side by side on the same target and compute a report similarity score. This validates that frontier integration does not lose recall.

---

## 8. Out of Scope

This design does **not** cover:

- HTTP/MCP/Tauri tool providers (see `rgi-unified-tool-harness-plan.md`).
- rlmlocal-site substrate integration beyond the existing JSON bridge.
- FortSignal governance integration beyond the existing stub gate.
- Memory layer (`fortmemory-vault`) persistence.

Those are tracked in separate specs and plans.

---

## 9. Success Criteria

1. With frontier enabled, `sample_project` analysis completes with no regressions vs. local-only.
2. Frontier plan call produces at least one additional high-confidence finding or eliminates at least one false positive vs. local-only.
3. Total frontier LLM calls per run ≤ 4 by default.
4. Fallback to local-only works silently when frontier is disabled or unavailable.

---

## 10. Relation to RGI Vision

This design keeps the core RGI thesis intact:

- **Graphs are computational units.** Local subgraphs do the work.
- **Intelligence organizes its own computation.** The engine decides when to invoke the frontier, not the user.
- **Cost-aware autonomy.** Frontier intelligence is treated as a scarce resource and spent only where it has leverage.
