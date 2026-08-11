# RGI Engine Language and Tauri Integration Design

**Date:** 2026-08-10  
**Context:** C2 real-codebase benchmark complete for 1.5b and 4b; 7b matrix partial. The engine is currently Python. rlmlocal-site (the product frontend) is a TypeScript/Vite app with an existing `src-tauri/` Tauri shell.

## Decision

Keep the RGI cognitive engine in **Python**. Integrate it with the Tauri/TypeScript frontend via a **local HTTP/gRPC service spawned by a Rust sidecar**.

Do not rewrite the engine in Rust while the research program is still active.

## Rationale

### Why Python stays the right choice for the engine

1. **LLM/ML ecosystem.** Local LLM clients (ollama, llama-cpp-python), embedding servers, and AST/static-analysis tooling are first-class in Python. Re-implementing adapters in Rust would be re plumbing, not research.
2. **Research velocity.** The graph-spawning hypothesis is still being proven. Python allows fast iteration on planner prompts, spawn rules, activation functions, and perception parsers. Rust would turn every experiment into a compile-and-ship cycle.
3. **The C2 bottleneck is not Python CPU time.** The slowest cell (4b R4_pygoat, 1072 s) spent its time waiting on local LLM and embedding inference. Profiling would not show Python as the dominant cost.
4. **Team expertise.** The existing RGI codebase, tests, and benchmark harness are already Python. A rewrite would discard working, verified code.

### When Rust is the right tool

Rust belongs in the **shell/integration layer**, not the cognitive engine:

- Process spawning and lifecycle management for the Python engine.
- Native file-system watchers, secure sandboxing, and OS-level permissions.
- IPC between the webview and the engine.
- Packaging a single installable desktop binary that bundles the Python runtime.

## Proposed architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Tauri desktop app                                          │
│  ┌──────────────┐    invoke/commands     ┌──────────────┐   │
│  │  Webview     │  ←──────────────────→  │  Rust host   │   │
│  │  TS/Vite     │                        │  src-tauri/  │   │
│  └──────────────┘                        └──────┬───────┘   │
└─────────────────────────────────────────────────┼───────────┘
                                                  │ spawns
                                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  Python RGI engine (localhost service)                      │
│  - HTTP or gRPC API                                         │
│  - accepts repo path                                        │
│  - streams progress / graph updates                         │
│  - returns final report + graph artifact                    │
└─────────────────────────────────────────────────────────────┘
```

### Interface sketch

Rust sidecar exposes to the frontend:

```typescript
// Tauri command wrapper
await invoke("analyze_repo", { path: "/path/to/repo", model: "qwen2.5:7b" });
await invoke("engine_status");           // is the Python service running?
await invoke("kill_engine");             // force terminate
```

Python engine exposes:

```python
POST /analyze              # start analysis, return job_id
GET  /jobs/{id}/status     # polling or SSE stream
GET  /jobs/{id}/result     # final report + topology JSON
POST /shutdown             # graceful exit
```

### Deployment options

| deployment | integration |
|---|---|
| Local desktop (primary) | Tauri + bundled Python engine |
| Cloud/rlmlocal-site | Same Python engine as a long-running service behind Cloudflare Workers / durable objects |
| CI/batch | Direct CLI invocation of `python -m rgi` |

The engine itself is unchanged across all three; only the transport layer differs.

## Alternatives considered

| approach | verdict |
|---|---|
| Full Rust rewrite of RGI engine | Rejected. High cost, low research payoff, ecosystem gaps for LLM/embeddings. |
| Hybrid Rust graph core + Python adapters | Rejected. The graph engine is not CPU-bound; splitting it adds FFI complexity without a measured need. |
| Python engine + HTTP API + Tauri sidecar | Accepted. Balances research velocity with a polished desktop product shell. |

## Open questions for v0.3

1. Should the IPC use HTTP/REST, gRPC, or Unix-domain sockets?
2. How is the Python runtime bundled for distribution (`pyinstaller`, `uv` standalone, or system Python)?
3. Does FortSignal governance enforce policies in the Rust shell, the Python engine, or both?

## Next step

Proceed with v0.3 perception work in Python. Parallel track: scaffold the Tauri sidecar that can spawn and talk to the Python engine. Do not block research on a Rust rewrite.
