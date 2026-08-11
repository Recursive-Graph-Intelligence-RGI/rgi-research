# RGI ↔ rlmlocal-site Tool Integration Plan

**Date:** 2026-08-10  
**Goal:** Inventory every tool built in rlmlocal-site (browser, Tauri, MCP, skills, engine RPCs) and design a concrete plan to unify them with RGI's tool registry.

---

## 1. Tool Inventory

### 1.1 rlmlocal-site Browser Toolkit
`src/lib/tools/browserTools.ts`

| Tool | What it does | RGI equivalent? |
|------|--------------|-----------------|
| `listDir` | List files/dirs at a path | **Missing** |
| `readFile` | Read file contents (full or truncated) | `read_file` exists but lacks span/offset options |
| `grep` | Regex search across files | `grep` exists |
| `findFiles` | Find files by glob/name | **Missing** |
| `writeFile` | Write file (gated) | **Missing** |
| `editFile` | Targeted string replacement (gated) | **Missing** |
| `stat` | mtime + size probe | **Missing** |

### 1.2 rlmlocal-site Engine RPC Queries
`src/features/agent/engine.protocol.ts`

| Method | What it does | RGI equivalent? |
|--------|--------------|-----------------|
| `readFile` | Read with context | `read_file` |
| `getDependencies` | File imports | Partial: `callers` |
| `getDependents` | Files importing target | Partial: `callers` |
| `cochangeOf` / `cochangeStats` | Git co-change graph | **Missing** |
| `getFileStructure` | Functions/classes/imports in file | `parse_python_file` (Python-only) |
| `listPaths` | All indexed paths | **Missing** |
| `findLiteralTargets` | Find literal strings across codebase | **Missing** |
| `conceptContextFor` | Concept summary for a file | **Missing** |
| `conceptMembers` | Members of a concept | **Missing** |
| `getCodingCandidates` | Files relevant to a question | Activation engine (weaker) |
| `completeWithCoder` / `invokeWithCoder` | Coder-model completion | **Missing** |
| `levelSlice` | Graph slice visualization | **Missing** |
| `importLineFor` | Correct import line between files | **Missing** |
| `fileNeighborhood` | N-hop file neighborhood | **Missing** |
| `resolveSymbols` | Type at position | **Missing** |
| `resolveCallers` | Callers of a symbol | `callers` (limited) |
| `searchSymbols` | Symbol search | **Missing** |

### 1.3 rlmlocal-site Tauri / Execution Commands
`src-tauri/src/lib.rs` via `src/features/execution/platform.ts`

| Command | What it does | RGI equivalent? |
|---------|--------------|-----------------|
| `run_tests` | Run project test suite | `run_pytest` (Python-only) |
| `verify_patch` | Verify edits in shadow worktree | **Missing** |
| `apply_patch` | Apply verified edits to real project | **Missing** |
| `resolve_types` | TS compiler type at position | **Missing** |
| `compute_refactor` | TS language-service refactor edits | **Missing** |
| `git_cochange` | Git co-change matrix | **Missing** |
| OpenCode host commands | Spawn `opencode serve`/`run` | **Missing** |

### 1.4 rlmlocal-site MCP Cloud Tools
`worker/mcp-server.ts`

| Tool | What it does | RGI equivalent? |
|------|--------------|-----------------|
| `web_search` | Search the web | **Missing** |
| `fetch_page` | Fetch any URL as readable text | **Missing** |
| `get_weather` | Weather lookup | **Missing** |
| `get_stock` | Stock price lookup | **Missing** |
| `get_news` | News headlines | **Missing** |

### 1.5 rlmlocal-site MCP Exposed Local Tools
`src/lib/mcp/McpClient.ts`

| Tool | What it does |
|------|--------------|
| `list_local_resources` | List local files |
| `read_local_file` | Read local file |
| `grep_local_resources` | Grep local files |
| `search_memory` | Search memory store |
| `get_relations` | Get memory relations |
| `rlm_*` | RLM-specific skills |

### 1.6 rlmlocal-site Skills
`src/features/skills/skillTemplates.ts`

**T0 — understanding:** analyze, find-callers, find-callees, find-dependencies, metrics, cluster-map, cluster-fields.  
**T0 — planning:** plan, decompose, design, reason.  
**T1 — verified changes:** move, move-cluster, batch-move, extract, carve, decouple, converge, run-tests, etc.

### 1.7 RGI Tools Today
`rgi/tools/registry.py`

- `parse_python_file`
- `grep_security_patterns`
- `check_jwt_usage`
- `find_hardcoded_secrets`
- `explore_corpus` (sandboxed REPL)
- `read_file`, `grep`, `callers`
- `run_py_compile`, `run_pytest`, `run_pyflakes`
- `security_scan`

---

## 2. Integration Architecture

The cleanest path is **dual MCP/HTTP exposure**: every tool lives in one authoritative runtime and is callable from the other over a standard protocol.

```
┌─────────────────────────────────────────────────────────────────────┐
│  rlmlocal-site cockpit (Vite + Tauri shell)                          │
│  - UI, graph canvas, approve/reject gates, chat                      │
└───────────────┬───────────────────────┬─────────────────────────────┘
                │                       │
                │ HTTP/MCP              │ Tauri invoke
                │                       │
┌───────────────▼───────┐   ┌───────────▼────────────┐
│  RGI Python server    │   │  Tauri Rust executor    │
│  - recursive planner  │   │  - verify/apply patches │
│  - security scanner   │   │  - run tests            │
│  - explore_corpus     │   │  - TS compiler service  │
│  - governance/audit   │   │  - git ops              │
└───────┬───────────────┘   └───────┬─────────────────┘
        │                           │
        │ MCP client                │ direct
        │                           │
┌───────▼───────────────────────────▼─────────────────────────────────┐
│  rlmlocal-site Engine Worker (Browser/Web Worker)                    │
│  - graph store, embeddings, freshness, browser toolkit               │
│  - exposes graph queries + browser file tools as MCP/HTTP            │
└─────────────────────────────────────────────────────────────────────┘
```

**Design rules:**
1. **Single registry per runtime.** RGI has one `ToolRegistry`; rlmlocal's engine worker has its own tool/skill surface. They call each other over HTTP/MCP, not by merging codebases.
2. **No direct Tauri from RGI.** RGI talks to Tauri only through the rlmlocal main thread relay (same pattern already used by the engine worker's `execRequest`).
3. **Skills are transport-agnostic prompt templates.** A skill template describes intent; the runtime resolves which tools are available locally vs remotely.
4. **Approval gates stay in rlmlocal-site.** RGI can propose writes; rlmlocal-site owns verify/apply.

---

## 3. Concrete Integration Steps

### Step 1: Expose RGI tools to rlmlocal-site via MCP

RGI already has `rgi/server.py` with `/analyze`, `/jobs/*`, `/health`. Extend it with an MCP server endpoint.

New RGI tools to expose as MCP:
- `security_scan` — deterministic vulnerability scan.
- `explore_corpus` — sandboxed REPL over file dict.
- `rgi_analyze` — run a full recursive analysis objective.
- `rgi_findings` — retrieve findings for a job.

**Files to change:**
- `rgi/server.py` — add `/mcp` SSE or stdio endpoint.
- `rgi/tools/registry.py` — ensure every tool has a JSON-schema description.

### Step 2: Expose rlmlocal-site engine tools to RGI via HTTP

The engine worker already has `query` RPCs. Wrap them in a small HTTP server or expose them through the existing Tauri dev bridge (`127.0.0.1:1421`) so RGI can call them.

Tools RGI needs from rlmlocal-site:

| RGI Need | rlmlocal Tool | Priority |
|----------|---------------|----------|
| Multi-language structure extraction | `getFileStructure`, `searchSymbols` | High |
| Import/call graph navigation | `getDependencies`, `getDependents`, `resolveCallers` | High |
| File system ops | `listDir`, `readFile`, `findFiles`, `stat` | High |
| Code neighborhood | `fileNeighborhood`, `conceptContextFor` | Medium |
| Git history | `cochangeOf`, `git_cochange` | Medium |
| Live data | `web_search`, `fetch_page` | Medium |
| Verified edits | `verify_patch`, `apply_patch` | Medium |

**Files to change:**
- `rlmlocal-site/src/features/agent/engine.worker.ts` — add HTTP listener or MCP server for RGI-facing queries.
- `rlmlocal-site/src/features/execution/platform.ts` — expose Tauri bridge over HTTP for RGI calls.

### Step 3: Add missing generic tools to RGI

Even before full rlmlocal integration, RGI should grow:

- `list_dir`, `find_files`, `stat`
- `write_file`, `edit_file` (gated, never auto-applied)
- `web_search`, `fetch_page` (via MCP)
- `run_tests` (generic, not Python-only)
- `verify_patch`, `apply_patch` (proxied to Tauri)

These make RGI useful as a standalone kernel for the Tauri sidecar example.

**Files to change:**
- `rgi/tools/browser_ops.py` — list_dir, find_files, stat, read_file with spans.
- `rgi/tools/edit_ops.py` — write_file, edit_file with governance gate.
- `rgi/tools/web_tools.py` — web_search, fetch_page.
- `rgi/tools/tauri_proxy.py` — proxy verify_patch, apply_patch, run_tests to Tauri bridge.
- `rgi/tools/registry.py` — register all new tools.

### Step 4: Unify skills between RGI and rlmlocal-site

Both projects have skill-like concepts. Define a shared skill schema:

```json
{
  "id": "find-callers",
  "description": "Find what calls this symbol",
  "trigger": ["function", "file"],
  "tools": ["resolve_callers"],
  "prompt": "Find callers of {symbol} in {file}"
}
```

- rlmlocal-site skills become templates that can invoke RGI for recursive sub-tasks.
- RGI `recommended_action` / `suggested_subgraphs` map to skill invocations.

**Files to change:**
- New: `rgi/skills/schema.py` and `rgi/skills/loader.py`.
- New: shared skill JSON files in a package both repos can consume.

### Step 5: Tauri sidecar wiring

The existing `tauri-sidecar-example/` shows spawning `python -m rgi server`. Extend it so the Tauri app:

1. Spawns RGI server on a free port.
2. Registers RGI as an MCP server in rlmlocal's engine worker.
3. Forwards RGI `execRequest` calls to the same Tauri commands used by the engine worker.
4. Surfaces RGI findings in the cockpit's "security findings" panel (the `securityFindings` event already exists in `engine.protocol.ts`).

**Files to change:**
- `tauri-sidecar-example/src-tauri/src/lib.rs`
- `tauri-sidecar-example/src/main.ts`
- `rlmlocal-site/src/features/agent/EngineClient.ts` — attach to RGI MCP.

---

## 4. What Brings Immediate Value

### Quick win A: RGI security scanner inside rlmlocal-site

The `securityFindings` event in `engine.protocol.ts:133` is already reserved. Wire RGI's `security_scan` to feed it:

1. User opens project in rlmlocal-site.
2. Background: rlmlocal-site calls RGI `/analyze` with objective `"find security vulnerabilities"`.
3. RGI runs scanner + recursive verification.
4. Findings stream back via `securityFindings` event.
5. Cockpit renders them in a panel; user clicks to navigate to file/line.

This gives rlmlocal-site a vulnerability scanner it doesn't currently have.

### Quick win B: rlmlocal graph queries inside RGI

Replace RGI's shallow `PerceptionLayer` with rlmlocal's graph export. Today RGI has `RlmlocalPerceptionLayer` but it rebuilds the graph from scratch. Instead:

1. rlmlocal-site exports `{nodes, edges}` JSON on demand.
2. RGI imports via `graph_bridge.py`.
3. RGI tools call rlmlocal queries (`getDependencies`, `resolveCallers`, etc.) during recursion.

This immediately fixes RGI's "shallow world model" gap.

### Quick win C: Shared Tauri execution

RGI can propose code fixes; rlmlocal-site already has verify/apply gates. Wire:

1. RGI emits a proposal with `{file, edits}`.
2. rlmlocal-site runs `verify_patch` in shadow.
3. Cockpit shows result; user approves → `apply_patch`.

This lets RGI participate in the safe-change pipeline without duplicating it.

---

## 5. Recommended Build Order

1. **Expose RGI `security_scan` and `rgi_analyze` as MCP tools** (1–2 days).
2. **Attach RGI MCP server to rlmlocal-site engine worker** and render findings (1–2 days).
3. **Add generic file/web tools to RGI** so it can operate without rlmlocal when needed (2–3 days).
4. **Add rlmlocal graph-query HTTP endpoint** and teach RGI to use it instead of rebuilding perception (3–5 days).
5. **Wire RGI proposals through rlmlocal verify/apply gates** (2–3 days).
6. **Extract shared skill schema** and port high-value skills both directions (ongoing).

---

## 6. What Not To Do

1. **Don't merge the codebases.** RGI should stay a Python engine; rlmlocal-site should stay a TypeScript product. Use HTTP/MCP as the seam.
2. **Don't move approval gates into RGI.** rlmlocal-site owns human-in-the-loop writes; RGI proposes.
3. **Don't expose write tools to RGI without governance.** `write_file`/`edit_file` should be gated and never auto-apply.
4. **Don't reimplement rlmlocal's graph in RGI.** Import or query it.
5. **Don't expose Tauri internals directly to RGI.** Always go through the main-thread relay so pairing tokens and security boundaries remain intact.

---

## 7. Bottom Line

rlmlocal-site has built **most of the tooling RGI needs**: rich file/graph tools, verified execution, web tools, skills, and a UI with approval gates. RGI has built **the recursive orchestration and scanner** rlmlocal-site lacks. The integration is mostly wiring, not invention. The highest-ROI first step is exposing RGI's security scanner to rlmlocal-site via MCP and feeding the existing `securityFindings` event — that gives the product a capability it doesn't have today while keeping both codebases separate and clean.
