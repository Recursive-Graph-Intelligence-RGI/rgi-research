# RGI ↔ rlmlocal-site Adapter Design & Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Canonical integration roadmap:** `docs/superpowers/plans/2026-08-12-rgi-rlmlocal-master-integration-roadmap.md`

**Goal:** Connect the RGI Python recursive-graph engine to the rlmlocal-site TypeScript workbench without modifying rlmlocal-site's production code path, using a feature-flagged HTTP/SSE adapter, a shared graph snapshot schema, and a phased migration that keeps both projects shippable.

**Architecture:** rlmlocal-site continues to run its existing `SimpleRLMAgent` / worker stack. A new `RGIEngineClient` implements the same `IEngine` interface and forwards to a local RGI HTTP server. RGI accepts either a filesystem path (desktop/Tauri sidecar) or a JSON graph snapshot exported from rlmlocal-site (PWA), builds/merges a `CognitiveGraph`, and streams progress back via SSE. Over time, RGI's Python perception layer grows the call/data-flow/reference graphs that rlmlocal-site already has, so RGI can also warm itself directly from a folder.

**Tech Stack:** Python 3.11+, aiohttp, Pydantic, tree-sitter, TypeScript, Vite, Tauri (later), HTTP/SSE, JSON graph snapshots.

## Global Constraints

- **Do not modify rlmlocal-site's default engine path.** The `SimpleRLMAgent` / `EngineClient` stack stays the default; RGI is opt-in via a feature flag.
- **RGI stays Python.** Do not rewrite the engine in TypeScript or Rust.
- **Production safety:** no remote code execution, no unapproved file writes, no breaking schema changes without versioning.
- **All new network surfaces are local-only** (`127.0.0.1` by default) unless explicitly enabled.
- **Graph snapshots are versioned.** The adapter rejects unknown snapshot versions.
- **Every new tool must declare permissions** (`read`, `write`, `exec`) in the `ToolRegistry`.
- **Windows/macOS/Linux parity** for the desktop sidecar path; PWA path stays browser-only.

---

## 1. Current State Summary

### 1.1 RGI today

| Layer | Key files | State |
|---|---|---|
| Engine loop | `rgi/core/engine.py`, `harness.py`, `models.py` | Recursive spawn/verify/correct loops, governance harness, audit log. |
| Perception | `rgi/perception/code_parser.py`, `rlmlocal_compat/*` | Python-only import edges; tree-sitter structure extractor exists; `graph_bridge.py` imports rlmlocal snapshots. |
| Tools | `rgi/tools/registry.py` | `security_scan`, `read_file`, `grep`, `callers`, REPL, pytest/pyflakes. Missing generic filesystem and patch tools. |
| Server | `rgi/server.py` | `/health`, `/analyze`, `/jobs/{id}/status`, `/jobs/{id}/result`. No SSE, no snapshot ingest, no chat. |
| Frontier | `rgi/reasoning/frontier_integration.py` | Optional frontier synthesis via env config. |

### 1.2 rlmlocal-site today

| Layer | Key files | State |
|---|---|---|
| UI shell | `src/main.ts` | 4,000+ line bootstrap; mounts chat, graph canvas, exec console. |
| Chat | `src/features/chat/sendMessage.ts`, `chatUI.ts` | Streaming chat runner with known abort/race bugs (see §8). |
| Engine worker | `src/features/agent/engine.worker.ts`, `EngineClient.ts` | Web Worker brain; `EngineClient` implements `IEngine`. |
| Protocol | `src/features/agent/engine.protocol.ts` | Typed main↔worker contract with `securityFindings`, `execRequest`, `execProposal`. |
| Graph | `src/features/agent/importGraph.ts`, `dataFlowGraph.ts`, `referenceGraph.ts` | Multi-language import/call/data-flow/reference edges. |
| Execution | `src/features/execution/platform.ts` | Tauri/dev-bridge seam for `verify_patch`, `apply_patch`, `run_tests`. |

### 1.3 Why integrate now

- RGI's C2 benchmark showed orchestration works but perception is too shallow for real codebases.
- rlmlocal-site has the deep, multi-language graph substrate RGI lacks.
- Both projects share the same long-term goal: a recursive, graph-first local AI workbench.
- The safest path is an adapter, not a merge.

---

## 2. Integration Boundary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ rlmlocal-site UI (browser or Tauri)                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────────────┐ │
│  │ chatUI       │  │ graphCanvas  │  │ execConsole / verify-approve-land  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┬─────────────────────┘ │
│         │                 │                         │                       │
│  ┌──────▼─────────────────▼─────────────────────────▼──────┐               │
│  │         IEngine  (engine.protocol.ts)                   │               │
│  │  ┌─────────────────┐        ┌──────────────────────┐    │               │
│  │  │ EngineClient    │ default│ RGIEngineClient      │    │               │
│  │  │ (worker agent)  │◄──────►│ (HTTP/SSE adapter)   │    │               │
│  │  └─────────────────┘        └──────────┬───────────┘    │               │
│  └────────────────────────────────────────┼────────────────┘               │
└───────────────────────────────────────────┼────────────────────────────────┘
                                            │ HTTP/SSE 127.0.0.1:8787
┌───────────────────────────────────────────▼────────────────────────────────┐
│ RGI Python server (rgi/server.py)                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────────────┐ │
│  │ /v1/snapshot│  │ /v1/chat     │  │ /v1/security-scan                  │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────────┬─────────────────────┘ │
│         │                │                         │                       │
│  ┌──────▼────────────────▼─────────────────────────▼──────┐               │
│  │            ProjectStore + CognitiveGraph                │               │
│  └─────────────────────────────────────────────────────────┘               │
│  ┌─────────────────────────────────────────────────────────┐               │
│  │  RGI engine (spawn/verify/correct) + ToolRegistry       │               │
│  └─────────────────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Graph Interchange Schema (Model C)

RGI and rlmlocal-site exchange a **versioned JSON graph snapshot**. RGI's `graph_bridge.py` already consumes this shape; the adapter standardizes it.

### 3.1 Snapshot envelope

```json
{
  "version": "rgi-graph-snapshot-v1",
  "project_id": "my-project",
  "project_name": "My Project",
  "generated_at": "2026-08-12T05:00:00Z",
  "nodes": [...],
  "edges": [...]
}
```

### 3.2 Node schema

```typescript
interface GraphNode {
  id: string;                    // stable, globally unique
  kind: 'file' | 'dir' | 'function' | 'class' | 'method' | 'concept' | 'key' | 'route' | 'symbol';
  label: string;                 // display label
  name?: string;                 // symbol name
  path?: string;                 // file path, relative to project root
  line?: number;                 // 1-based line number
  span?: { start: number; end: number };
  content?: string;              // capped source snippet (≤8 KB default)
  embedding?: number[];          // optional vector for activation
  version?: number;              // freshness sequence
  symbols?: string[];            // child symbol ids
  language?: string;             // 'python' | 'typescript' | 'javascript' | 'go' | 'rust'
}
```

### 3.3 Edge schema

```typescript
interface GraphEdge {
  id: string;
  kind: 'import' | 'call' | 'dataFlow' | 'reference' | 'coChange' | 'contains' | 'depends';
  source: string;                // node id
  target: string;                // node id
  label?: string;
  line?: number;
  snippet?: string;              // grounded evidence
  weight?: number;               // 0.0–1.0
  confidence?: number;           // 0.0–1.0
  verified?: boolean;            // true if confirmed by both ends
}
```

### 3.4 Validation rules

- `version` must be exactly `"rgi-graph-snapshot-v1"`.
- Every `edge.source` and `edge.target` must exist in `nodes`.
- `embedding` length must be consistent across nodes (RGI ignores mismatches but logs a warning).
- File paths are relative; absolute paths are rejected for security.

### 3.5 Example minimal snapshot

```json
{
  "version": "rgi-graph-snapshot-v1",
  "project_id": "sample_project",
  "project_name": "sample_project",
  "generated_at": "2026-08-12T05:00:00Z",
  "nodes": [
    { "id": "f:auth.py", "kind": "file", "label": "auth.py", "path": "auth.py" },
    { "id": "fn:login", "kind": "function", "label": "login", "path": "auth.py", "line": 12, "name": "login" }
  ],
  "edges": [
    { "id": "e:1", "kind": "contains", "source": "f:auth.py", "target": "fn:login", "line": 12 }
  ]
}
```

---

## 4. HTTP API Contract

Base URL: `http://127.0.0.1:8787` (default). All endpoints return JSON unless SSE.

### 4.1 `GET /health`

Response:

```json
{ "status": "ok", "version": "0.3.0", "providers": ["ollama"] }
```

### 4.2 `POST /v1/projects/{project_id}/snapshot`

Create or update a project from a graph snapshot.

Request body: the snapshot JSON (see §3).

Response:

```json
{
  "project_id": "my-project",
  "status": "imported",
  "nodes": 142,
  "edges": 389
}
```

### 4.3 `POST /v1/projects/{project_id}/chat`

Start a chat turn. Returns an SSE stream.

Request body:

```json
{
  "message": "Find the SQL injection in auth.py",
  "scope": { "level": "file", "file": "auth.py", "breadcrumb": ["auth.py"] },
  "options": { "max_llm_calls": 20, "max_total_nodes": 50 }
}
```

SSE event format (each line is `data: <json>\n\n`):

```json
{ "kind": "thinking", "step": "planning" }
{ "kind": "filesRead", "paths": ["auth.py", "session.py"] }
{ "kind": "securityFindings", "findings": [{"kind":"sql_injection","file":"auth.py","line":34}] }
{ "kind": "token", "token": "The " }
{ "kind": "result", "content": "The query at auth.py:34 uses f-string interpolation..." }
```

Error events:

```json
{ "kind": "error", "message": "project not found" }
```

### 4.4 `POST /v1/projects/{project_id}/security-scan`

Run the deterministic scanner and stream findings via SSE.

Request body:

```json
{ "path": "/optional/override/path" }
```

SSE events:

```json
{ "kind": "thinking", "step": "security_scan_started" }
{ "kind": "securityFindings", "findings": [...] }
{ "kind": "result", "content": "Found 3 issues." }
```

### 4.5 `POST /v1/projects/{project_id}/exec-result`

Relay the result of a native execution operation from the UI/runtime back to RGI.

Request body:

```json
{
  "opId": 1,
  "ok": true,
  "value": { "passed": true, "output": "..." },
  "error": null
}
```

Response:

```json
{ "status": "received" }
```

### 4.6 `GET /v1/projects/{project_id}/status`

Response:

```json
{
  "project_id": "my-project",
  "status": "ready",
  "nodes": 142,
  "edges": 389,
  "last_activity": "2026-08-12T05:01:00Z"
}
```

### 4.7 `POST /v1/shutdown`

Graceful shutdown.

Response:

```json
{ "status": "shutting_down" }
```

---

## 5. rlmlocal-site Adapter Design

### 5.1 `RGIEngineClient.ts`

A new file at `rlmlocal-site/src/features/agent/RGIEngineClient.ts` implements `IEngine`. It is a drop-in alternative to `EngineClient`.

Key responsibilities:

- Maintain `project_id`, `baseUrl`, and an `AbortController` per chat.
- Translate `IEngine.chat()` into an SSE `POST /v1/projects/{id}/chat` request.
- Emit `thinking`, `token`, `filesRead`, `slicePlan`, and `securityFindings` callbacks.
- Stub `execRequest` forwarding until Phase 3.
- Stub non-chat methods (`warmUp`, `getDependencies`, etc.) with snapshot-based or HTTP-based implementations in later phases.

### 5.2 Feature flag

Opt-in via `localStorage`:

```typescript
const useRgi = localStorage.getItem('rgi-adapter-enabled') === '1';
const rgiBaseUrl = localStorage.getItem('rgi-base-url') || 'http://127.0.0.1:8787';
```

`engineWiring.ts` chooses `RGIEngineClient` when the flag is set and the server is reachable; otherwise falls back to the existing worker path.

### 5.3 Mode matrix

| Mode | How RGI is started | How project is loaded |
|---|---|---|
| PWA + user runs RGI manually | User launches `python -m rgi server` | rlmlocal-site exports snapshot to `/v1/snapshot` |
| Tauri desktop sidecar | Tauri spawns RGI Python binary | sidecar passes project path; RGI warms from disk |
| Dev (both repos open) | `python -m rgi server` in RGI repo | snapshot export or shared filesystem path |

---

## 6. RGI Server Extensions

### 6.1 New modules

- `rgi/api/project_store.py` — in-memory project registry keyed by `project_id`.
- `rgi/api/snapshot.py` — snapshot validation and import into `CognitiveGraph`.
- `rgi/api/sse.py` — SSE streaming helpers.
- `rgi/api/security_stream.py` — deterministic scanner streaming.
- `rgi/api/chat_stream.py` — chat-turn streaming wrapper around the engine.
- `rgi/tools/filesystem.py` — generic `list_dir`, `find_files`, `stat`.
- `rgi/tools/patch.py` — gated `verify_patch` / `apply_patch` (Phase 3).

### 6.2 Server route additions

Add to `rgi/server.py`:

- `GET /v1/projects/{project_id}/status`
- `POST /v1/projects/{project_id}/snapshot`
- `POST /v1/projects/{project_id}/chat`
- `POST /v1/projects/{project_id}/security-scan`
- `POST /v1/projects/{project_id}/exec-result`

Keep the existing `/analyze`, `/jobs/*`, `/health`, `/shutdown` routes unchanged.

---

## 7. Phased Migration Plan

### Phase 0 — RGI Hardening (pre-adapter)

**Goal:** Fix known blockers so the engine produces reliable output when the adapter connects it to rlmlocal-site.

#### Task 0.1: Fix the `finding` prompt/schema mismatch

**Files:**
- Modify: `rgi/core/engine.py` (where `SYSTEM_PROMPT` is built)
- Modify: `rgi/core/findings.py` (`normalize_finding`)
- Test: `tests/test_findings.py`

**Problem:** The `SYSTEM_PROMPT` currently tells the model to emit `finding` as a string, but the pipeline expects a structured dict (`kind`, `file`, `line`, `detail`).

**Interfaces:**
- Consumes: existing `normalize_finding(finding)`.
- Produces: system prompt fragment describing the finding dict schema; `normalize_finding` string-to-dict fallback.

- [ ] **Step 1: Add a string-to-dict fallback in `normalize_finding`**

```python
# rgi/core/findings.py
def normalize_finding(finding: Any) -> dict | None:
    if finding is None:
        return None
    if isinstance(finding, str):
        # Best-effort parse: "kind at file:line - detail"
        import re
        m = re.match(r"^(?P<kind>\w+)\s+at\s+(?P<file>[^:]+):(?P<line>\d+)\s*-\s*(?P<detail>.+)$", finding.strip())
        if m:
            return {
                "kind": m.group("kind"),
                "file": m.group("file"),
                "line": int(m.group("line")),
                "detail": m.group("detail"),
                "confidence": 0.5,
            }
        return {"kind": "note", "detail": finding, "confidence": 0.3}
    if isinstance(finding, dict):
        required = {"kind", "detail"}
        if not required.issubset(finding):
            return None
        return {**finding, "confidence": finding.get("confidence", 0.5)}
    return None
```

- [ ] **Step 2: Update the system prompt to emit a dict**

```python
# rgi/core/engine.py (wherever SYSTEM_PROMPT is assembled)
FINDING_SCHEMA = """
When you report a concrete issue, emit a finding as a JSON object with exactly these keys:
{
  "kind": "sql_injection|hardcoded_secret|jwt_weakness|path_traversal|weak_crypto|command_injection|plaintext_password|session_without_timeout|other",
  "file": "relative/path/to/file.py",
  "line": 42,
  "symbol": "function_or_variable_name",
  "detail": "one-sentence explanation",
  "confidence": 0.85,
  "severity": "critical|high|medium|low"
}
Do not emit the finding as a plain string.
"""
```

- [ ] **Step 3: Run the findings test suite**

```bash
pytest tests/test_findings.py -v
```

Expected: all tests pass; add new cases for string fallback.

- [ ] **Step 4: Commit**

```bash
git add rgi/core/findings.py rgi/core/engine.py tests/test_findings.py
git commit -m "fix: align finding prompt schema with normalize_finding"
```

#### Task 0.2: Tune convergence for real codebases

**Files:**
- Modify: `rgi/cli.py` (default `max_iterations` / `confidence_threshold`)
- Test: `tests/test_baseline.py` or a new benchmark run

**Interfaces:**
- Consumes: env vars `RGI_MAX_ITERATIONS`, `RGI_CONFIDENCE_THRESHOLD`.
- Produces: looser defaults for large codebases.

- [ ] **Step 1: Make defaults size-aware**

```python
# rgi/cli.py inside run_analysis()
import os
from pathlib import Path

file_count = len(list(Path(path).rglob("*.py"))) if Path(path).is_dir() else 1
max_iterations = int(os.environ.get("RGI_MAX_ITERATIONS", "12" if file_count > 20 else "8"))
confidence_threshold = float(os.environ.get("RGI_CONFIDENCE_THRESHOLD", "0.65" if file_count > 20 else "0.75"))
```

- [ ] **Step 2: Run C2 benchmark**

```bash
python -m rgi analyze benchmarks/vuln_app_2 --objective "Find security vulnerabilities" --provider ollama --model qwen2.5:7b
```

Expected: at least one more R3 completion than the previous run.

- [ ] **Step 3: Commit**

```bash
git add rgi/cli.py
git commit -m "feat: size-aware convergence defaults for large codebases"
```

---

### Phase 1 — Adapter Skeleton

**Goal:** rlmlocal-site can toggle RGI on and see `security_scan` findings in the chat UI.

#### Task 1.1: Add project store and snapshot endpoint

**Files:**
- Create: `rgi/api/project_store.py`
- Create: `rgi/api/snapshot.py`
- Modify: `rgi/server.py`
- Test: `tests/test_snapshot_endpoint.py`

**Interfaces:**
- Consumes: `import_rlmlocal_graph` from `rgi/perception/rlmlocal_compat/graph_bridge.py`.
- Produces: `POST /v1/projects/{project_id}/snapshot` returns import stats.

- [ ] **Step 1: Create project store**

```python
# rgi/api/project_store.py
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from rgi.core.models import CognitiveGraph


@dataclass
class Project:
    project_id: str
    graph: CognitiveGraph
    path: Optional[str] = None
    last_activity: float = field(default_factory=lambda: __import__("time").time())


class ProjectStore:
    def __init__(self) -> None:
        self._projects: Dict[str, Project] = {}

    def create(self, project_id: str, graph: CognitiveGraph, path: Optional[str] = None) -> Project:
        project = Project(project_id=project_id, graph=graph, path=path)
        self._projects[project_id] = project
        return project

    def get(self, project_id: str) -> Optional[Project]:
        project = self._projects.get(project_id)
        if project is not None:
            project.last_activity = __import__("time").time()
        return project

    def delete(self, project_id: str) -> bool:
        return self._projects.pop(project_id, None) is not None

    def list_ids(self) -> list[str]:
        return list(self._projects.keys())


STORE = ProjectStore()
```

- [ ] **Step 2: Add snapshot validation and import**

```python
# rgi/api/snapshot.py
import json
from pathlib import Path
from typing import Any

from rgi.api.project_store import STORE, Project
from rgi.core.models import CognitiveGraph, CognitiveNode, CognitiveEdge, GraphPolicy, GraphState, LoopType, NodeType


SNAPSHOT_VERSION = "rgi-graph-snapshot-v1"
VALID_EDGE_KINDS = {"dependency", "flow", "feedback", "triggers", "verifies", "activates", "contains", "imports"}


def _map_edge_kind(kind: str) -> str:
    mapping = {
        "import": "imports",
        "call": "flow",
        "dataFlow": "flow",
        "reference": "dependency",
        "coChange": "feedback",
        "contains": "contains",
        "depends": "dependency",
    }
    return mapping.get(kind, "dependency")


def import_snapshot(data: dict[str, Any], project_id: str, path: str | None = None) -> Project:
    if data.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported snapshot version: {data.get('version')!r}")

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_ids = {n["id"] for n in nodes if "id" in n}

    graph = CognitiveGraph(
        loop_type=LoopType.KNOWLEDGE,
        state=GraphState(objective=f"Imported snapshot for {project_id}"),
        policy=GraphPolicy(auto_spawn=False, require_verification=False),
    )

    for n in nodes:
        node_id = n.get("id")
        if not node_id:
            continue
        content = n.get("content") or f"{n.get('kind', 'entity')} {n.get('label', '')}".strip()
        graph.nodes[node_id] = CognitiveNode(
            id=node_id,
            type=NodeType.MEMORY,
            content=content,
            confidence=float(n.get("confidence", 1.0)),
            parent_graph_id=graph.id,
            metadata={
                "kind": n.get("kind"),
                "label": n.get("label"),
                "name": n.get("name"),
                "file": n.get("path"),
                "line": n.get("line"),
                "span": n.get("span"),
                "language": n.get("language"),
                "embedding": n.get("embedding"),
            },
        )

    for e in edges:
        source = e.get("source")
        target = e.get("target")
        if source not in node_ids or target not in node_ids:
            continue
        kind = _map_edge_kind(e.get("kind", "dependency"))
        graph.edges.append(
            CognitiveEdge(
                source=source,
                target=target,
                edge_type=kind,
                weight=float(e.get("weight", 0.9)),
                metadata={
                    "original_kind": e.get("kind"),
                    "line": e.get("line"),
                    "snippet": e.get("snippet"),
                    "verified": e.get("verified"),
                },
            )
        )

    return STORE.create(project_id, graph, path=path)
```

- [ ] **Step 3: Wire snapshot endpoint into server**

```python
# rgi/server.py additions inside RGIServer._make_app()
app.router.add_post("/v1/projects/{project_id}/snapshot", self.snapshot)
app.router.add_get("/v1/projects/{project_id}/status", self.project_status)
app.router.add_post("/v1/projects/{project_id}/security-scan", self.security_scan)
app.router.add_post("/v1/projects/{project_id}/chat", self.chat)
app.router.add_post("/v1/projects/{project_id}/exec-result", self.exec_result)

# Add __init__ import
from rgi.api.project_store import STORE, ProjectStore
from rgi.api.snapshot import import_snapshot

# And these methods:
async def snapshot(self, request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)
    project_id = request.match_info["project_id"]
    try:
        project = import_snapshot(data, project_id)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    return web.json_response({
        "project_id": project_id,
        "status": "imported",
        "nodes": len(project.graph.nodes),
        "edges": len(project.graph.edges),
    })

async def project_status(self, request: web.Request) -> web.Response:
    project = STORE.get(request.match_info["project_id"])
    if project is None:
        return web.json_response({"error": "project_not_found"}, status=404)
    return web.json_response({
        "project_id": project.project_id,
        "status": "ready",
        "nodes": len(project.graph.nodes),
        "edges": len(project.graph.edges),
        "last_activity": project.last_activity,
    })

async def exec_result(self, request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)
    project_id = request.match_info["project_id"]
    project = STORE.get(project_id)
    if project is None:
        return web.json_response({"error": "project_not_found"}, status=404)
    # Store the result where the active chat stream can pick it up.
    pending = project.graph.memory_snapshot.setdefault("pending_exec_results", {})
    pending[body.get("opId")] = body
    return web.json_response({"status": "received"})
```

- [ ] **Step 4: Test**

```python
# tests/test_snapshot_endpoint.py
import pytest
from rgi.server import RGIServer


@pytest.fixture
def client():
    server = RGIServer(host="127.0.0.1", port=0)
    app = server._make_app()
    return app


async def test_snapshot_import(aiohttp_client, client):
    cli = await aiohttp_client(client)
    payload = {
        "version": "rgi-graph-snapshot-v1",
        "project_id": "test",
        "nodes": [{"id": "a", "kind": "file", "label": "a.py"}],
        "edges": [],
    }
    resp = await cli.post("/v1/projects/test/snapshot", json=payload)
    assert resp.status == 200
    body = await resp.json()
    assert body["nodes"] == 1
```

Run:

```bash
pytest tests/test_snapshot_endpoint.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rgi/api/ rgi/server.py tests/test_snapshot_endpoint.py
git commit -m "feat(api): project store and snapshot ingest endpoint"
```

#### Task 1.2: Add SSE streaming helpers

**Files:**
- Create: `rgi/api/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Produces: `EventStreamResponse` context manager that yields JSON-serializable events.

- [ ] **Step 1: Implement SSE helper**

```python
# rgi/api/sse.py
import json
from typing import Any, AsyncGenerator

from aiohttp import web


async def event_stream(request: web.Request, generator: AsyncGenerator[dict[str, Any], None]) -> web.StreamResponse:
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)
    async for event in generator:
        payload = json.dumps(event)
        await response.write(f"data: {payload}\n\n".encode("utf-8"))
    await response.write("data: [DONE]\n\n".encode("utf-8"))
    await response.write_eof()
    return response
```

- [ ] **Step 2: Test**

```python
# tests/test_sse.py
import pytest
from rgi.api.sse import event_stream


async def _gen():
    yield {"kind": "token", "token": "hi"}


async def test_sse_writes_event(aiohttp_client):
    from aiohttp import web
    app = web.Application()
    app.router.add_get("/stream", lambda r: event_stream(r, _gen()))
    cli = await aiohttp_client(app)
    resp = await cli.get("/stream")
    assert resp.status == 200
    text = await resp.text()
    assert 'data: {"kind": "token", "token": "hi"}' in text
```

Run:

```bash
pytest tests/test_sse.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add rgi/api/sse.py tests/test_sse.py
git commit -m "feat(api): reusable SSE event stream helper"
```

#### Task 1.3: Add `/v1/projects/{id}/chat` SSE endpoint

**Files:**
- Create: `rgi/api/chat_stream.py`
- Modify: `rgi/server.py`
- Test: `tests/test_chat_stream.py`

**Interfaces:**
- Consumes: `run_analysis` from `rgi.cli`.
- Produces: SSE `thinking`, `filesRead`, `securityFindings`, `token`, `result`, `error` events.

- [ ] **Step 1: Implement chat stream wrapper**

```python
# rgi/api/chat_stream.py
import json
import tempfile
from pathlib import Path
from typing import AsyncGenerator

from rgi.api.project_store import STORE
from rgi.cli import run_analysis


async def chat_stream(project_id: str, message: str, options: dict | None = None) -> AsyncGenerator[dict, None]:
    project = STORE.get(project_id)
    if project is None:
        yield {"kind": "error", "message": "project not found"}
        return

    path = project.path
    if path is None:
        yield {"kind": "error", "message": "project has no filesystem path"}
        return

    yield {"kind": "thinking", "step": "planning"}
    try:
        output_path = Path(tempfile.gettempdir()) / f"rgi_chat_{project_id}.json"
        report = await run_analysis(
            path=path,
            objective=message,
            output=str(output_path),
            mock=False,
            provider="ollama",
            model=None,
            max_llm_calls=int((options or {}).get("max_llm_calls", 20)),
            max_total_nodes=int((options or {}).get("max_total_nodes", 50)),
        )
    except Exception as exc:
        yield {"kind": "error", "message": str(exc)}
        return

    for finding in report.get("findings", []):
        if finding.get("file"):
            yield {"kind": "securityFindings", "findings": [finding]}
    summary = report.get("summary")
    if not summary:
        summary = f"Completed analysis. Findings: {len(report.get('findings', []))}."
    yield {"kind": "result", "content": summary}
```

- [ ] **Step 2: Wire endpoint**

```python
# rgi/server.py
from rgi.api.chat_stream import chat_stream

async def chat(self, request: web.Request) -> web.StreamResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "invalid_json"}, status=400)
    project_id = request.match_info["project_id"]
    return await event_stream(
        request,
        chat_stream(project_id, body.get("message", ""), body.get("options")),
    )
```

- [ ] **Step 3: Test**

```python
# tests/test_chat_stream.py
import pytest
from rgi.server import RGIServer


async def test_chat_requires_project(aiohttp_client):
    server = RGIServer(host="127.0.0.1", port=0)
    cli = await aiohttp_client(server._make_app())
    resp = await cli.post("/v1/projects/missing/chat", json={"message": "hi"})
    assert resp.status == 200
    text = await resp.text()
    assert "project not found" in text
```

Run:

```bash
pytest tests/test_chat_stream.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add rgi/api/chat_stream.py rgi/server.py tests/test_chat_stream.py
git commit -m "feat(api): SSE chat endpoint"
```

#### Task 1.4: Add `/v1/projects/{id}/security-scan` endpoint

**Files:**
- Create: `rgi/api/security_stream.py`
- Modify: `rgi/server.py`
- Test: `tests/test_security_stream.py`

**Interfaces:**
- Consumes: `run_security_scan` from `rgi.tools.security_scan`.
- Produces: SSE `securityFindings` events.

- [ ] **Step 1: Implement streaming scanner**

```python
# rgi/api/security_stream.py
from pathlib import Path
from typing import AsyncGenerator

from rgi.api.project_store import STORE
from rgi.tools.security_scan import run_security_scan


async def security_scan_stream(project_id: str, override_path: str | None = None) -> AsyncGenerator[dict, None]:
    project = STORE.get(project_id)
    if project is None:
        yield {"kind": "error", "message": "project not found"}
        return

    path = override_path or project.path
    if path is None:
        yield {"kind": "error", "message": "project has no filesystem path"}
        return

    yield {"kind": "thinking", "step": "security_scan_started"}
    findings = run_security_scan(path)
    if findings:
        yield {"kind": "securityFindings", "findings": findings}
    yield {"kind": "result", "content": f"Found {len(findings)} issue(s)."}
```

- [ ] **Step 2: Wire endpoint**

```python
# rgi/server.py
from rgi.api.security_stream import security_scan_stream
from rgi.api.sse import event_stream

async def security_scan(self, request: web.Request) -> web.StreamResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    project_id = request.match_info["project_id"]
    return await event_stream(request, security_scan_stream(project_id, body.get("path")))
```

- [ ] **Step 3: Test**

```python
# tests/test_security_stream.py
import pytest
from pathlib import Path
from rgi.server import RGIServer


async def test_security_scan_finds_hardcoded_secret(aiohttp_client, tmp_path):
    p = tmp_path / "secret.py"
    p.write_text("API_KEY = 'supersecret123456'\n")
    server = RGIServer(host="127.0.0.1", port=0)
    server.store = server.store  # use default store
    from rgi.api.project_store import STORE
    from rgi.api.snapshot import import_snapshot
    import_snapshot({"version": "rgi-graph-snapshot-v1", "nodes": [], "edges": []}, "sec", path=str(tmp_path))
    cli = await aiohttp_client(server._make_app())
    resp = await cli.post("/v1/projects/sec/security-scan", json={})
    assert resp.status == 200
    text = await resp.text()
    assert "hardcoded_secret" in text
```

Run:

```bash
pytest tests/test_security_stream.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add rgi/api/security_stream.py rgi/server.py tests/test_security_stream.py
git commit -m "feat(api): streaming security-scan endpoint"
```

#### Task 1.5: Add generic filesystem tools

**Files:**
- Create: `rgi/tools/filesystem.py`
- Modify: `rgi/tools/registry.py`
- Test: `tests/test_filesystem_tools.py`

**Interfaces:**
- Produces: `list_dir`, `find_files`, `stat` tools registered in `ToolRegistry`.

- [ ] **Step 1: Implement tools**

```python
# rgi/tools/filesystem.py
import fnmatch
from pathlib import Path


def list_dir(params: dict) -> dict:
    root = Path(params["path"])
    if not root.is_dir():
        return {"error": f"not a directory: {root}", "entries": []}
    entries = []
    for child in sorted(root.iterdir()):
        entries.append({
            "name": child.name,
            "kind": "dir" if child.is_dir() else "file",
            "path": str(child),
        })
    return {"entries": entries}


def find_files(params: dict) -> dict:
    root = Path(params["root"])
    pattern = params.get("pattern", "*")
    results = []
    for p in root.rglob(pattern):
        if p.is_file():
            results.append(str(p))
    return {"files": sorted(results)}


def stat_file(params: dict) -> dict:
    p = Path(params["path"])
    if not p.exists():
        return {"error": f"not found: {p}"}
    return {
        "path": str(p),
        "exists": True,
        "size": p.stat().st_size,
        "is_dir": p.is_dir(),
        "is_file": p.is_file(),
    }
```

- [ ] **Step 2: Register them**

```python
# rgi/tools/registry.py — add to _LOCAL_TOOLS list
from rgi.tools.filesystem import list_dir, find_files, stat_file

_LOCAL_TOOLS.extend([
    Tool(
        name="list_dir",
        description="List files and directories under a path.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=list_dir,
    ),
    Tool(
        name="find_files",
        description="Recursively find files matching a glob pattern.",
        input_schema={"type": "object", "properties": {"root": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["root"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=find_files,
    ),
    Tool(
        name="stat",
        description="Return metadata for a file or directory.",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        domain="local",
        permissions={"read"},
        handler=stat_file,
    ),
])
```

- [ ] **Step 3: Test**

```python
# tests/test_filesystem_tools.py
from rgi.tools.filesystem import list_dir, find_files, stat_file


def test_list_dir(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "sub").mkdir()
    result = list_dir({"path": str(tmp_path)})
    names = {e["name"] for e in result["entries"]}
    assert "a.py" in names
    assert "sub" in names
```

Run:

```bash
pytest tests/test_filesystem_tools.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add rgi/tools/filesystem.py rgi/tools/registry.py tests/test_filesystem_tools.py
git commit -m "feat(tools): generic filesystem tools for REPL navigation"
```

#### Task 1.6: Create `RGIEngineClient.ts`

**Files:**
- Create: `rlmlocal-site/src/features/agent/RGIEngineClient.ts`
- Test: `rlmlocal-site/src/features/agent/__tests__/RGIEngineClient.test.ts` (or equivalent)

**Interfaces:**
- Consumes: `IEngine` from `engine.protocol.ts`, `ExecArgs`/`ExecProposal` from `execution/platform.ts`.
- Produces: an `IEngine` implementation that POSTs to `/v1/projects/{id}/chat` and reads SSE.

- [ ] **Step 1: Implement the client**

```typescript
// rlmlocal-site/src/features/agent/RGIEngineClient.ts
import type { IEngine, ProviderConfig, TurnScope, VizPayload } from './engine.protocol';
import type { ExecProposal, ExecPlan } from '../execution/platform';

export interface RGIClientOptions {
  projectId: string;
  baseUrl: string;
  projectPath?: string;
  snapshot?: unknown;
}

export class RGIEngineClient implements IEngine {
  readonly kind = 'worker' as const;
  _warmedUp = false;
  vectorStore = {
    remove: async () => true,
    clear: async () => true,
    getDependencies: () => [] as string[],
    getDependents: () => [] as string[],
  };

  private projectId: string;
  private baseUrl: string;
  private projectPath?: string;
  private snapshot?: unknown;
  private controller: AbortController | null = null;
  private findingsHandler?: (findings: any) => void;

  constructor(opts: RGIClientOptions) {
    this.projectId = opts.projectId;
    this.baseUrl = opts.baseUrl.replace(/\/$/, '');
    this.projectPath = opts.projectPath;
    this.snapshot = opts.snapshot;
  }

  async warmUp(onProgress?: (msg: string) => void): Promise<void> {
    if (this.snapshot) {
      const resp = await fetch(`${this.baseUrl}/v1/projects/${encodeURIComponent(this.projectId)}/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.snapshot),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || 'snapshot import failed');
      onProgress?.(`imported ${body.nodes} nodes, ${body.edges} edges`);
    }
    this._warmedUp = true;
  }

  chat(
    message: string,
    onThinking?: (step: string) => void,
    onToken?: (token: string) => void,
    onFilesRead?: (paths: string[]) => void,
    onSlicePlan?: (payload: VizPayload) => void,
    options?: { signal?: AbortSignal; forceDeep?: boolean; forceDeeper?: boolean; openFile?: string | null },
  ): Promise<string> {
    this.controller = new AbortController();
    const signal = options?.signal;
    if (signal) {
      signal.addEventListener('abort', () => this.controller?.abort(), { once: true });
    }

    return fetch(`${this.baseUrl}/v1/projects/${encodeURIComponent(this.projectId)}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, options }),
      signal: this.controller.signal,
    }).then(async (resp) => {
      if (!resp.body) throw new Error('no response body');
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let final = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const event = this._parseSSE(line);
          if (!event) continue;
          if (event.kind === 'thinking') onThinking?.(event.step);
          else if (event.kind === 'token') onToken?.(event.token);
          else if (event.kind === 'filesRead') onFilesRead?.(event.paths);
          else if (event.kind === 'slicePlan') onSlicePlan?.(event.payload);
          else if (event.kind === 'securityFindings') this.findingsHandler?.(event.findings);
          else if (event.kind === 'result') {
            final = event.content || '';
          } else if (event.kind === 'error') {
            throw new Error(event.message);
          }
        }
      }
      return final;
    });
  }

  private _parseSSE(line: string): any | null {
    const trimmed = line.trim();
    if (!trimmed.startsWith('data: ')) return null;
    const payload = trimmed.slice(6);
    if (payload === '[DONE]') return null;
    try {
      return JSON.parse(payload);
    } catch {
      return null;
    }
  }

  setSecurityFindingsHandler(fn: (findings: any) => void): void {
    this.findingsHandler = fn;
  }

  abort(): void {
    this.controller?.abort();
  }

  // IEngine shims — Phase 2/3 fill these in
  getDependencies() { return []; }
  getDependents() { return []; }
  setRecursive() {}
  setContextSize() {}
  setCurrentOpenFile() {}
  addMcpClient() {}
  ingestUploadedFiles() { return Promise.resolve(0); }
}
```

- [ ] **Step 2: Add a unit test**

```typescript
// rlmlocal-site/src/features/agent/__tests__/RGIEngineClient.test.ts
import { describe, it, expect, vi } from 'vitest';
import { RGIEngineClient } from '../RGIEngineClient';

describe('RGIEngineClient.parseSSE', () => {
  it('parses a valid SSE data line', () => {
    const client = new RGIEngineClient({ projectId: 'p', baseUrl: 'http://localhost:8787' });
    // @ts-expect-error private method
    expect(client._parseSSE('data: {"kind":"token","token":"hi"}')).toEqual({ kind: 'token', token: 'hi' });
  });
});
```

Run:

```bash
cd /home/jeff/projects/rlmlocal-site && npm test -- RGIEngineClient.test.ts
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/jeff/projects/rlmlocal-site
git add src/features/agent/RGIEngineClient.ts src/features/agent/__tests__/RGIEngineClient.test.ts
git commit -m "feat(agent): RGI HTTP/SSE adapter client"
```

#### Task 1.7: Wire feature flag in `engineWiring.ts`

**Files:**
- Modify: `rlmlocal-site/src/features/agent/engineWiring.ts`
- Modify: `rlmlocal-site/src/main.ts` (read feature flag and pass to wiring)

**Interfaces:**
- Consumes: `RGIEngineClient`, `buildEngineWorkerClient`, `buildMainThreadAgent`.
- Produces: `createEngine` chooses adapter when flag is set.

- [ ] **Step 1: Modify engineWiring**

```typescript
// rlmlocal-site/src/features/agent/engineWiring.ts
import { RGIEngineClient } from './RGIEngineClient';

export interface EngineWiringOptions {
  provider: ProviderConfig;
  rootHandle?: FileSystemDirectoryHandle;
  fileTree?: Array<{ name: string; kind: string; children?: any[] }>;
  rgiAdapter?: { enabled: boolean; baseUrl: string; projectId: string; snapshot?: unknown };
}

export async function createEngine(opts: EngineWiringOptions) {
  if (opts.rgiAdapter?.enabled) {
    const client = new RGIEngineClient({
      projectId: opts.rgiAdapter.projectId,
      baseUrl: opts.rgiAdapter.baseUrl,
      snapshot: opts.rgiAdapter.snapshot,
    });
    await client.warmUp();
    return client;
  }
  // existing default path
  return buildEngineWorkerClient(opts.provider, opts.rootHandle);
}
```

- [ ] **Step 2: Read flag in main.ts**

```typescript
// rlmlocal-site/src/main.ts near engine construction
const rgiEnabled = localStorage.getItem('rgi-adapter-enabled') === '1';
const rgiBaseUrl = localStorage.getItem('rgi-base-url') || 'http://127.0.0.1:8787';
const rgiAdapter = rgiEnabled
  ? { enabled: true, baseUrl: rgiBaseUrl, projectId: projectName, snapshot: undefined }
  : undefined;
const engine = await createEngine({ provider, rootHandle, fileTree, rgiAdapter });
```

- [ ] **Step 3: Commit**

```bash
cd /home/jeff/projects/rlmlocal-site
git add src/features/agent/engineWiring.ts src/main.ts
git commit -m "feat(agent): feature-flagged RGI adapter wiring"
```

#### Task 1.8: Surface `securityFindings` in chat UI

**Files:**
- Modify: `rlmlocal-site/src/features/chat/sendMessage.ts`
- Modify: `rlmlocal-site/src/main.ts` (install findings handler)

**Interfaces:**
- Consumes: `RGIEngineClient.setSecurityFindingsHandler`.
- Produces: findings rendered as a warning card above the answer bubble.

- [ ] **Step 1: Install handler in main.ts**

```typescript
// rlmlocal-site/src/main.ts after engine creation
if ((engine as any).setSecurityFindingsHandler) {
  (engine as any).setSecurityFindingsHandler((findings: any[]) => {
    appEvents.dispatchEvent(new CustomEvent('security.findings', { detail: findings }));
  });
}
```

- [ ] **Step 2: Render findings card in sendMessage**

```typescript
// rlmlocal-site/src/features/chat/sendMessage.ts
appEvents.addEventListener('security.findings', ((e: CustomEvent) => {
  const findings: any[] = e.detail;
  const card = document.createElement('div');
  card.className = 'rgi-security-card p-3 rounded border-l-4 border-red-500 bg-red-50 text-red-900 mb-2';
  card.innerHTML = `<strong>Security findings (${findings.length})</strong><ul class="list-disc pl-5 mt-1">` +
    findings.map(f => `<li>${f.kind} at ${f.file}:${f.line} — ${f.detail}</li>`).join('') +
    '</ul>';
  chatAPI.appendElement(card);
}) as EventListener);
```

- [ ] **Step 3: Commit**

```bash
cd /home/jeff/projects/rlmlocal-site
git add src/features/chat/sendMessage.ts src/main.ts
git commit -m "feat(chat): render RGI security findings card"
```

#### Task 1.9: Integration smoke test

- [ ] **Step 1: Start RGI server**

```bash
cd /home/jeff/projects/rgi
python -m rgi server --port 8787
```

- [ ] **Step 2: Enable adapter in rlmlocal-site**

Open the browser dev console on `http://localhost:5173` (or the Tauri dev window) and run:

```javascript
localStorage.setItem('rgi-adapter-enabled', '1');
location.reload();
```

- [ ] **Step 3: Load a Python project and ask**

```text
Run a security scan on this project.
```

Expected: a red findings card appears listing grounded vulnerabilities.

- [ ] **Step 4: Regression check**

Disable the flag:

```javascript
localStorage.removeItem('rgi-adapter-enabled');
location.reload();
```

Expected: original worker engine still works.

---

### Phase 2 — Graph Port

**Goal:** RGI can warm itself from a folder using the same multi-language graph semantics rlmlocal-site has, and rlmlocal-site can optionally export a richer snapshot.

#### Task 2.1: Port call/data-flow/reference graphs to Python

**Files:**
- Create: `rgi/perception/rlmlocal_compat/call_graph.py`
- Create: `rgi/perception/rlmlocal_compat/data_flow_graph.py`
- Create: `rgi/perception/rlmlocal_compat/reference_graph.py`
- Modify: `rgi/perception/rlmlocal_perception.py`
- Test: `tests/test_rlmlocal_call_graph.py`, etc.

**Approach:** Reimplement the algorithms from `rlmlocal-site/src/features/agent/importGraph.ts`, `dataFlowGraph.ts`, and `referenceGraph.ts` in Python using tree-sitter. Keep the node/edge output compatible with the snapshot schema.

#### Task 2.2: Snapshot export from rlmlocal-site

**Files:**
- Create: `rlmlocal-site/src/features/agent/exportSnapshot.ts`
- Modify: `rlmlocal-site/src/features/agent/engineWiring.ts` to pass snapshot to `RGIEngineClient`

**Approach:** Walk `VectorStore` and the in-memory graph indexes to produce a `rgi-graph-snapshot-v1` JSON object.

#### Task 2.3: RGI `warmUp` from folder path

**Files:**
- Modify: `rgi/api/project_store.py` to accept `path` on creation.
- Modify: `rgi/api/snapshot.py` to optionally run the new perception layer when no snapshot body is provided.
- Modify: `RGIEngineClient.ts` to send `projectPath` when available.

**Success criterion:** Loading a project in the Tauri sidecar triggers RGI's own multi-language graph builder and produces a snapshot-compatible graph.

---

### Phase 3 — Execution Loop

**Goal:** RGI can propose code changes that flow through rlmlocal-site's existing `verify_patch` → approve → `apply_patch` pipeline.

#### Task 3.1: Add gated `write_file`/`edit_file` tools to RGI

**Files:**
- Create: `rgi/tools/patch.py`
- Modify: `rgi/tools/registry.py`

**Approach:** Tools build `{search, replace}` hunks but do **not** touch disk. They return a proposal payload.

#### Task 3.2: Proxy `execRequest` to rlmlocal platform

**Files:**
- Modify: `rlmlocal-site/src/features/agent/RGIEngineClient.ts`
- Modify: `rgi/server.py` (`exec_result` method already added in Phase 1)
- Modify: `rlmlocal-site/src/features/execution/platform.ts` if new op kinds are needed.

**Interfaces:**
- Consumes: `execRequest` SSE event, `platform.run_tests`/`verify_patch`/`apply_patch`.
- Produces: `POST /v1/projects/{id}/exec-result` with the op outcome.

- [ ] **Step 1: Add exec relay to `RGIEngineClient.ts`**

```typescript
// inside RGIEngineClient class
import { runTests, verifyPatch, applyPatch } from '../execution/platform';

private execRequestHandler?: (req: any) => Promise<any>;

private async _handleExecRequest(event: any): Promise<void> {
  const op = event.op;
  const args = event.args;
  let ok = false;
  let value: unknown = null;
  let error: string | null = null;
  try {
    if (op === 'run_tests') {
      value = await runTests(args.projectPath, args.file);
    } else if (op === 'verify_patch') {
      value = await verifyPatch(args.projectPath, args.file, args.edits);
    } else if (op === 'apply_patch') {
      value = await applyPatch(args.projectPath, args.file, args.edits, args.message);
    } else {
      throw new Error(`unsupported exec op: ${op}`);
    }
    ok = true;
  } catch (exc) {
    error = String(exc);
  }
  await fetch(`${this.baseUrl}/v1/projects/${encodeURIComponent(this.projectId)}/exec-result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opId: event.opId, ok, value, error }),
  });
}

setExecRequestHandler(fn: (req: any) => Promise<any>): void {
  this.execRequestHandler = fn;
}
```

- [ ] **Step 2: Dispatch `execRequest` in the SSE loop**

In the `chat()` SSE loop, add:

```typescript
else if (event.kind === 'execRequest') {
  await this._handleExecRequest(event);
}
```

- [ ] **Step 3: Commit**

```bash
cd /home/jeff/projects/rlmlocal-site
git add src/features/agent/RGIEngineClient.ts
git commit -m "feat(agent): relay execRequest from RGI to platform"
```

#### Task 3.3: Surface `execProposal` in exec console

**Files:**
- Modify: `rlmlocal-site/src/features/execution/execConsole.ts`

**Approach:** Reuse the existing proposal card rendering; RGI proposals use the same `ExecProposal` shape.

---

### Phase 4 — Desktop Packaging

**Goal:** Ship a Tauri desktop app that bundles RGI as a sidecar.

#### Task 4.1: Sidecar spawn from Tauri

**Files:**
- Modify: `rgi/tauri-sidecar-example/src-tauri/src/lib.rs`

**Approach:** Use `tauri::api::process::Command` to spawn `rgi-server` (the packaged Python binary) on app start, kill it on exit.

#### Task 4.2: Bundle Python runtime

**Options (pick one in a dedicated spike):**

1. **PyInstaller** — freeze `rgi` + dependencies into one executable.
2. **uv standalone** — ship a Python toolchain and RGI source, install deps on first run.
3. **System Python fallback** — smallest bundle; require user to install Python 3.11+.

**Recommendation:** Start with option 3 for dev velocity, move to option 1 before public release.

#### Task 4.3: Pass project path from Tauri to RGI

**Files:**
- Modify: Tauri Rust commands to expose a folder picker and return the path.
- Modify: `RGIEngineClient.ts` to use `projectPath` instead of snapshot export when running under Tauri.

---

## 8. rlmlocal-site Chat UI Diagnosis

The full diagnosis is in `docs/internal/rgi-rlmlocal-full-integration-analysis.md`. The headline issues that affect RGI integration are:

1. **SkillRuntime chat is non-streaming/non-abortable** — skill invocations look frozen.
2. **Toolkit abort signals are swallowed** — cancelling while a tool runs does not stop the loop.
3. **Worker abort races** — rapid send/abort can spawn zombie chats.
4. **Agent rebuild races** — folder/model switch can kill an active turn.
5. **`[cancelled]` return value mishandled** — empty bubble on pre-aborted chats.

**Impact on RGI adapter:** because `RGIEngineClient` uses `fetch` + `AbortController`, it can avoid the worker abort bugs entirely, but it must still play nicely with `sendMessage.ts`'s locking and cleanup. The adapter should therefore:

- Always unlock the input in a `finally` block.
- Treat adapter/network errors as recoverable hints, not fatal crashes.
- Not rely on `SimpleRLMAgent` semantics for cancellation.

---

## 9. Risks and Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| rlmlocal-site parser/semantics are imperfect (acknowledged) | Medium | Port only mature modules; keep rlmlocal's graph authoritative where possible. |
| Graph interchange format drift | Medium | Version the snapshot schema; reject unknown versions. |
| RGI local-model precision collapse on real OSS | High | Phase 0 convergence tuning + mandatory verification gate. |
| Tauri packaging complexity | Medium | Dev-mode Python path first; bundle later. |
| FortSignal auth not specified | High | Phase 4; ship v0.3 without cloud auth or with a simple token. |
| rlmlocal-site internal refactor distracts integration | High | Adapter only; do not refactor main.ts for RGI. |

### Open questions

1. **SSE vs long-polling?** SSE is chosen for low latency and simple browser support. If Tauri/Rust consumers prefer WebSocket, add a `/v1/projects/{id}/chat/ws` variant later.
2. **How does the PWA export snapshots without killing performance?** Export should be incremental and debounced; full export only on explicit "Sync to RGI" action.
3. **Do we keep the existing `/analyze` endpoint?** Yes, unchanged; it is the batch benchmark entry point. The new endpoints are for interactive adapter use.
4. **What is the auth model for the desktop app?** Deferred to Phase 4. Options: none for local-only, simple token, or FortSignal passkey.

---

## 10. Success Criteria

- [ ] `localStorage.setItem('rgi-adapter-enabled','1')` routes chat to RGI without breaking the default path.
- [ ] `POST /v1/projects/{id}/snapshot` imports rlmlocal snapshots and reports node/edge counts.
- [ ] `POST /v1/projects/{id}/security-scan` streams grounded findings to the rlmlocal chat UI.
- [ ] Generic filesystem tools (`list_dir`, `find_files`, `stat`) are registered and tested.
- [ ] Existing C2 benchmark still passes (or improves) after Phase 0 changes.
- [ ] No production code in rlmlocal-site is modified unless the feature flag is enabled.

---

## 11. Document Map

- `docs/internal/rgi-rlmlocal-full-integration-analysis.md` — current state, gap analysis, chat UI diagnosis.
- `docs/superpowers/specs/2026-08-10-rgi-engine-language-and-tauri-integration-design.md` — why RGI stays Python and how Tauri hosts it.
- `docs/superpowers/specs/2026-08-10-rgi-unified-desktop-os-design.md` — v0.3 desktop OS vision.
- `docs/superpowers/specs/2026-08-11-rgi-hybrid-local-frontier-integration-design.md` — local + frontier model strategy.
- `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md` — porting rlmlocal graph semantics into RGI.
- **This document** — adapter contract, HTTP API, graph schema, and phased migration plan.
