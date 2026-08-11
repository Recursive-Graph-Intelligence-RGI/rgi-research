# RGI-OS — Product & Integration Plan (Canonical)

**Status:** ACTIVE — canonical roadmap. Supersedes the piecemeal 08-10/08-11/08-12
integration notes for product direction. Research findings in `docs/reports/`
remain authoritative for the science; this doc decides the product.

**Last updated:** 2026-08-11 (post deep-dive alignment session)

---

## 1. The Product (one sentence)

A **governed, local-first cognitive workbench for code**: one download, one UI,
one CLI. Pick a folder → the graph builds in front of you → ask questions, run a
security scan, or start a deep investigation → any change is verified in a shadow
and lands only on human approval → every run is audited, with FortSignal as the
optional cloud governance layer that makes it trustworthy.

## 2. Positioning (what we are / are not)

| Not this | This |
|---|---|
| Another agentic coding tool (Cursor / Claude Code / OpenCode) | A governed local intelligence workbench |
| A "governance OS" product | Governance is the **moat**, not the product |
| A swarm of agents | One world-model (the code graph), many coordinated jobs inside it |
| A research lab artifact | A product that ships a vertical slice, then hardens |

**The differentiated slot:** *agent governance + verifiable local intelligence.*
Nobody owns "you can see the graph, you can see why it acted, it can't land
anything without proof and approval, and it's signed."

## 3. Architecture (settled)

```
┌────────────────────────────────────────────────────────────────────┐
│ rlmlocal UI (workbench surface) — graph canvas, chat, evidence,     │
│ exec console, verify/approve/land                                   │
│   ↕  HTTP/SSE (127.0.0.1) — localhost-guarded, CORS'd              │
├────────────────────────────────────────────────────────────────────┤
│ RGI engine (Python) — perception (tree-sitter graph), recursive     │
│ spawn/verify/correct, deterministic scanner, tool registry,          │
│ memory/activation, semantic governance (LocalGate → FortSignalGate)  │
│   ↕  spawn via Tauri sidecar / `python -m rgi`                      │
├────────────────────────────────────────────────────────────────────┤
│ Rust shell (Tauri) — process lifecycle, hard path boundary,         │
│ packaging, (later) passkey + OS sandbox                             │
├────────────────────────────────────────────────────────────────────┤
│ FortSignal (cloud, neutral) — metered governance API, signed        │
│ receipts, delegation caps, passkey identity (Phase 6)               │
└────────────────────────────────────────────────────────────────────┘
```

**Hard rules:**
1. **rlmlocal stays TypeScript; RGI stays Python; Rust stays the shell.**
   No engine rewrite, no brain merge into the UI.
2. **The default reasoning path is rlmlocal's brain (SimpleRLMAgent) until the
   substrate research proves RGI's engine is better** on precision + recall +
   answer quality. RGI is an opt-in "deep research" mode, flagged off.
3. **Nothing lands without proof + approval.** Shadow verify → human Approve →
   apply. The invariant: *the brain proposes, the human approves, the hands
   write.*
4. **All new network surfaces are localhost-only** by default.
5. **Graph snapshots are versioned** (`rgi-graph-snapshot-v1`); unknown
   versions rejected; absolute/parent-relative paths rejected.
6. **Every spawn/deny/correction is audited** (this is the governance hook).

## 4. The research→product bridge

RGI's C2 verdict (2026-08-10) is the honest anchor:

> *v0.2 proves recursive orchestration is the active ingredient for
> small/medium real code, but the next breakthrough requires a code-grounded
> substrate — call/data-flow graphs, symbol-aware activation, grounded REPL
> tools — rather than further tuning of spawn caps or time limits.*

So the product does **not** wait for the research to settle the brain question.
It ships the vertical slice with rlmlocal's brain as default and RGI as the
opt-in deep mode. The substrate work (Phase 3 below) is the experiment that
decides whether RGI's engine *becomes* the default later — data, not taste.

**Kill criteria (pre-committed):** if after the substrate work RGI's engine does
not beat the incumbent on real code on precision + recall + answer quality,
RGI stays a tool/research contributor and the product keeps rlmlocal's brain.
That is a win either way: the product ships, the research is honest.

## 5. Phases

### Phase 0 — Truth & hygiene (small, do first)
- Update plan/spec docs so checkboxes/status match code (docs lag reality badly).
- Add the RGI-OS role to rlmlocal's `docs/internal/STATUS.md` so the product
  repo acknowledges the strategy it serves.
- Delete the dead `v0.3-perception-port` branch (done) + rename the adapter
  branch to `feature/rgi-rlmlocal-adapter` on both repos (rlmlocal done).

**Exit:** docs match code; both repos on one branch name.

### Phase 1 — Scanner into rlmlocal as a tool (real value, zero engine risk)
- rlmlocal's `securityFindings` is an empty stub with zero producers.
- The MCP bridge (`rgi/mcp/server.py`) already exposes `security_scan` as a
  tool; wire it into rlmlocal's existing MCP client so users get a real
  deterministic scan (SQLi, path traversal, weak crypto, cmd injection,
  hardcoded secrets, env-fallback credentials) without touching the engine.
- Deliverable: chat "run a security scan" → findings card (already built,
  XSS-escaped, flag-gated).

**Exit:** scan works end-to-end from the rlmlocal UI, default engine untouched.

### Phase 2 — Desktop vertical slice (the "one product" proof)
- Take `tauri-sidecar-example/`, make it real:
  - Un-mock the LLM path (currently hardcoded `mock: true` in `lib.rs`).
  - Reuse rlmlocal UI components (file picker, graph canvas, chat, report) —
    do NOT copy the brain.
  - One end-to-end run: pick folder → graph builds → ask/scan → findings →
    audited report.
- No production packaging yet (bundle stays dev-runnable).
- Local-only mode first; passkey/auth comes with FortSignal (Phase 6).

**Exit:** one installable dev app does the full loop against a real LLM.

### Phase 3 — Substrate research (parallel, decides the brain question)
- Finish the C2-named substrate: wire multi-language perception end-to-end
  (currently extractor-only; `ingest_codebase` walks only `*.py`), port the
  data-flow graph, symbol-aware activation.
- Re-run the C2-style benchmark; compare RGI vs incumbent on precision +
  recall + answer quality.
- Pre-registered read: if RGI ≥ incumbent, flip the default in a future phase;
  if not, RGI stays tool/research.

**Exit:** an honest verdict, published with the numbers.

### Phase 4 — Product hardening (after the slice works)
- Packaging (single installer, bundled Python runtime spike: PyInstaller vs uv
  vs system Python).
- Production build config (`bundle.active`, icons, `scripts/build.sh`).
- Tauri E2E smoke script + committed protocol doc.
- The PWA stays as lightweight browser companion (chat + scanner).

### Phase 5 — RGI-OS deep integration (only if Phase 3 says flip)
- RGI engine becomes the default reasoning kernel; rlmlocal brain retired from
  the default path (kept as fallback).
- Graph canvas surfaces the live RGI graph; evidence panel renders verified
  findings.

### Phase 6 — FortSignal governance (the moat, deliberately last)
- `FortSignalGate` (currently a `NotImplementedError` stub) → real integration
  through the existing seams (`LocalGate` policy file, `AuditLog` receipts).
- Passkey/WebAuthn identity in the Rust shell; signed receipts; delegation
  caps.
- Desktop gets passkey first; PWA gets governed writes later.
- This is what external architectures adopt and why anyone pays — but it is
  not the next sprint. The vertical slice works local-only first.

## 6. What NOT to do (standing)

1. Don't rewrite rlmlocal's brain into RGI or vice versa.
2. Don't build more skeletons before the vertical slice works.
3. Don't let RGI's engine become the default before the Phase 3 verdict.
4. Don't add governance before the product works (it's the moat, not the MVP).
5. Don't treat "GREEN" as correct — human Approve stays the land gate.
6. Don't auto-land anything (T0 deterministic transforms may auto-land later,
   T1/generative never without human).

## 7. Open questions (parked, not blocking)

- Python runtime bundling strategy (PyInstaller vs uv vs system Python) — spike
  in Phase 4.
- Graph snapshot performance for large repos — test with real projects.
- Whether the PWA ever hosts the RGI engine (cloud mode) or stays companion.
- FortSignal policy language / static config vs runtime policy graph.

## 8. Definition of Done for v1 (vertical slice)

- [ ] One download → pick folder → graph builds → ask/scan/investigate → verified
      findings → audited report, against a real LLM.
- [ ] Scanner works from the rlmlocal UI, default engine untouched.
- [ ] RGI engine is an opt-in deep-research mode, flagged off, measured.
- [ ] Every run is audited; nothing lands without shadow-verify + human Approve.
- [ ] All new network surfaces localhost-only; snapshot paths validated.
- [ ] Both repos on `feature/rgi-rlmlocal-adapter`; docs match code.
