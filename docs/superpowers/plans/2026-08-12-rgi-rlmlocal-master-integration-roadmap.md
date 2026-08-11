# RGI ↔ rlmlocal-site Master Integration Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement the referenced sub-plans task-by-task. This roadmap is the index; the detailed code/tasks live in the linked sub-plans.

**Goal:** Replace the piecemeal integration notes with one canonical roadmap that orders all work across RGI, rlmlocal-site, Tauri, MCP, and memory, without breaking either production codebase.

**Architecture:** RGI stays a Python recursive-graph orchestration kernel. rlmlocal-site stays a TypeScript local-first workbench. Integration is via a local HTTP/SSE adapter (primary channel) and MCP (tool bridge). A future Tauri desktop shell bundles RGI. fortmemory-vault is the durable memory sidecar. Each project keeps its own repo and release cadence.

**Tech Stack:** Python 3.11+, aiohttp, Pydantic, tree-sitter, TypeScript, Vite, Tauri, SSE, MCP JSON-RPC, SQLite/FTS5 (fortmemory).

## Global Constraints

- **RGI stays Python; rlmlocal-site stays TypeScript.** No engine rewrite.
- **rlmlocal-site production code is not modified unless behind a feature flag.**
- **All new network surfaces are local-only by default** (`127.0.0.1`).
- **Graph snapshots are versioned.** Unknown versions are rejected.
- **No unapproved writes.** Execution flows through existing verify/approve/land gates.
- **Commits are small and reviewable.** Each task ends with a passing test or smoke check.

---

## 1. Document Map

| Document | Path | Role |
|---|---|---|
| **Master roadmap** | `docs/superpowers/plans/2026-08-12-rgi-rlmlocal-master-integration-roadmap.md` | **This file.** Canonical index, decision log, phase dependencies, next actions. |
| Full integration analysis | `docs/internal/rgi-rlmlocal-full-integration-analysis.md` | Current state, gap analysis, chat-UI diagnosis, risks. |
| MCP wrapper analysis | `docs/internal/rgi-rlmlocal-mcp-wrapper-analysis.md` | How rlmlocal's MCP client works and how RGI can expose/consume MCP. |
| Adapter design spec | `docs/superpowers/specs/2026-08-12-rgi-rlmlocal-adapter-design.md` | HTTP/SSE API contract, graph snapshot schema, `RGIEngineClient`, phased adapter tasks. |
| Integration strategy | `docs/internal/2026-08-10-rgi-rlmlocal-integration-strategy.md` | Model A/C decision (port concepts vs. shared spec). |
| Tool integration plan | `docs/internal/rgi-rlmlocal-tool-integration-plan.md` | Dual MCP/HTTP tool exposure, tool inventory. |
| Unified tool harness plan | `docs/internal/rgi-unified-tool-harness-plan.md` | RGI `ToolRegistry` design for local/HTTP/MCP/Tauri providers. |
| Cognitive runtime strategy | `docs/internal/rgi-cognitive-runtime-strategy.md` | Three-layer architecture: substrate + orchestration + memory. |
| Engine language / Tauri design | `docs/superpowers/specs/2026-08-10-rgi-engine-language-and-tauri-integration-design.md` | Why RGI stays Python and how Tauri spawns it. |
| Unified desktop OS design | `docs/superpowers/specs/2026-08-10-rgi-unified-desktop-os-design.md` | v0.3 product split, auth, packaging vision. |
| OS governance integration | `docs/superpowers/specs/2026-08-10-rgi-os-governance-integration-strategy.md` | FortSignal governance split between Rust shell and Python engine. |
| Hybrid local/frontier design | `docs/superpowers/specs/2026-08-11-rgi-hybrid-local-frontier-integration-design.md` | Local models for constrained work, frontier for synthesis. |
| v0.3 perception port plan | `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md` | Porting rlmlocal graph semantics into RGI Python. |
| v0.3 Tauri desktop plan | `docs/superpowers/plans/2026-08-10-rgi-v0.3-tauri-desktop-integration.md` | Sidecar scaffolding and Tauri commands. |
| v0.3 unified desktop OS plan | `docs/superpowers/plans/2026-08-10-rgi-v0.3-unified-desktop-os-implementation-plan.md` | End-to-end desktop build tasks. |
| v0.3 noise reduction plan | `docs/superpowers/plans/2026-08-10-rgi-v0.3-noise-reduction.md` | Convergence/precision fixes for local models. |

---

## 2. Canonical Decision Log

| # | Decision | Rationale | Where it lives |
|---|---|---|---|
| 1 | **RGI stays Python.** | Ecosystem, research velocity, C2 bottleneck is inference not Python CPU. | `2026-08-10-rgi-engine-language-and-tauri-integration-design.md` |
| 2 | **rlmlocal-site is not rewritten.** | It is the production product; integration is adapter-only. | Adapter design spec §Global Constraints |
| 3 | **Integration model is Model C with Model A inside RGI.** | Shared graph snapshot spec; RGI also ports rlmlocal graph algorithms to Python. | `2026-08-10-rgi-rlmlocal-integration-strategy.md` |
| 4 | **Primary transport is HTTP/SSE.** | Browser-friendly, low latency, fits rlmlocal's event model. | Adapter design spec §4 |
| 5 | **MCP is a secondary tool bridge.** | Reuse rlmlocal's existing MCP client; expose RGI tools without new adapter code. | `rgi-rlmlocal-mcp-wrapper-analysis.md` |
| 6 | **Tauri desktop is a separate product shell.** | Sidecar spawns RGI; rlmlocal UI components reused; no in-place rewrite. | `2026-08-10-rgi-unified-desktop-os-design.md` |
| 7 | **FortSignal auth is Phase 4.** | v0.3 can ship local-only or with simple token; passkey integration comes after core engine works. | Desktop OS design §Open questions |
| 8 | **Deterministic scanner is the floor.** | `security_scan` seeds findings so weak models don't miss real vulns. | `rgi-cognitive-runtime-strategy.md` |
| 9 | **Mandatory verification gate.** | Every non-scanner finding must be tool-verified before reporting. | `rgi-cognitive-runtime-strategy.md` §Phase 1 |
| 10 | **Graph is truth.** | All reasoning grounded in rlmlocal's live code graph or an imported snapshot. | `rgi-cognitive-runtime-strategy.md` §Design principles |

---

## 3. System Boundary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Human-in-the-loop UI                                                        │
│  rlmlocal-site PWA  OR  Tauri Desktop (reusing rlmlocal components)         │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ HTTP/SSE 127.0.0.1:8787
                            │ MCP JSON-RPC /mcp (optional)
┌───────────────────────────▼─────────────────────────────────────────────────┐
│ RGI Python engine                                                           │
│  - /v1/chat, /v1/snapshot, /v1/security-scan                                │
│  - recursive spawn/verify/correct loops                                     │
│  - ToolRegistry (local + MCP providers)                                     │
│  - perception port (import/call/data-flow/reference graphs)                 │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ reads / queries
┌───────────────────────────▼─────────────────────────────────────────────────┐
│ Code substrate (one of)                                                     │
│  A) rlmlocal-site exported graph snapshot                                   │
│  B) RGI's own tree-sitter graph builder (perception port)                   │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ writes / reads
┌───────────────────────────▼─────────────────────────────────────────────────┐
│ Durable memory (future)                                                     │
│  fortmemory-vault — episodic notes, semantic facts, procedural skills       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase Overview

| Phase | Goal | Primary repo | Key deliverables | Depends on | Exit criteria |
|---|---|---|---|---|---|
| **0. Hardening** | Fix RGI's own reasoning noise so the adapter has something useful to route. | `rgi` | finding-prompt fix, size-aware convergence, generic filesystem tools | — | C2 benchmark stable or improved; `security_scan` reliable. |
| **1. Adapter skeleton** | rlmlocal-site can toggle RGI on and see streamed findings. | `rgi` + `rlmlocal-site` | project store, SSE endpoints, `RGIEngineClient`, feature flag | Phase 0 | Feature flag routes chat to RGI; findings render in UI. |
| **2. Graph port** | RGI builds a rlmlocal-style multi-language graph itself. | `rgi` | call/data-flow/reference graphs in Python; snapshot ingest | Phase 1 | RGI warms from folder or snapshot with rich edges. |
| **3. Execution loop** | RGI proposes changes through rlmlocal's verify/approve/land flow. | `rgi` + `rlmlocal-site` | patch tools, `execRequest` proxy, proposal cards | Phase 2 | End-to-end verified patch lands from RGI. |
| **4. MCP bridge** | RGI exposes tools via MCP and consumes external MCP servers. | `rgi` | `/mcp` endpoint, `McpToolProvider`, env config | Phase 1 | rlmlocal can call RGI tools through its existing MCP client. |
| **5. Tauri desktop** | Ship a single installable desktop app bundling RGI. | `rgi` (sidecar) | Rust spawn commands, Python bundling strategy, UI reuse | Phase 3 or 4 | One download → pick folder → run analysis. |
| **6. Memory + governance** | fortmemory sidecar + FortSignal passkey integration. | `rgi` + `fortmemory-vault` | memory writes/reads, auth flow, signed audit | Phase 5 | Runs remember lessons; auth binds policy. |

---

## 5. Immediate Tasks (Next 2 Weeks)

These are the concrete first steps. Each points to a sub-plan for code-level detail.

### Task 1: Create a feature branch for integration work

**Files:**
- Repo: `rgi`
- Branch name: `feature/rgi-rlmlocal-adapter`

**Interfaces:**
- Produces: isolated branch off `main` or current dev branch.

- [ ] **Step 1: Check current branch and status**

```bash
cd /home/jeff/projects/rgi
git status
```

Expected: clean working tree on a known branch.

- [ ] **Step 2: Create feature branch**

```bash
git checkout -b feature/rgi-rlmlocal-adapter
```

- [ ] **Step 3: Push branch to remote**

```bash
git push -u origin feature/rgi-rlmlocal-adapter
```

Do **not** modify `rlmlocal-site` production; keep any rlmlocal changes on a separate branch when they happen.

---

### Task 2: Complete Phase 0 — RGI hardening

**Files:**
- Modify: `rgi/core/findings.py`, `rgi/core/engine.py`, `rgi/cli.py`, `rgi/tools/filesystem.py`, `rgi/tools/registry.py`
- Test: `tests/test_findings.py`, `tests/test_filesystem_tools.py`, benchmark run

**Interfaces:**
- Consumes: existing `normalize_finding`, `run_analysis`, `ToolRegistry`.
- Produces: finding schema alignment, size-aware convergence defaults, `list_dir`/`find_files`/`stat` tools.

- [ ] **Step 1: Follow Task 0.1 and 0.2 in the adapter design spec**

```bash
# Verify the docs exist
ls docs/superpowers/specs/2026-08-12-rgi-rlmlocal-adapter-design.md
```

- [ ] **Step 2: Implement the changes and run tests**

```bash
cd /home/jeff/projects/rgi
pytest tests/test_findings.py tests/test_filesystem_tools.py -v
python -m rgi analyze benchmarks/vuln_app_2 --objective "Find security vulnerabilities" --provider ollama --model qwen2.5:7b
```

Expected: tests pass; benchmark completes with recall ≥ previous best.

- [ ] **Step 3: Commit**

```bash
git add rgi/core/findings.py rgi/core/engine.py rgi/cli.py rgi/tools/filesystem.py rgi/tools/registry.py tests/
git commit -m "feat(hardening): finding schema, convergence defaults, filesystem tools"
```

---

### Task 3: Complete Phase 1 — Adapter skeleton

**Files:**
- RGI: `rgi/api/project_store.py`, `rgi/api/snapshot.py`, `rgi/api/sse.py`, `rgi/api/security_stream.py`, `rgi/api/chat_stream.py`, `rgi/server.py`
- rlmlocal-site: `src/features/agent/RGIEngineClient.ts`, `src/features/agent/engineWiring.ts`, `src/main.ts`, `src/features/chat/sendMessage.ts`
- Tests: `tests/test_snapshot_endpoint.py`, `tests/test_sse.py`, `tests/test_security_stream.py`, `tests/test_chat_stream.py`, plus TS unit test

**Interfaces:**
- Consumes: `IEngine` from `engine.protocol.ts`, `run_analysis`, `run_security_scan`, graph snapshot schema.
- Produces: `POST /v1/projects/{id}/snapshot`, `/chat`, `/security-scan`; `RGIEngineClient` implementing `IEngine`; feature flag wiring.

- [ ] **Step 1: Follow Tasks 1.1–1.9 in the adapter design spec**

Reference: `docs/superpowers/specs/2026-08-12-rgi-rlmlocal-adapter-design.md` §7 Phase 1.

- [ ] **Step 2: Run Python tests**

```bash
cd /home/jeff/projects/rgi
pytest tests/test_snapshot_endpoint.py tests/test_sse.py tests/test_security_stream.py tests/test_chat_stream.py -v
```

Expected: all pass.

- [ ] **Step 3: Run TypeScript unit test**

```bash
cd /home/jeff/projects/rlmlocal-site
npm test -- RGIEngineClient.test.ts
```

Expected: pass.

- [ ] **Step 4: Integration smoke test**

```bash
# Terminal 1
cd /home/jeff/projects/rgi
python -m rgi server --port 8787

# Browser dev console on rlmlocal-site
localStorage.setItem('rgi-adapter-enabled', '1');
location.reload();
```

Ask: "Run a security scan." Expected: red findings card appears.

- [ ] **Step 5: Commit both repos**

```bash
cd /home/jeff/projects/rgi
git add rgi/api/ rgi/server.py rgi/tools/ tests/
git commit -m "feat(adapter): SSE endpoints, project store, RGIEngineClient integration"
```

---

### Task 4: Add MCP server surface to RGI

**Files:**
- Create: `rgi/mcp/server.py`
- Modify: `rgi/server.py` (mount `/mcp`), `rgi/tools/harness.py` (if provider interface needs extension)
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `ToolRegistry.list_tools_for_prompt()`, `ToolRegistry.execute()`.
- Produces: MCP `initialize`, `tools/list`, `tools/call` JSON-RPC endpoints.

- [ ] **Step 1: Follow Option C in the MCP analysis doc**

Reference: `docs/internal/rgi-rlmlocal-mcp-wrapper-analysis.md` §3.1.

- [ ] **Step 2: Test with rlmlocal's MCP client**

```bash
# Start RGI with /mcp
cd /home/jeff/projects/rgi
python -m rgi server --port 8787

# In rlmlocal-site dev console, add RGI as an MCP server
localStorage.setItem('rlm-mcp-servers', JSON.stringify(['http://127.0.0.1:8787/mcp']));
location.reload();
```

Verify the server appears in the MCP panel and lists RGI tools.

- [ ] **Step 3: Commit**

```bash
git add rgi/mcp/ rgi/server.py tests/test_mcp_server.py
git commit -m "feat(mcp): expose RGI ToolRegistry as MCP server"
```

---

### Task 5: Snapshot export from rlmlocal-site (Phase 2 prep)

**Files:**
- Create: `rlmlocal-site/src/features/agent/exportSnapshot.ts`
- Modify: `rlmlocal-site/src/features/agent/engineWiring.ts` to pass snapshot to `RGIEngineClient`
- Test: unit test for export function

**Interfaces:**
- Consumes: `VectorStore`, graph indexes.
- Produces: `rgi-graph-snapshot-v1` JSON object.

- [ ] **Step 1: Implement export function**

Walk `VectorStore` + import/call/data-flow/reference indexes and emit the snapshot schema defined in the adapter design spec §3.

- [ ] **Step 2: Validate snapshot against RGI importer**

```bash
cd /home/jeff/projects/rgi
python -c "
from rgi.api.snapshot import import_snapshot
import json
snap = json.load(open('/tmp/rlmlocal_snapshot.json'))
project = import_snapshot(snap, 'test')
print(len(project.graph.nodes), len(project.graph.edges))
"
```

Expected: import succeeds and reports node/edge counts.

- [ ] **Step 3: Commit**

```bash
cd /home/jeff/projects/rlmlocal-site
git add src/features/agent/exportSnapshot.ts src/features/agent/engineWiring.ts
git commit -m "feat(agent): export rlmlocal graph snapshot for RGI"
```

---

## 6. Later Phases (High-Level)

### Phase 2 — Graph port
- Reference: `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md`
- Goal: RGI builds import/call/data-flow/reference graphs from a folder using tree-sitter.
- Owner: `rgi`
- Blocked by: Phase 1

### Phase 3 — Execution loop
- Reference: `docs/superpowers/specs/2026-08-12-rgi-rlmlocal-adapter-design.md` §Phase 3
- Goal: RGI emits patch proposals that flow through rlmlocal's `verify_patch` → approve → `apply_patch`.
- Owner: `rgi` + `rlmlocal-site`
- Blocked by: Phase 2

### Phase 4 — MCP client provider in RGI
- Reference: `docs/internal/rgi-rlmlocal-mcp-wrapper-analysis.md` §3.2
- Goal: RGI can call external MCP servers (cloud web tools, user-added servers).
- Owner: `rgi`
- Blocked by: Phase 1

### Phase 5 — Tauri desktop packaging
- Reference: `docs/superpowers/plans/2026-08-10-rgi-v0.3-tauri-desktop-integration.md`, `docs/superpowers/plans/2026-08-10-rgi-v0.3-unified-desktop-os-implementation-plan.md`
- Goal: Single installable app that spawns RGI and reuses rlmlocal UI.
- Owner: `rgi` sidecar example
- Blocked by: Phase 3 or 4

### Phase 6 — Memory + FortSignal governance
- Reference: `docs/internal/rgi-cognitive-runtime-strategy.md`, `docs/superpowers/specs/2026-08-10-rgi-os-governance-integration-strategy.md`
- Goal: fortmemory sidecar integration; passkey auth; signed audit.
- Owner: `rgi` + `fortmemory-vault`
- Blocked by: Phase 5

---

## 7. Open Blockers

| Blocker | Current status | Owner | Resolution path |
|---|---|---|---|
| FortSignal auth endpoints/credentials | Unknown | Tauri / auth service | Defer to Phase 4; use local-only or simple token for v0.3. |
| Python runtime bundling strategy | Not decided | Packaging | Spike PyInstaller vs. uv vs. system Python in Phase 5. |
| rlmlocal-site chat UI abort/race bugs | Diagnosed | rlmlocal-site | Fix independently or adapter avoids worker path; see analysis doc §6. |
| RGI local-model precision on real OSS | High recall, low precision | RGI | Phase 0 mandatory verification + Phase 2 substrate. |
| Graph snapshot performance for large repos | Unknown | Both | Export incremental/debounced; test with real projects. |

---

## 8. Definition of Done for v0.3

- [ ] A user can enable the RGI adapter in rlmlocal-site with one `localStorage` flag.
- [ ] Chat routes to RGI; `security_scan` findings render in the chat UI.
- [ ] RGI can import a rlmlocal-site graph snapshot or build its own multi-language graph.
- [ ] RGI exposes its tools via MCP; rlmlocal can call them without new adapter code.
- [ ] `rlmlocal-site` production path remains unchanged and functional when the flag is off.
- [ ] All new RGI code has tests; integration smoke test passes.
- [ ] Tauri sidecar can spawn RGI and run an analysis (Phase 5 stretch).

---

## 9. Next Actions (Today / Tomorrow)

1. **Review this roadmap** and confirm phase ordering.
2. **Create the `feature/rgi-rlmlocal-adapter` branch** in `rgi`.
3. **Start Task 2** (Phase 0 hardening) — it is unblocked and gives immediate benchmark payoff.
4. **Schedule a spike** on Python runtime bundling before Phase 5.
5. **Keep rlmlocal-site untouched** until Task 3 (adapter skeleton) is ready.
