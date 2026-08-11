# RGI OS and FortSignal Governance Integration Strategy

**Date:** 2026-08-10  
**Status:** Decision record  
**Related docs:**
- `docs/architecture.md`
- `docs/vision.md`
- `docs/superpowers/specs/2026-08-10-rgi-engine-language-and-tauri-integration-design.md`
- `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md`

## Decision

Build the **RGI OS shell first**, with **FortSignal governance as its kernel** — not as two separate products.

The user-facing product is a local-first, recursive-graph intelligence environment that runs as a desktop application. FortSignal provides the safety and policy layer that makes that environment trustworthy. RGI provides the cognition layer that makes it useful.

## Rationale

### Why RGI-first

The RGI engine is already functional:

- Recursive graph execution works.
- The v0.3 perception port ingests real codebases via tree-sitter and produces structural cognitive graphs.
- Benchmarks show adaptive topology outperforming fixed pipelines at the local-model tier.

Starting from the engine means we ship a working product quickly, then harden it with governance rather than designing governance in a vacuum.

### Why governance as kernel, not separate product

A standalone "FortSignal OS" without RGI would be a policy framework with no compelling user-facing capability. RGI without FortSignal would be a powerful local agent with no safety story.

The correct shape is a single product where:

- **RGI** is the reason to install it.
- **FortSignal** is the reason to trust it.

## Proposed architecture

```
┌─────────────────────────────────────────────────────────────┐
│  RGI OS — Tauri desktop shell (Rust)                        │
│  ┌──────────────┐    invoke/commands     ┌──────────────┐   │
│  │  Webview     │  ←──────────────────→  │  Rust host   │   │
│  │  TS/Vite     │                        │  src-tauri/  │   │
│  └──────────────┘                        └──────┬───────┘   │
│                                                 │            │
│  FortSignal kernel (OS-level policy enforcement)│            │
└─────────────────────────────────────────────────┼───────────┘
                                                  │ spawns / monitors
                                                  ▼
┌─────────────────────────────────────────────────────────────┐
│  RGI cognitive engine (Python)                              │
│  - HTTP or gRPC service                                     │
│  - recursive graph execution                                │
│  - perception, memory, reasoning, tools                     │
│  - FortSignal semantic policy checks                        │
└─────────────────────────────────────────────────────────────┘
```

### Rust shell responsibilities

- Spawn and lifecycle-manage the Python RGI engine.
- Enforce OS-level permissions: which directories the engine may read, whether subprocesses are allowed, network access, LLM provider restrictions.
- Provide IPC between the webview and the engine.
- Package the whole product as a single installable desktop binary.
- Implement the FortSignal **hard boundary**: the engine cannot read or write anything the shell has not explicitly permitted.

### Python engine responsibilities

- Build and reason over local cognitive graphs.
- Recursively spawn, verify, and correct subgraphs.
- Execute grounded tools (`read_file`, `grep`, `callers`, security scanners, etc.).
- Implement the FortSignal **semantic boundary**: evaluate whether a proposed spawn or tool call violates policy, lacks confidence, or requires verification.

### Why governance lives in both layers

| Layer | Enforces | Example |
|---|---|---|
| Rust shell | Hard resource limits | Engine cannot read `~/.ssh` unless explicitly allowed. |
| Python engine | Semantic policy | A spawn request with confidence 0.4 must be verified before execution. |

The shell answers **"is this physically allowed?"** The engine answers **"is this wise?"** Both are required for a safe autonomous system.

## Deployment targets

The same Python engine runs across all targets; only the transport/packaging changes:

| Target | Shell | Governance enforcement |
|---|---|---|
| Local desktop | Tauri + Rust sidecar | Rust shell + Python engine |
| Cloud / rlmlocal-site | Python engine as long-running service | Container policy + Python engine |
| CI / batch | Direct `python -m rgi` | Environment policy + Python engine |

## Immediate next steps

1. **Scaffold Tauri sidecar.** Create the Rust code that spawns the RGI Python engine as a local HTTP service and exposes `analyze_repo`, `engine_status`, and `kill_engine` to the webview.
2. **Choose IPC for v0.3.** HTTP/REST is acceptable for the first integration. gRPC or Unix-domain sockets can be evaluated later if latency becomes an issue.
3. **Add semantic FortSignal gate in Python.** Extend `FortSignalGate`/`LocalGate` so that every tool execution and spawn request is checked against a policy file or policy graph.
4. **Add OS-level sandbox in Rust.** Before launching the engine, the shell should restrict filesystem access and report those restrictions to the user.
5. **Do not split products yet.** Market and ship one product: a local recursive-graph intelligence environment with built-in governance.

## Open questions

1. Does FortSignal policy live as a static config file, a runtime graph, or both?
2. How does the user approve policy exceptions mid-session?
3. Should the Rust shell maintain its own audit trail, or should all events be streamed from the Python engine's audit log?
4. What is the minimum viable policy language for v0.3?

## Alternatives considered

| Approach | Verdict |
|---|---|
| Build FortSignal governance OS as a separate product first | Rejected. No compelling user capability without RGI. |
| Build RGI without governance and add it later | Rejected. Safety must be part of the core story from the start. |
| RGI OS shell with FortSignal as kernel | Accepted. Single product, clear value proposition, layered enforcement. |
