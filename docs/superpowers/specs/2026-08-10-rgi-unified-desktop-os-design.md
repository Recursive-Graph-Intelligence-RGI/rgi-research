# RGI Unified Desktop OS — v0.3 Design

**Date:** 2026-08-10  
**Status:** Design spec awaiting approval  
**Related docs:**
- `docs/superpowers/specs/2026-08-10-rgi-engine-language-and-tauri-integration-design.md`
- `docs/superpowers/specs/2026-08-10-rgi-os-governance-integration-strategy.md`
- `docs/superpowers/plans/2026-08-10-rgi-v0.3-engine-perception-port.md`
- `docs/superpowers/plans/2026-08-10-rgi-v0.3-tauri-desktop-integration.md`
- `docs/internal/2026-08-10-rgi-rlmlocal-integration-strategy.md`

## Goal

Ship v0.3 as a single installable desktop application: **recursive-graph intelligence for local codebases**, with a polished UI, local execution, and built-in governance. From the user's perspective: one download, one icon, pick a folder, type an objective, get a reasoned, audited analysis.

## Product split

| Product | Stack | Role |
|---|---|---|
| **RGI Desktop** (v0.3) | Tauri shell + RGI Python engine | Primary product. Full local reasoning, filesystem access, governance, code execution. |
| **rlmlocal.com PWA** | TypeScript/Vite + browser ML + Cloudflare worker | Lightweight companion. No RGI, no local filesystem. Stays as-is. |

The existing TypeScript agent stack in `rlmlocal-site` (`SimpleRLMAgent`, `RecursiveScheduler`, gate cascade) is **not duplicated** in the desktop product. Its UI components and graph rendering are reused; its reasoning logic is replaced by RGI.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  RGI Desktop application                                    │
│  ┌──────────────┐    invoke/commands     ┌──────────────┐   │
│  │  Webview     │  ←──────────────────→  │  Rust host   │   │
│  │  TS/Vite     │                        │  src-tauri/  │   │
│  │  (rlmlocal   │                        │              │   │
│  │   UI)        │                        │  FortSignal  │   │
│  └──────────────┘                        │  hard kernel │   │
│                                          │  + passkey   │   │
└──────────────────────────────────────────┼────────────────┘
                                           │ spawns / monitors
                                           ▼
┌─────────────────────────────────────────────────────────────┐
│  RGI Python engine                                          │
│  - HTTP service (`python -m rgi server`)                    │
│  - recursive graph execution                                │
│  - perception / memory / reasoning / tools                  │
│  - FortSignal semantic gate                                 │
└─────────────────────────────────────────────────────────────┘
```

## Component responsibilities

### RGI Python engine

- **Perception:** build a code-grounded cognitive graph from the target directory (functions, classes, imports, calls).
- **Reasoning:** recursively spawn planning/execution/verification/correction subgraphs.
- **Tools:** grounded REPL primitives (`read_file`, `grep`, `callers`, `explore_corpus`, security scanners).
- **Memory + activation:** route attention to relevant symbols using embeddings and graph topology.
- **Governance:** semantic policy checks on every LLM call, tool execution, and spawn.
- **HTTP API:** expose `/analyze`, `/jobs/{id}/status`, `/jobs/{id}/result`, `/shutdown`.

### Tauri Rust shell

- **Spawn RGI:** start the Python engine as a child process on a free localhost port.
- **Process lifecycle:** start, stop, restart, health-check.
- **Hard boundary:** enforce allowed workspace root and pass policy to RGI via environment variables.
- **IPC bridge:** expose Tauri commands (`start_rgi`, `stop_rgi`, `analyze_repo`, `get_status`, `get_result`) that forward to the RGI HTTP API.
- **Packaging:** bundle into a single installable desktop binary.

### rlmlocal UI (TypeScript/Vite)

- **Reused from `rlmlocal-site`:** file picker, graph visualization, chat panel, report view.
- **Retired on desktop:** `SimpleRLMAgent`, `RecursiveScheduler`, in-browser LLM reasoning.
- **New behavior:** call Tauri commands instead of running local agent logic.

### FortSignal governance

- **Rust shell:** hard filesystem limits, LLM provider restrictions, network restrictions.
- **Python engine:** semantic policy (allowed/denied tools, spawn depth, LLM budget, audit trail).
- **Audit:** every spawn, tool call, LLM call, and governance decision is logged.

### FortSignal identity / passkey auth

The existing FortSignal passkey strategy from `rlmlocal-site/docs/_archive/integration-plan.md` is ported into the desktop shell:

- **Passkeys (WebAuthn)** are the primary login method, consistent with fortsignal-api.
- **User onboarding:** first launch prompts the user to create or bind a hardware passkey. On desktop this is done through a Tauri webview or native OS WebAuthn bridge.
- **Authentication endpoint:** the shell authenticates against the Cloudflare Worker / FortSignal auth service, which handles passkey registration, authentication, JWT/session issuance, and subscription status.
- **Session storage:** the Tauri shell stores the session token/credential securely and attaches it to privileged actions.
- **Policy binding:** the authenticated identity is bound to the local policy and audit trail, so every analysis run is signed and attributable.
- **Phase 1 (v0.3):** port the FortSignal passkey flow as a Tauri-side integration; full cryptographic receipts and delegation caps are Phase 2.

## Data flow

1. **On first launch:** user creates or binds a FortSignal hardware passkey through the Tauri-hosted WebAuthn flow.
2. **Per session:** Tauri shell authenticates with the FortSignal/Cloudflare Worker auth endpoint and receives a session token; the token is required before enabling analysis.
3. User picks a folder in the UI.
4. UI calls `analyze_repo(path, objective)` via Tauri invoke.
5. Rust shell verifies `path` is inside the allowed workspace root and the user is authenticated.
6. Rust shell POSTs to RGI `/analyze`.
7. RGI builds the knowledge graph, spawns subgraphs, executes tools, verifies findings.
8. UI polls `get_status(job_id)` and displays progress.
9. When completed, UI calls `get_result(job_id)` and renders findings.

## Integration with rlmlocal-site

The desktop product **does not** modify `rlmlocal-site` in place. Instead:

1. RGI repo provides a working engine + sidecar example.
2. A future integration step copies the proven sidecar pattern into `rlmlocal-site/src-tauri`.
3. `rlmlocal-site` UI components are imported/reused in the desktop product.
4. rlmlocal's rich graph data (`StructureExtractor`, `VectorStore`, import/call graphs) is consumed by RGI via a JSON interchange format.

This keeps `rlmlocal-site` production-stable while RGI experiments in parallel.

## Governance model

| Action | Hard check (Rust) | Semantic check (RGI Python) |
|---|---|---|
| Pick folder | Path must be under allowed root. | — |
| Spawn subgraph | — | `allow_spawn`, `max_depth` policy. |
| LLM call | Provider/network restrictions. | `max_llm_calls` budget. |
| Tool execute | — | Tool allow/deny list + path scope. |
| Code execution | Sandbox via OS permissions. | Confidence / verification requirements. |

## Open questions

1. Should the desktop installer bundle its own Python runtime, or require system Python?
2. How does the Tauri shell discover the RGI installation path in dev vs. production?
3. Should the UI poll for status, or should RGI stream Server-Sent Events?
4. What is the minimal rlmlocal graph interchange format for v0.3?
5. How is the FortSignal passkey flow exposed to the Tauri shell — direct API calls, embedded web view, or native OS APIs?
6. Which FortSignal endpoints and credentials are required for v0.3 auth integration?

## Success criteria

- `python -m rgi server` starts and responds to HTTP requests.
- Tauri sidecar example can spawn RGI, run an analysis, and display results.
- Existing RGI CLI and test suite remain green.
- `rlmlocal-site` is not modified.
- A user can download one desktop app, create/bind a FortSignal hardware passkey, pick a folder, and get a security analysis report.

## Phases

1. **Engine substrate (mostly complete)** — tree-sitter perception, import/call graphs, grounded REPL tools, HTTP service, semantic governance gate.
2. **Tauri sidecar example (in progress)** — minimal Rust+TS app in the RGI repo that drives RGI.
3. **Desktop product shell** — evolve the sidecar example into a real desktop app, reusing rlmlocal UI components.
4. **rlmlocal-site integration** — copy the proven sidecar pattern into `rlmlocal-site/src-tauri` and retire the TS agent stack on desktop.
5. **Packaging + installer** — bundle Python runtime and RGI into the Tauri binary.
6. **FortSignal hardening** — OS-level sandbox, signed receipts, policy UI.
