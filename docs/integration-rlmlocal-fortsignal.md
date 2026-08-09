# Integration Architecture: RGI × rlmlocal × FortSignal

*Drafted 2026-08-09, after full-workspace analysis (rlmlocal-site,
rlmlocal-sandbox, rlm-cognitive, fortsignal-api/sdk, fortmemory-vault).*

## The full stack — no missing layer

```
┌─────────────────────────────────────────────────┐
│ GOVERNANCE   fortsignal-api (LIVE, production)  │  cryptographic intent binding,
│              + @fortsignal/sdk (npm)            │  deterministic assertPolicy(),
│                                                │  HMAC-chained audit, signed
│                                                │  execution artifacts (receipts)
├─────────────────────────────────────────────────┤
│ INTELLIGENCE RGI (this repo)                    │  recursive graphs, harness hard
│                                                │  limits, coverage verification,
│                                                │  REPL substrate, measured curve
├─────────────────────────────────────────────────┤
│ INTERFACE    rlmlocal-site (browser brain)      │  tree-sitter AST graph (polyglot),
│                                                │  WebGPU local models, cytoscape
│                                                │  canvas, human approval UX
├─────────────────────────────────────────────────┤
│ EXECUTION    rlmlocal-sandbox (Tauri, v0.1.7)   │  shadow-run tests, approved
│                                                │  writes only, pairing-token
│                                                │  localhost bridge (127.0.0.1:1421)
├─────────────────────────────────────────────────┤
│ MEMORY       fortmemory-vault (Go MVP)          │  agentic memory for Markdown
│                                                │  vaults, FortSignal-governed
│                                                │  mutates, HTTP + MCP
└─────────────────────────────────────────────────┘
```

Philosophy is identical at every layer: *propose → verify → only then act.*
FortSignal: nothing executes without cryptographic authorization. RGI:
nothing spawns without harness approval, every decision audited. Sandbox:
nothing writes without human approval. Same shape, three layers.

## Division of labor: rlmlocal is the face, RGI is the brain stem

```
BROWSER (rlmlocal)                SERVER (RGI)
┌─────────────────────┐          ┌──────────────────────────┐
│ tree-sitter AST      │  files   │ PerceptionLayer           │
│ graph (polyglot      │ ──────►  │ (upgraded: consumes       │
│ perception)          │  + AST   │  tree-sitter entities,    │
│                      │  entities│  not just Python ast)     │
│ cytoscape canvas     │          │                           │
│ (renders topology)   │  SSE     │ execute_graph() + Harness │
│                      │ ◄──────  │ (the measured engine:     │
│ "what is the system  │  live    │  spawn, verify, cover,    │
│  doing right now?"   │  audit   │  correct, hard limits)    │
└─────────────────────┘          └──────────────────────────┘
         ▲                                  │
         │        FortSignal artifact       ▼
         └──────── approval token ── rlmlocal-sandbox (writes)
```

## The three seams (build order)

### Seam 1 — RGI gets an API (1–2 days)
RGI is CLI-only today. Wrap `run_analysis` in FastAPI with Server-Sent
Events streaming the audit log. Turns RGI from a batch tool into a
runtime: the browser subscribes and watches graphs spawn, verify, and
correct live on the cytoscape canvas. Audit events are already JSON;
`topology_used` in the report is already renderable. This is the demo
nobody else can show: topology visibly evolving.

### Seam 2 — Perception bridge (2–3 days)
RGI's PerceptionLayer uses Python `ast` — Python-only. rlmlocal's
tree-sitter graph parses JS/TS/Rust/Go/Python into dependency entities
in-browser. Ship those entities as RGI's world-model seed: RGI stops
parsing and starts *receiving* perception. Polyglot support for free;
45k lines of existing browser work becomes RGI's eyes.

### Seam 3 — Governance + execution loop (the flagship)
RGI's `FortSignalGate` stub (`rgi/core/governance.py`) → FortSignal
`/challenge/start` + `/challenge/verify`. RGI actions (spawn, tool, LLM
call) map to FortSignal's action/recipient/amount model; the graph
runtime registers as an Ed25519 agent passport with dashboard-approved
delegation (caps = spawn limits). The sandbox validates the signed
artifact before any write lands. Audit schemas nest cleanly: RGI
`{event, graph_id, reason, timestamp}` is a subset of FortSignal's
HMAC-chained `AuditRecord {action, agent_id, decision, reason, ...}`.

## What "RGI becomes the tech" means

rlmlocal's in-browser `RecursiveScheduler` is replaced over time by RGI
API calls. The browser keeps interaction, rendering, and approval UX;
RGI owns cognition, evidence, and the audit trail. No site rewrite —
it becomes an API client gaining a smarter backend, one seam at a time.

## Consolidation note

Three codebases implement recursive scheduling: rlmlocal-site (TS),
rlm-cognitive (Python, stalled since 2026-05, ~1.7k LOC, empty graph/
package), and RGI. Decision: RGI is the measured engine; rlmlocal-site
is the interface; rlmlocal-sandbox is the executor; rlm-cognitive's 24
planning docs are mined for ideas and the code retired.

## Sequencing (unchanged, evidence-first)

1. Verdict: overnight ladder + pre-fix control graded
2. 5-run cells on key tiers (error bars for review)
3. Phase 1: real-repo scale test (REPL becomes load-bearing)
4. THEN Seam 1-3 integration as the flagship demo:
   *"An AI system that spawns its own sub-agents, proves what it read,
   and cannot act without cryptographic authorization — running
   entirely on local models."*
