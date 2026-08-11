# RGI-OS Session Log — 2026-08-11 (deep-dive alignment day)

**Branch:** `feature/rgi-rlmlocal-adapter` (rgi) / `feature/rgi-rlmlocal-adapter` (rlmlocal)
**Canonical plan:** `docs/superpowers/plans/2026-08-11-rgi-os-product-and-integration-plan.md`

This is the running session log for the RGI-OS build. Entries record decisions,
findings, and open threads so future sessions/agents can pick up context without
re-deriving it. Follows rlmlocal's `memory/notes-*.md` pattern.

---

## 2026-08-11 — Day 1: strategy alignment + first vertical slice

### Decisions made (locked this session)

1. **One product, not three.** RGI-OS = a governed, local-first cognitive workbench
   for code: one download, one UI, one CLI. rlmlocal = the workbench surface
   (UI + executor + brain). RGI = the recursive-graph engine (opt-in deep mode).
   FortSignal = the moat (governance, Phase 6, deliberately last). Not "an OS",
   not "a governance OS", not "a coder" — the intersection, with agent governance
   + verifiable local intelligence as the differentiated slot.
2. **rlmlocal's brain stays the default** until the Phase 3 benchmark proves RGI's
   engine beats it on precision + recall + answer quality. RGI is feature-flagged
   (`rgi-adapter-enabled`, default off) until then. Kill criteria pre-committed:
   if the substrate work doesn't beat the incumbent, RGI stays tool/research.
3. **Artifact layer is a first-class principle.** Materialized, versioned,
   content-addressed outputs (graphs, findings, reports); logic stays code.
   Keyed by content hash + producer version → O(1) retrieval from memory instead
   of recompute. Adopts rlmlocal's freshness model (content hash changed →
   rebuild + downstream). Local cache first (`rgi/artifacts.py`); fortmemory is
   the durable store in Phase 6.
4. **Memory strategy = two layers.** NOW: committed session log + plan docs (zero
   friction, works today). LATER (Phase 6): fortmemory-vault as the governed
   durable store (its writes require FortSignal challenge/verify by design —
   that's the product, and governance is deliberately last).
5. **Integration = RGI selects targets from its graph, emits existing command
   strings into rlmlocal's scheduler** (zero engine change; gates re-derive
   structure + verify via shadow). TS ground-truth via `resolveExtractTypes.cjs`
   (already speaks tree-sitter coordinates).

### What was built (commits on `feature/rgi-rlmlocal-adapter`)

| Commit | What |
|---|---|
| `2ae75c7` | Canonical RGI-OS plan doc |
| `525c5ea` | Tauri slice: real security-scan command, un-mock analyze_repo, tsconfig |
| `b8eaf9a` | Tauri fixes: working-dir resolution, dialog capability, valid icons |
| `16ef411` | Multi-language world model (py/js/ts/go/rs) + build-dir skip |
| `ed3db66` | Symbol-aware activation (C2-named gap) |
| `a1e0dbc` | Data-flow graph port (producer→consumer channels) |
| `f0ab97f` | Plan: parser map + refactor matrix + interim integration design |
| `793ddab` | Artifact cache + artifact-layer plan section |

rlmlocal (`feature/rgi-rlmlocal-adapter`): adapter client + flag wiring + findings
card (earlier commits), then `72ab4fd` — executor path-traversal fix (confine_join
+ scoped git add), `1b6bf0a` — XSS escape + flag-gated listener + fail-open.

### Verified working

- **Desktop vertical slice (Phase 2):** pick folder → start engine → run security
  scan → 7 grounded findings in the Tauri app (sample_project). Toolchain:
  `GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1 npm run tauri:dev`
- **Server hardening:** localhost guard (Host/Origin), CORS, snapshot path
  validation, path confinement on security-scan. 257→286 tests passing.
- **Multi-language world model:** tauri-sidecar-example 5959 → 23 nodes after
  build-dir skip; federated-alpha yields 492 data-flow edges.

### Deep-dive findings (the analysis that shaped the plan)

1. **rlmlocal execution layer is real, not skeleton.** Rust backend (27 commands),
   TS bridge (`:1421` + Tauri invoke), human gate (verify→approve→apply), iterate
   loop. Crown jewels to reuse: verify engine (shadow worktree + baseline-diff),
   hunk engine, human-gate invariant, transport split.
2. **Parser map:** rlmlocal = tree-sitter everywhere (Python lane is
   tree-sitter-python, NOT `ast`) + TS compiler for types/refactors; RGI = mixed
   `ast` (default) + tree-sitter (compat) + regex. RGI has TWO perception paths
   that must be unified. Data-flow modules are semantic twins (identical op
   tables); the real mismatch is route-param collapse (`:id`/`${x}` vs `<`).
3. **Refactor matrix:** decouple + deterministic carve are TS-only; Python extract
   falls to the generative coder; Python rename is not reference-aware. RGI can
   DRIVE all gates via command strings without reimplementation.
4. **Artifact value:** fixes the C2 "labels not bodies" failure (artifacts carry
   bodies, content-addressed); IS the typed-memory design (semantic/episodic/
   procedural); IS the audit/receipts story (provenance = replayable).

### Open threads / next steps

1. **Phase 3 benchmark re-run** — the honest verdict on whether RGI's engine beats
   rlmlocal's brain (one run, complete substrate). The plan's disciplined next move.
   **LAUNCHED 15:29** — qwen2.5:7b, all 4 real targets (R1 vulpy, R2 dvpwa,
   R4 pygoat, R3 aiohttp) × (rgi, fixed, single), substrate ON
   (`RGI_RLMLocal_PERCEPTION=1`), fresh output
   `data/real_c2_qwen2_5_7b_substrate-v1.json`. Resumable; ~1.5–3h.
2. **Wire perception layers into the artifact cache** (prove O(1) lookup on a real
   graph build) — plan §9.5. **DONE** — `ingest_codebase_cached`, 2 tests.
3. **Commit the deep-dive raw reports** to `docs/internal/` (currently only
   syntheses are in the plan). **DONE** — `2026-08-11-rlmlocal-refactor-engine-analysis.md`,
   `2026-08-11-parser-map-analysis.md`.
4. **14 untracked `bench/*.mts` probes** in rlmlocal — delete/commit/leave (user's
   call, still open).
5. **Phase 4 hardening** — packaging, production build config, smoke script.
6. **fortmemory as durable store** — Phase 6, when governance lands; artifact
   schema already designed for it.
7. **GEPA analyzed** — rlmlocal's self-healing prompt loop (traceMine → laneGate →
   reflect → objective score → human activate) is the procedural-memory half of
   the typed-memory design. Real + shipped, JS/TS-lane-specific; RGI-OS inherits
   the loop, RGI adds the artifact layer underneath it. Plan §8.5.
8. **Scorer normalization bug found + fixed** — the deterministic scanner emits
   underscore kinds (`sql_injection`) but the eval scorer matched ground-truth
   terms (`sql injection`, `sqli`) as exact substrings → scanner-seeded runs scored
   0 recall despite finding real vulns. Fixed `_normalize()` (underscore/hyphen →
   space on both sides). Verified: 5 sql_injection findings now score recall 0.139 /
   precision 1.0 on vulpy (was 0.0). Commit `add71e3`. This bug had been silently
   deflating every scanner-seeded run's recall — the benchmark re-run is the first
   to measure the substrate honestly.
9. **Model C bridge built + proven** — `exportSnapshot.ts` (rlmlocal) serializes
   the already-built graph (import/call/reference/dataFlow edges + lineage) to
   `rgi-graph-snapshot-v1`; RGI's `import_snapshot` accepts it (round-trip
   verified). This is the "easier solution": RGI consumes rlmlocal's rich graph
   instead of re-porting. Commits `f4d954e`, `6917319`.
10. **Cloudflare edge provider wired into RGI frontier** — `LLMClient
    provider='edge'` hits `{workerUrl}/infer` with `X-RLM-Owner-Key` + ownerKey
    body + CF envelope, mirroring rlmlocal's CloudflareAIProvider. The hybrid:
    local models + graph do breadth, edge frontier (30B @cf/qwen) does
    plan/arbitrate/synthesize (1-3 small calls). Commit `9e9c5c0`.
11. **Phase 3 benchmark results (partial, 7b, substrate ON, scorer fixed):**
    - R1_vulpy: rgi 0.139/prec 1.0 · fixed 0.25/prec 0.33 · single 0.0
    - R2_dvpwa: rgi 0.077/prec 1.0 · fixed 0.192 · single 0.0
    - Pattern: rgi = high precision (verified findings), lower recall; fixed =
      higher recall, lower precision. R4/R3 (big targets) still running.

### Memory (the "let you loose" enabler, as of end of session)

- **Working memory:** this session log + the canonical plan (committed, pushed)
- **Artifact memory:** `rgi/artifacts.py` content-addressed cache; perception
  wired in (`ingest_codebase_cached` → O(1) world-model lookup)
- **Deep analysis:** 4 committed reports (refactor engine, parser map, execution
  layer, C2/session notes) + the 6 plan sections
- **Procedural memory (future):** GEPA loop in rlmlocal; the artifact layer makes
  its traces/lessons/proposals replayable + queryable
- **Governed durable memory (Phase 6):** fortmemory-vault (its writes require
  FortSignal proof by design)

### Running commands (for future sessions)

```bash
# rgi tests
cd /home/jeff/projects/rgi && python -m pytest tests/ -q

# rlmlocal tauri dev (needs the display flags on Linux)
cd /home/jeff/projects/rlmlocal-site && GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1 LIBGL_ALWAYS_SOFTWARE=1 npm run tauri:dev

# rgi server (for PWA smoke test)
cd /home/jeff/projects/rgi && python -m rgi server --port 8787
```
