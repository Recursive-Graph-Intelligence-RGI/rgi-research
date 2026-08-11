# RGI Cognitive Runtime Strategy

**Date:** 2026-08-10  
**Purpose:** Synthesize deep analysis of `rlmlocal-site`, `rgi`, and `fortmemory-vault` plus external research into a concrete, phased plan for a continuously-running recursive code-intelligence runtime.

---

## Executive Summary

The "frontier-level intelligence by running longer" intuition is **partially right but the wrong lever**. A 4B/7B local model does not become a frontier model through more tokens or deeper recursion. It *can* punch above its weight when the architecture:

1. **Gives it a rich, queryable code substrate** (rlmlocal-site's graph).
2. **Constrains each reasoning step to a narrow, verifiable task** (RGI subgraphs).
3. **Requires tool-grounded verification before any finding is believed** (RGI verification loops).
4. **Stores durable memory across runs** (fortmemory-vault).
5. **Uses deterministic scanners as a fast-path floor** (RGI `security_scan`).

The winning architecture is a **three-layer cognitive runtime**:

- **Substrate layer:** `rlmlocal-site` builds and maintains the live code graph.
- **Orchestration layer:** `rgi` recursively plans, spawns, verifies, and converges.
- **Memory layer:** `fortmemory-vault` persists episodic runs, semantic facts, and procedural skills.

This document lays out what each project contributes, what external research confirms, and a phased implementation path.

---

## 1. What We Analyzed

### 1.1 `rlmlocal-site` — the code substrate

`rlmlocal-site` is a mature **local-first, human-in-the-loop cognitive runtime for code maintenance**.

**Core strengths:**
- **Multi-layer code graph:** import, call, data-flow (G1), route-reference (G2), co-change, and semantic concept layers, all version-anchored and freshness-healed.
- **Tree-sitter parsing** for TS/JS/TSX, Python, Go, Rust.
- **Vector store + embeddings** (local Transformers.js / Ollama) with concept detection.
- **Two-door execution model:** deterministic T0/T1 refactor plans and an OpenCode shadow loop for larger changes; every write is verified in a disposable worktree before human approval.
- **Skill runtime:** declarative skills (`analyze`, `find-callers`, `plan`, `move`, `extract`, `converge`, etc.) routed through a command palette.
- **Model-agnostic providers:** Ollama, WebLLM, Cloudflare Workers AI, Anthropic, with context-window budgeting.
- **Tauri desktop shell + Cloudflare Pages/Worker deployment**.

**Gaps relevant to RGI:**
- Recursive orchestration is present (`SimpleRLMAgent`, `RecursiveScheduler`) but the deepest value is in single-turn question answering and verified edits, not long-horizon autonomous investigation.
- No external recursive-graph engine integration beyond the designed-but-not-shipped RGI bridge.
- Graph UI is rich but graph-first action wiring is incomplete.

**Key files:**
- `src/features/agent/SimpleRLMAgent.ts` — main agent loop.
- `src/features/agent/RecursiveScheduler.ts` — depth/budget/convergence controller.
- `src/features/agent/VectorStore.ts` — graph + embedding store.
- `src/features/agent/importGraph.ts`, `dataFlowGraph.ts`, `referenceGraph.ts` — graph layers.
- `src/features/execution/platform.ts`, `RunCodeTaskIterate.ts` — verify/apply pipeline.
- `planning/MASTER-ARCHITECTURE-2026-07-26.md` — engineering frame.

### 1.2 `rgi` — the recursive orchestrator

`rgi` is a **hybrid recursive-graph intelligence engine**: engineered topology handles decomposition, coverage, governance, and audit; the LLM is a reasoning primitive inside nodes.

**Core strengths:**
- `CognitiveGraph` / `CognitiveNode` / `CognitiveEdge` data model with typed loop types (`PLANNING`, `EXECUTION`, `VERIFICATION`, `GOVERNANCE`, `LEARNING`).
- `Harness` enforces hard caps on depth, nodes, LLM calls, time.
- Topological self-correction: verification spawns new graphs rather than retrying.
- Multi-language perception port (`rgi/perception/rlmlocal_compat/`) and rlmlocal JSON graph bridge.
- HTTP server mode (`rgi/server.py`) and a Tauri sidecar example.
- Deterministic security scanner seed.

**Gaps:**
- Default perception is shallow without `RGI_RLMLocal_PERCEPTION=1`.
- REPL/tool use is not deeply integrated into recursive execution; model must generate `repl_code` itself.
- Local-model precision collapse on real OSS: high recall but very low precision (duplicates, hallucinated files, vague findings).
- `FortSignalGate` is a stub.

**Key files:**
- `rgi/core/engine.py` — five-phase execution loop.
- `rgi/core/harness.py` — safety kernel.
- `rgi/perception/rlmlocal_compat/graph_bridge.py` — rlmlocal interchange.
- `rgi/tools/security_scan.py` — deterministic scanner.
- `rgi/core/findings.py` — finding normalization/deduplication.

### 1.3 `fortmemory-vault` — governable agent memory

`fortmemory-vault` is a **local-first agent memory server** for Markdown/Obsidian vaults with cryptographic authorization per write.

**Core strengths:**
- Canonical storage as human-readable `.md` files; SQLite FTS5 + optional Ollama embeddings for fast search.
- FortSignal-governed writes (`challenge` → `start` → `sign` → `verify`); reads use local bearer tokens.
- HTTP REST API + MCP stdio server.
- Path-jailed vault I/O, policy-based deny lists.

**Relevance:**
- Provides exactly the durable memory layer RGI currently lacks. RGI's `data/pathways.json` and per-run JSON dumps are not queryable across sessions.
- Fits naturally as a sidecar: RGI writes findings, runbooks, lessons, and episode notes; RGI retrieves relevant context via `/v1/search`.

**Key files:**
- `internal/server/server.go` — HTTP API.
- `internal/memory/memory.go` — write/read/search orchestration.
- `internal/index/sqlite.go` — FTS5 + hybrid vector search.
- `docs/API.md`, `docs/openapi.yaml` — API contract.

---

## 2. What External Research Confirms

### 2.1 Recursive multi-agent systems can exceed single-model performance

[ReDel: A Toolkit for LLM-Powered Recursive Multi-Agent Systems](https://arxiv.org/html/2408.02248v2) frames recursive delegation as a way for a root agent to dynamically spawn sub-agents rather than relying on a static decomposition graph. The key insight is that **topology can compensate for model limitations** — exactly RGI's thesis.

### 2.2 Agent memory should be typed: working, episodic, semantic, procedural

Multiple sources ([Vicco Labs](https://www.viccolabs.com.br/en/articles/agent-memory-episodic-semantic-procedural), [Atlan](https://atlan.com/know/types-of-ai-agent-memory/), [Patronus](https://www.patronus.ai/ai-agent-development/agentic-memory), [Synthara](https://www.syntharatechnologies.com/blog/agent-memory-architectures)) agree:

- **Working memory:** current session state and tool outputs (RGI `memory_snapshot`, `ledger`).
- **Episodic memory:** summaries of past runs/decisions (fits `fortmemory-vault` notes).
- **Semantic memory:** durable facts and relationships (validated findings, call-graph facts).
- **Procedural memory:** learned workflows/skills (RGI skills, GEPA-evolved prompts).

[Synthara](https://www.syntharatechnologies.com/blog/agent-memory-architectures) specifically notes that **vector DBs struggle with multi-hop relationships while graph DBs excel**; production systems combine both with a SQL store for verifiable facts. This argues for keeping rlmlocal's graph *and* fortmemory's search.

### 2.3 Hybrid SAST + LLM outperforms either alone

[Large Language Models Versus Static Code Analysis Tools: A Systematic Benchmark for Vulnerability Detection](https://arxiv.org/abs/2508.04448) found that LLM-based scanners achieved higher F-1 scores than SonarQube/CodeQL/Snyk on a curated C dataset. [LLMVD.js](https://arxiv.org/pdf/2604.20179) showed a ReAct agent with tool use confirming 84% of vulnerabilities in npm packages. The pattern is consistent: **deterministic rules find the floor, LLM + tools finds the ceiling**.

### 2.4 Tree-sitter knowledge graphs improve code exploration

[Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP](https://arxiv.org/abs/2603.27277) demonstrates that a persistent Tree-sitter knowledge graph exposed via MCP improves LLM code exploration. rlmlocal-site already has this; RGI needs to consume it.

### 2.5 Verification reduces false positives

The same LLMVD.js work and Agent Audit research ([Agent Audit: A Security Analysis System for LLM Agent Applications](https://arxiv.org/pdf/2603.22853)) emphasize that **confirmation via tool use / taint analysis** is what turns LLM guesses into reliable findings. RGI's verification loop is architecturally correct but under-utilized for local-model findings.

---

## 3. The Cognitive Runtime Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Human-in-the-loop UI (rlmlocal-site cockpit / Tauri shell)      │
│  - graph canvas, chat, approve/reject gates, skill palette       │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP / MCP / graph JSON
┌───────────────────────▼─────────────────────────────────────────┐
│  Orchestration Kernel (rgi)                                      │
│  - recursive planner, spawn/verify/correct loops                 │
│  - governance: depth, budget, time, audit                        │
│  - tool registry: read_file, grep, callers, REPL, security_scan  │
└───────────────────────┬─────────────────────────────────────────┘
                        │ queries
┌───────────────────────▼─────────────────────────────────────────┐
│  Code Substrate (rlmlocal-site engine worker / exported graph)   │
│  - Tree-sitter ASTs, import/call/data-flow/reference edges       │
│  - embeddings, concepts, freshness healing                       │
└───────────────────────┬─────────────────────────────────────────┘
                        │ writes / reads
┌───────────────────────▼─────────────────────────────────────────┐
│  Durable Memory (fortmemory-vault)                               │
│  - episodic run notes, semantic facts, procedural skills         │
│  - FTS5 + vector search, FortSignal-governed writes              │
└─────────────────────────────────────────────────────────────────┘
```

**Design principles:**
1. **Graph is truth.** All reasoning is grounded in rlmlocal's live code graph.
2. **Findings are guilty until proven innocent.** Every LLM-generated finding must be verified by a tool call before reporting.
3. **Scanner is the floor.** Deterministic checks run first; LLM explores what patterns miss.
4. **Memory spans runs.** fortmemory retains validated lessons so the runtime improves over time.
5. **Local models do constrained work; frontier models do synthesis.** Route high-uncertainty synthesis to stronger models, keep verification local.

---

## 4. Phased Implementation Plan

### Phase 1: Clean up RGI's own reasoning quality (days)

**Goal:** Make 4B/7B local models useful within RGI by eliminating noise.

1. **Mandatory verification gate**
   - Every non-scanner finding must be confirmed by a `VERIFICATION` subgraph that reads the cited file/line and answers `finding_valid: bool`.
   - If verification fails, drop the finding; if it succeeds, promote it with verifier confidence.

2. **Narrower subgraph objectives**
   - Replace broad spawn reasons (`"auth"`, `"config"`) with concrete mandates (`"verify jwt.decode exp check at auth.py:17"`, `"check for plaintext password comparison in login.py"`).
   - Pass file + line + symbol into the objective so the model's job is verification, not discovery.

3. **Better deduplication**
   - Merge findings at the same `(file, line, symbol)` even when kinds differ, keeping the highest-confidence canonical kind from the scanner.

4. **LLM capability gate**
   - For models < 7B: scanner-heavy mode, fewer subgraphs, no REPL.
   - For models >= 7B / frontier: enable deeper exploration.

**Expected outcome:** 4B/7B reports on `sample_project` and `fusion-edge/api` remain at 100% true-positive rate with near-zero noise.

### Phase 2: Consume rlmlocal's graph substrate (weeks)

**Goal:** Replace RGI's shallow perception with rlmlocal's rich graph.

1. **Graph export from rlmlocal**
   - Add a JSON export endpoint or file format containing nodes (files, functions, classes, symbols) and edges (imports, calls, data-flow, references).
   - Reuse the existing `graph_bridge.py` importer.

2. **Symbol-aware activation**
   - Instead of keyword/embedding activation over file labels, activate specific symbols relevant to the objective (e.g., all functions calling `jwt.decode`).

3. **Tool queries over the graph**
   - `get_callers(symbol)`
   - `get_callees(symbol)`
   - `get_data_flow(resource_key)`
   - `get_route_handlers(route)`
   - `find_similar_symbols(embedding)`

4. **REPL powered by graph**
   - Let the model write Python over the graph structure (not just raw file text) so it can navigate relationships programmatically.

**Expected outcome:** RGI can answer questions like "show me every code path that reads `POSTGRES_PASSWORD`" and trace cross-file vulnerability chains.

### Phase 3: Add durable memory via fortmemory (weeks)

**Goal:** Make the runtime stateful across runs and projects.

1. **Run episodes**
   - After each analysis, write a Markdown note to fortmemory: objective, findings, model used, topology metrics, lessons.

2. **Semantic facts**
   - Store validated findings as structured facts: `project/X has hardcoded secret at Y`, `auth.py jwt.decode lacks exp verification`.
   - On new runs, retrieve relevant facts via `/v1/search` and seed them into the root graph.

3. **Procedural memory / skills**
   - When a verification pattern works repeatedly, promote it to a skill template (e.g., `verify_jwt_exp_check`).
   - Store the skill in fortmemory and register it with RGI's tool registry.

4. **Cross-project memory**
   - If the same vulnerability class appears across projects, surface that pattern as a global lesson.

**Expected outcome:** The runtime gets faster and more accurate the more it runs.

### Phase 4: Dynamic scanner / skill generation (research)

**Goal:** Move beyond hand-written checks.

1. **Synthesize checkers**
   - Use a frontier model to write small Python checkers for novel vulnerability patterns observed in episodes.
   - Sandbox-execute them; if they produce verified findings, promote them.

2. **GEPA for prompts**
   - Mine successful verification subgraph traces to evolve better system prompts and subgraph objectives.

3. **Learned decomposition policies**
   - Train or prompt-engineer a meta-planner that decides when to spawn verification vs exploration subgraphs based on past outcomes.

**Expected outcome:** The runtime discovers and codifies new vulnerability classes autonomously.

---

## 5. What *Not* To Do

1. **Don't brute-force longer runs with small models.** More tokens won't fix reasoning quality; it increases noise and cost.
2. **Don't abandon the scanner.** Deterministic checks are the floor that keeps reports reliable.
3. **Don't let the LLM write to production code without verify/approve gates.** rlmlocal's two-door model is the right discipline.
4. **Don't store unverified findings as memory.** fortmemory should only receive findings that survived verification.
5. **Don't try to merge all three codebases into one repo.** Keep them as sidecars with clean interfaces (HTTP/MCP/graph JSON).

---

## 6. Immediate Next Action

Implement **Phase 1**:
- Add verification subgraph requirement for non-scanner findings.
- Tighten spawn objectives to file:line:symbol scope.
- Add LLM capability gate.
- Re-run 4B and 7B benchmarks to measure precision/recall improvement.

This is the highest-ROI step and does not require touching rlmlocal-site or fortmemory. Once Phase 1 is solid, the value of Phases 2–4 becomes much clearer.

---

## 7. Bottom Line

Your intuition about a continuously-running cognitive runtime is right. The correct lever is not "more compute on small models" but **better architecture**: scanner floor, graph substrate, narrow verified subgraphs, and durable memory. RGI + rlmlocal-site + fortmemory-vault already contain all the pieces; the work is wiring them together in the right order.
