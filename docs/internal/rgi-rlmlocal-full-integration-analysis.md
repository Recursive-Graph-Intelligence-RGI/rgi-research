# RGI ↔ rlmlocal-site Full Integration Analysis

**Date:** 2026-08-12  
**Goal:** Understand exactly what each project has today, where the seams are, and how to integrate them without breaking rlmlocal-site production.

> **Canonical integration roadmap:** `docs/superpowers/plans/2026-08-12-rgi-rlmlocal-master-integration-roadmap.md`
>  
> This analysis feeds into the master roadmap; use the roadmap for ordering, dependencies, and next actions.

---

## 1. Executive Summary

RGI and rlmlocal-site are two mature but separate halves of the same vision:

- **RGI** (`/home/jeff/projects/rgi`) is a Python recursive-graph intelligence engine: planner, recursive spawn/verify/correct loops, deterministic scanner, governance harness, and a growing HTTP service.
- **rlmlocal-site** (`/home/jeff/projects/rlmlocal-site`) is a TypeScript local-first code assistant with a rich code graph, browser/Tauri runtime, skill-like gates, and a polished workbench UI.

The integration path is **not** to merge the codebases. It is to:

1. Keep rlmlocal-site running exactly as it does today.
2. Add an `RGIEngineClient` adapter inside rlmlocal-site that talks to a local RGI HTTP/MCP server.
3. Port the most valuable rlmlocal graph semantics into RGI's Python perception layer so RGI can also build the graph itself.
4. Wire RGI's recursive engine into rlmlocal's UI through existing event seams (`securityFindings`, `execProposal`, graph canvas).
5. Ship a Tauri desktop app that bundles RGI as a sidecar.

The C2 real-codebase benchmark showed that RGI's orchestration works but its perception substrate is too shallow. rlmlocal-site has the substrate. The integration is therefore the highest-leverage next move.

---

## 2. What rlmlocal-site Has Today

### 2.1 Runtime architecture

| Layer | Files | Responsibility |
|---|---|---|
| UI shell | `src/main.ts` | Chat, file tree, graph canvas, execution console. Currently a 4,262-line god module. |
| Chat surface | `src/features/chat/sendMessage.ts`, `src/features/chat/chatUI.ts` | One-turn chat runner with streaming, trace, history, attachments. |
| Graph UI | `src/features/graphCanvas/graphStore.ts`, `graphCanvas.ts` | Holds `VizPayload` and selection; selection currently has no consumers. |
| Evidence panel | `src/features/viz/evidencePanel.ts`, `cyGraph.ts` | Renders verified graph slices per answer. |
| Engine worker | `src/features/agent/engine.worker.ts` | Web Worker host for `SimpleRLMAgent`. |
| Engine client | `src/features/agent/EngineClient.ts` | Main-thread handle to the worker; implements `IEngine`. |
| Protocol | `src/features/agent/engine.protocol.ts` | Typed main↔worker message contract, including `securityFindings`, `execRequest`, `execProposal`, `execPlan`. |
| Agent | `src/features/agent/SimpleRLMAgent.ts` | 4,115-line monolith: prompt building, tool loops, retrieval, routing, decomposition, graph mutation. |
| Planner | `src/features/agent/planner.ts` | Route classifier (`fast`/`web`/`tool`/`recursive`), not a staged plan/verify/execute spine. |
| Vector store | `src/features/agent/VectorStore.ts` | IndexedDB-backed `VFile` records (content, embedding, structure, version). |
| Graph indexes | `src/features/agent/importGraph.ts`, `dataFlowGraph.ts`, `referenceGraph.ts` | Import/call/data-flow/reference edges rebuilt in-memory from `VFile`. |
| Semantic engine | `src/features/agent/semanticEngine.ts`, `conceptDetector.ts` | Concept communities, coupling, semantic concepts. |
| Execution seam | `src/features/execution/platform.ts`, `execConsole.ts` | `verify_patch` → approve → `apply_patch`, `run_tests`, `resolve_types`, `compute_refactor`, `git_cochange`. |
| Browser toolkit | `src/lib/tools/browserTools.ts` | `listDir`, `readFile`, `grep`, `findFiles`, `writeFile`, `editFile`, `stat`. |
| MCP client | `src/lib/mcp/McpClient.ts`, `mcp.worker.ts` | Connects to MCP servers (web search, weather, stocks, user-added). |
| Tauri backend | `src-tauri/src/lib.rs`, `opencode_host.rs` | Native commands, OpenCode CLI host, SQLite memory. |

### 2.2 Data flow

```
FileSystemDirectoryHandle
  → BrowserToolkit (main thread)
  → VFile records in IndexedDB
  → in-memory import/call/data-flow/reference edges
  → GraphSnapshot
  → SemanticEngine concepts
  → VizPayload
  → graphStore / graphCanvas / evidencePanel
```

### 2.3 Authority split

| Concern | Browser | Backend |
|---|---|---|
| Intent/selection | ✅ | ❌ |
| Skill definitions | ✅ (Markdown) | ❌ |
| File content cache | ✅ IndexedDB | ❌ |
| Embeddings | ✅ IndexedDB | ❌ |
| Real file writes | ❌ | ✅ Tauri |
| Tests/lint/type | ❌ | ✅ Tauri |
| Execution traces | ❌ raw | ✅ SQLite |

### 2.4 Architecture inventory confirmation

A fresh read of the `rlmlocal-site` source tree (see `agent-122` output) confirms the runtime shape above and adds detail:

- `src/features/agent/engineWiring.ts` is the single place that decides worker vs. main-thread execution.
- `src/features/agent/engine.worker.ts` reconstructs the full brain inside a Web Worker: LLM provider, `SimpleRLMAgent`, `BrowserToolkit`, `VectorStore`, `McpClient`s, and the Tauri exec relay.
- `src/features/agent/EngineClient.ts` is the main-thread `IEngine` proxy; it implements crash recovery by respawning the worker.
- `src/features/chat/sendMessage.ts` owns the one-turn chat runner; it streams tokens into the answer bubble and merges the verified `VizPayload` into `graphStore`.
- `src/features/execution/platform.ts` abstracts native operations, dynamic-importing `@tauri-apps/api/core` only inside Tauri and falling back to a dev HTTP bridge on `127.0.0.1:1421` otherwise.
- The Tauri backend (`src-tauri/src/lib.rs`) hosts OpenCode on port `4097`, file-change watching, shadow worktrees, and a SQLite trace DB.

### 2.5 Key architectural problems already identified

From the July 2026 audits:

- `main.ts` is a 4,262-line god module.
- All actions inject text into `chatInput` instead of dispatching typed `SkillInvocation` events.
- `graphStore` is passive: selection changes drive nothing.
- No real `SkillRegistry`/`SkillRuntime`; gates are prompt-regex-driven.
- `SimpleRLMAgent` is a 4,115-line monolith.
- Two graph renderers for the same `VizPayload`.
- Multiple overlapping graph representations with no canonical model.
- `evidencePanel.ts` statically imports `cyGraph.ts`, defeating lazy loading.
- Chat history stores full `VizPayload` slices in `localStorage`.

These are **rlmlocal-site-internal** problems. RGI integration should not be blocked by them, but it should not make them worse.

---

## 3. What RGI Has Today

### 3.1 Core engine

| Layer | Files | Responsibility |
|---|---|---|
| Engine loop | `rgi/core/engine.py` | Five-phase execution: activation, node execution, recursive spawning, verification/consolidation, learning. |
| Harness | `rgi/core/harness.py` | Safety kernel: depth, node, LLM call, time caps; governance gate; audit log. |
| Models | `rgi/core/models.py` | `CognitiveGraph`, `CognitiveNode`, `CognitiveEdge`, loop types, node states. |
| Spawn search | `rgi/core/spawn_search.py` | v1 adaptive action selection over `stop`, `execution_sweep`, `verify_tool`, `repl_explore`, `frontier_arbitrate`. |
| Governance | `rgi/core/governance.py` | `LocalGate`; `FortSignalGate` is a stub. |
| Audit | `rgi/core/audit.py` | JSONL audit trail. |
| Context builder | `rgi/core/context_builder.py` | Builds LLM context from graph state. |
| Findings | `rgi/core/findings.py` | Finding normalization, deduplication, compilation. |

### 3.2 Perception

| Layer | Files | Responsibility |
|---|---|---|
| Default parser | `rgi/perception/code_parser.py` | Shallow Python AST parsing. |
| rlmlocal compat | `rgi/perception/rlmlocal_compat/structure_extractor.py` | Tree-sitter extraction for Python/JS/Go/Rust. |
| Import graph | `rgi/perception/rlmlocal_compat/import_graph.py` | Import edges for Python only. |
| Graph bridge | `rgi/perception/rlmlocal_compat/graph_bridge.py` | Imports a rlmlocal-style JSON snapshot into a `CognitiveGraph`. |
| rlmlocal layer | `rgi/perception/rlmlocal_perception.py` | Builds a `CognitiveGraph` from extracted structures. |

### 3.3 Tools

`rgi/tools/registry.py` registers:

- `parse_python_file`
- `grep_security_patterns`
- `check_jwt_usage`
- `find_hardcoded_secrets`
- `explore_corpus` (sandboxed REPL)
- `read_file`, `grep`, `callers`
- `run_py_compile`, `run_pytest`, `run_pyflakes`
- `security_scan` (deterministic scanner)

Missing compared to rlmlocal-site:

- `list_dir`, `find_files`, `stat`
- `write_file`, `edit_file` (gated)
- `web_search`, `fetch_page`
- `verify_patch`, `apply_patch`
- `run_tests` for non-Python projects
- Multi-language structure extraction beyond Python

### 3.4 Reasoning and memory

| Layer | Files | Responsibility |
|---|---|---|
| LLM client | `rgi/reasoning/llm_client.py` | Ollama/Anthropic/cloud providers + deterministic mock. |
| Frontier integration | `rgi/reasoning/frontier_integration.py` | Frontier plan/arbitrate/synthesize hooks. |
| Activation | `rgi/memory/activation.py` | Embedding + keyword activation. |
| Embeddings | `rgi/reasoning/embeddings.py` | OpenAI-compatible embedding client. |

### 3.5 Server / CLI

| Layer | Files | Responsibility |
|---|---|---|
| CLI | `rgi/cli.py` | `analyze`, `compare`, `eval`, `server` commands. |
| HTTP server | `rgi/server.py` | `/health`, `/analyze`, `/jobs/{id}/status`, `/jobs/{id}/result`, `/shutdown`. |
| Sidecar example | `tauri-sidecar-example/` | Minimal Tauri app spawning RGI and polling results. |

---

## 4. Existing Integration Plans — Summary and Contradictions

### 4.1 Documents reviewed

- `docs/internal/2026-08-10-rgi-rlmlocal-integration-strategy.md`
- `docs/internal/rgi-rlmlocal-tool-integration-plan.md`
- `docs/internal/rgi-cognitive-runtime-strategy.md`
- `docs/superpowers/specs/2026-08-10-rgi-engine-language-and-tauri-integration-design.md`
- `docs/superpowers/specs/2026-08-10-rgi-unified-desktop-os-design.md`
- `docs/superpowers/specs/2026-08-10-rgi-os-governance-integration-strategy.md`
- `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md`
- `docs/superpowers/specs/2026-08-11-rgi-hybrid-local-frontier-integration-design.md`
- `/home/jeff/projects/rlmlocal-site/memory/MASTER-ALIGNMENT-PLAN-2026-07-17.md`
- `/home/jeff/projects/rlmlocal-site/memory/REFINED-SKILLS-ARCHITECTURE-PLAN-2026-07-17.md`
- `/home/jeff/projects/rlmlocal-site/memory/ARCHITECTURE-ALIGNMENT-AUDIT-2026-07-17.md`
- `/home/jeff/projects/rlmlocal-site/memory/BACKEND-SKILLS-HOME-AUDIT-2026-07-17.md`

### 4.2 Main claims

| Doc | Main Claim |
|---|---|
| `rgi-rlmlocal-integration-strategy.md` | RGI orchestration should run on top of rlmlocal's graph substrate. Choose Model A (port concepts to Python) or Model C (shared graph spec). Do **not** choose Model B unless sunsetting RGI. |
| `rgi-rlmlocal-tool-integration-plan.md` | Dual MCP/HTTP exposure: each tool lives in one runtime and is callable from the other. Don't merge codebases. Approval gates stay in rlmlocal-site. |
| `rgi-cognitive-runtime-strategy.md` | Three-layer runtime: rlmlocal substrate, RGI orchestration, fortmemory durable memory. Phase 1 is fixing RGI's own reasoning quality; Phase 2 consumes rlmlocal's graph. |
| `engine-language-and-tauri-integration-design.md` | Keep RGI Python. Use Tauri Rust shell to spawn RGI as a local HTTP service. |
| `rgi-unified-desktop-os-design.md` | v0.3 ships as a single installable desktop app: Tauri + RGI Python engine. rlmlocal.com PWA stays lightweight. Do not modify rlmlocal-site in place. |
| `rgi-v0.3-engine-perception-port.md` | Port `languagePacks.ts`, `StructureExtractor.ts`, `importGraph.ts` into `rgi/perception/rlmlocal_compat/`. Do not touch rlmlocal-site. |
| `rgi-hybrid-local-frontier-integration-design.md` | Use local models for constrained work, frontier models for synthesis. Configurable via env. |

### 4.3 Contradictions / tensions

1. **Product split.** The unified desktop OS doc says RGI Desktop is the primary product and rlmlocal.com PWA stays lightweight. The tool integration plan treats rlmlocal-site cockpit as the UI that consumes RGI. Both can coexist, but v0.3 prioritization is ambiguous.
2. **Code modification.** The perception-port doc and tool integration plan explicitly say **do not modify rlmlocal-site**. The unified desktop OS doc says a future step will copy the sidecar pattern into `rlmlocal-site/src-tauri` and retire the TS agent stack on desktop.
3. **Integration model.** The strategy doc recommends Model A/C. The tool integration plan effectively uses Model C semantics but with MCP/HTTP coupling that blurs the boundary.
4. **Auth.** FortSignal passkey auth is mentioned in the desktop OS doc but endpoints, credentials, and WebAuthn mechanism are unspecified.

### 4.4 Resolution

For v0.3, the safest path that satisfies all docs is:

- **Model C with a Model A port inside RGI.** RGI Python grows its own tree-sitter-based graph builder (continuing the perception port), while also being able to import a rlmlocal JSON snapshot via `graph_bridge.py`.
- **rlmlocal-site gets an adapter, not a rewrite.** A new `RGIEngineClient` implements the existing `IEngine` interface and forwards to a local RGI server. Existing `EngineClient`/`SimpleRLMAgent` paths remain untouched.
- **Tauri desktop app is a separate product shell** built from the sidecar example, reusing rlmlocal UI components where possible, but not requiring changes to rlmlocal-site production code.

---

## 5. Gap Analysis

### 5.1 Perception / graph substrate

| Gap | Impact | Owner |
|---|---|---|
| RGI only has import edges for Python; no call/data-flow/reference edges | Cannot trace cross-file vulnerability chains | RGI |
| RGI perception has no persistent `VFile`-style cache | Re-ingests on every run; no freshness healing | RGI |
| RGI embeddings activation is keyword/embedding-only; no symbol/concept layer | Misses relevant symbols; spawns broad, low-quality subgraphs | RGI |
| rlmlocal graph is in-memory in the browser; not easily exported | RGI cannot consume it without a new export endpoint | rlmlocal adapter |

### 5.2 Tools

| Gap | Impact | Owner |
|---|---|---|
| No `list_dir`, `find_files`, `stat` in RGI | REPL and subgraphs cannot navigate file system generically | RGI |
| No `write_file`/`edit_file` in RGI | Cannot propose code fixes | RGI (gated) |
| No `verify_patch`/`apply_patch` in RGI | Cannot participate in safe-change pipeline | RGI (proxy to Tauri) |
| No web search/fetch in RGI | Cannot answer questions requiring live data | RGI (via MCP) |
| `callers` in RGI uses import edges only | Misses intra-file and dynamic calls | RGI |

### 5.3 Skills / orchestration

| Gap | Impact | Owner |
|---|---|---|
| rlmlocal-site has no `SkillRegistry`/`SkillRuntime` | Cannot express RGI actions as first-class skills | rlmlocal-site |
| RGI has no skill abstraction | Cannot consume rlmlocal skill definitions | RGI |
| RGI spawn objectives are often broad | Local models produce vague findings | RGI prompt engineering |

### 5.4 UI / product

| Gap | Impact | Owner |
|---|---|---|
| rlmlocal chat is chat-first, not graph-first | Graph cannot drive actions | rlmlocal-site |
| `graphStore` selection has no consumers | Node selection does nothing | rlmlocal-site |
| No progress streaming from RGI into rlmlocal UI | Long analyses feel frozen | Adapter + UI |

### 5.5 Governance / packaging

| Gap | Impact | Owner |
|---|---|---|
| FortSignal integration unspecified | Cannot ship authenticated desktop app | Tauri / auth service |
| Python runtime bundling unspecified | End users may need system Python | Packaging |
| Audit trail ownership split | Rust shell vs Python engine logs may diverge | Design decision |

---

## 6. rlmlocal-site Chat UI Diagnosis

User report: "the chat part doesn't work too well."

### 6.1 Message flow

```
chatInput keydown
  → chatUI.send()
  → main.ts onSend(text)
  → runSendMessage(deps)
  → agent.chat(message, onThinking, onToken, onFilesRead, onSlicePlan, options)
  → EngineClient.chat() → postMessage to engine.worker.ts
  → engine.worker.ts handleChat() → agent.chat()
  → SimpleRLMAgent.chat()
  ← thinking/token/filesRead/slicePlan/result events
  ← render answer bubble
```

### 6.2 Root-cause diagnosis (agent-123)

A focused trace of the chat path found concrete runtime/async integration bugs. TypeScript compiles clean and unit tests pass; the failures happen at runtime.

| # | Bug | Location | Impact |
|---|---|---|---|
| 1 | SkillRuntime chat is **non-streaming and non-abortable** | `src/features/skills/SkillRuntime.ts:128-141` | Toolbar skill invocations run silently; UI looks frozen until the answer pops in, and cannot be cancelled. |
| 2 | Abort signals are **swallowed by the toolkit layer** | `src/features/agent/SimpleRLMAgent.ts:2924` (`addFactBlock`) | Cancelling during `readFile`/`listDir`/`grep` returns an error-shaped string instead of stopping; the tool loop continues. |
| 3 | Worker abort can be **lost when signal is already aborted** | `src/features/agent/EngineClient.ts:301-305` | The abort is posted before the worker registers the `reqId`, so rapid send/abort creates zombie chats that stream into stale DOM. |
| 4 | In-chat aborts are mapped to `error`, not `[cancelled]` | `src/features/agent/engine.worker.ts:546` | Cancellation is inconsistent; the UI must special-case `AbortError` instead of receiving a uniform cancelled result. |
| 5 | In-flight chats race with agent rebuild/dispose | `src/main.ts:1886-1888`, `src/features/agent/engineWiring.ts:196-199` | Model/folder switch rejects the active turn with "engine disposed" / "worker crashed" and can leave input locked. |
| 6 | `sendMessage` mishandles the `'[cancelled]'` return value | `src/features/chat/sendMessage.ts:392-407` | Pre-aborted chats leave an empty agent bubble instead of rendering the cancelled hint. |
| 7 | Old chat promises are not awaited on new send | `src/features/chat/sendMessage.ts:322-325` | Tokens from the cancelled turn can still append to DOM elements below the new turn, duplicating output. |

Secondary findings:

- `engine.worker.ts:74` silently swallows MCP attach failures, so missing web tools never surface.
- `EngineClient.handleCrash` rejects pending promises but does not emit a dedicated reconnecting event.
- `chatUI.ts:87` uses `void opts.onSend(text)`; any sync throw before the first `await` is unhandled.
- The event bus and worker message protocol are structurally sound; missed events are not the primary cause.

### 6.3 Recommended fixes (independent of RGI integration)

1. **Stream skill chats**: change `SkillRuntime.runEngineChat` to proxy `onThinking`/`onToken` and a `signal`, or emit progress events on `appEvents`.
2. **Respect abort in toolkit calls**: rethrow `AbortError` in `SimpleRLMAgent.addFactBlock` instead of stringifying it.
3. **Make worker abort reliable**: in `EngineClient.request`, reject immediately when `signal.aborted` is true rather than posting a doomed abort message.
4. **Normalize cancellation in the worker**: in `engine.worker.ts:handleChat`, catch `AbortError` and post `{ kind: 'result', reqId, content: '[cancelled]' }`.
5. **Serialize chat vs rebuild**: before disposing/rebuilding the worker, await or forcibly cancel in-flight chats and clear the UI lock.
6. **Handle `[cancelled]` explicitly in sendMessage**: treat the returned string the same as an `AbortError` — show the cancelled hint and skip history.
7. **Await cleanup on new send**: track the in-flight chat promise and `await` it after aborting, or gate sends so only one turn runs at a time.

---

## 7. Risks and Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| rlmlocal-site parser/semantics are imperfect (acknowledged) | Medium | Port only mature, well-tested modules; keep rlmlocal's graph as the authoritative source where possible. |
| Graph interchange format drift | Medium | Version the snapshot schema; start with a minimal subset (nodes + edges + content + embeddings). |
| RGI local-model precision collapse on real OSS | High | Phase 1: mandatory verification gate, narrower objectives, better dedup. |
| Tauri packaging complexity | Medium | Start with dev-mode Python path; bundle later. |
| FortSignal auth not specified | High | Treat as Phase 2; ship v0.3 without cloud auth or with a simple token. |
| rlmlocal-site internal refactor distracts integration | High | Do not refactor rlmlocal-site for RGI; add adapter only. |

### Open questions

1. Should RGI's perception be tree-sitter based (like rlmlocal) or stay Python-AST based?  
   **Answer:** Tree-sitter, because rlmlocal already proved it works for multi-language codebases.
2. How should findings be verified against source code?  
   **Answer:** RGI's existing `verify_findings` reads cited file/line; enhance it with rlmlocal's `readFile`/`callers`.
3. What is the minimal graph interchange spec?  
   **Answer:** See the adapter design doc.
4. Should the desktop app bundle Python or require system Python?  
   **Answer:** Bundle for consumers; allow `RGI_PYTHON_PATH` override for dev.
5. Does rlmlocal-site PWA ever talk to RGI, or only the desktop app?  
   **Answer:** PWA can talk to a local RGI server if the user runs it; desktop app bundles it.

---

## 8. Recommended Next Steps

1. **Finalize this analysis and the adapter design doc.** (`docs/superpowers/specs/2026-08-12-rgi-rlmlocal-adapter-design.md`)
2. **Implement the RGI HTTP/SSE adapter in rlmlocal-site.** Add `RGIEngineClient` behind a feature flag.
3. **Expose RGI `security_scan` as the first integrated skill.** Feed the existing `securityFindings` event.
4. **Port call/data-flow/reference graphs into RGI Python.** Extend `rgi/perception/rlmlocal_compat/`.
5. **Add generic file tools to RGI** (`list_dir`, `find_files`, `stat`, gated `read_file`).
6. **Wire RGI proposals through rlmlocal's `execProposal` flow.** `verify_patch` → approve → `apply_patch`.
7. **Package the Tauri sidecar example into a real desktop app.**
8. **Re-run C2 benchmark** with the new perception substrate to measure recall/precision improvement.
