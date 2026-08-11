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

## 7. Execution layer & tool alignment (analyzed 2026-08-11)

**rlmlocal's execution layer is real, not a skeleton** (verified against code):
- Rust backend `src-tauri/src/lib.rs` (2001) + `opencode_host.rs` (1902): 27 Tauri
  commands — patch pipeline, TS compiler service, git_cochange, GEPA trace DB,
  OpenCode host.
- TS bridge `platform.ts` (618): one brain, two runtimes — Tauri `invoke`
  (production) or `:1421` HTTP bridge (browser dev). Pairing token (release-only),
  domain-locked CORS.
- Human gate `execConsole.ts` (2297): verify → approve → `apply_patch` (the ONE
  atomic write path), one commit per land, task released only after Approve.
- Iterate loop `RunCodeTaskIterate.ts` (1685): stash, atomic batch verify,
  RED-clears-stash, caps (6 iters / 2 RED / 3 junk / 5 truncate), never auto-lands.

**Crown jewels to REUSE in RGI-OS (language-agnostic, transport-agnostic):**
- The verify engine: `make_shadow`/`remove_shadow`/`verify_patch_inner` (git
  worktree shadow, baseline-diff, failure fingerprints, `tests_ran=None` honesty).
- The hunk engine (`Edit` search/replace with atomic cross-file validation).
- The human gate invariant: "all changes land through the one atomic
  `apply_patch` tail."
- The transport split pattern (one logic, two transports → RGI-OS adopts the
  same trick on its Python localhost server).

**REPLACE / harden (don't inherit baggage):**
- ⚠️ Path traversal in verify/apply — **FIXED 2026-08-11** (`confine_join`
  rejects absolute + `..` on every edit target; scoped `git add -- <files>`
  instead of `git add -A`; 2 new Rust tests, 31 pass).
- Debug builds have no token on `:1421` + CORS any-localhost — RGI-OS must
  implement real auth (per-request, proper error statuses).
- Errors return HTTP 200 with `{"error":...}` — clients must parse body.
- Missing timeouts on `run_ts_script` and `opencode_task_turn`.
- TS-only fence + TS-only T0 gates — port to Python (ruff/mypy/pytest).

**Tool inventory — rlmlocal vs RGI (alignment):**

| Capability | rlmlocal (TS) | RGI (Python) | Aligned? |
|---|---|---|---|
| List dir | `listDir` (browserTools) | `list_dir` | ✅ same shape |
| Read file | `readFile` (full/truncated/fresh) | `read_file` (line bounds) | ✅ RGI adds line bounds |
| Grep | `grep` (regex, caps) | `grep` (regex, glob) | ✅ |
| Find files | `findFiles` (pattern) | `find_files` (glob) | ✅ |
| Stat | `stat` (mtime+size) | `stat` (size/mtime) | ✅ |
| Write file | `writeFile` (gated) | *(none — Phase 3 exec)* | ⚠️ RGI missing, planned |
| Edit file | `editFile` (gated) | *(none — Phase 3 exec)* | ⚠️ RGI missing, planned |
| Run tests | `runTests` → executor | `run_pytest` | ⚠️ RGI only pytest, rlmlocal multi-runner |
| Lint/type | `resolve_types` (TS compiler) | `run_pyflakes`/`run_py_compile` | ⚠️ rlmlocal TS, RGI Python |
| Refactor | `compute_refactor` (TS LS) | *(none)* | ⚠️ RGI missing |
| Co-change | `git_cochange` (git log) | *(none)* | ⚠️ RGI missing |
| Security scan | *(none — stub `securityFindings`)* | `security_scan` (deterministic) | ✅ RGI fills rlmlocal's gap |
| Explore corpus | `explore_corpus` (sandbox REPL) | `explore_corpus` (sandbox REPL) | ✅ both |
| Symbol callers | `getDependencies`/`callers` (graph) | `callers` (import-graph) | ⚠️ rlmlocal richer |
| Parse structure | tree-sitter `StructureExtractor` | `parse_python_file` + rlmlocal_compat | ✅ both |
| MCP tools | `list_local_resources` etc. | MCP server (`/mcp`) | ✅ both directions |

**The alignment rule:** where both have a tool, keep the same wire shape
(`ToolResult {success, output}` / `{findings, confidence}`) so either engine can
drive either surface. Where only one has it (security_scan on RGI; refactor/
co-change on rlmlocal), the other side gains it without changing the existing
tool's contract. RGI-OS reuses rlmlocal's executor primitives via the bridge and
adds Python runners + security_scan + recursive verification as RGI's
contribution.

## 8. Parser map & interim integration design (analyzed 2026-08-11)

### 8.1 The parser landscape (which technology does what)

| Technology | rlmlocal (TS) | RGI (Python) |
|---|---|---|
| tree-sitter | Everything structural — extract/cluster/decouple/fence/method-object. **Python lane = tree-sitter-python, NOT `ast`** | Structure extraction (6 langs), import/call graphs |
| Python `ast` | none | `code_parser.py` (default) + security_scan plaintext check |
| regex | commands, data-flow keys, route refs, non-JS rename, SEARCH/REPLACE | data-flow keys, route refs, security checks, fallback |
| TS compiler (executor) | `resolveTypes`/`computeRefactor` — the ONLY full-semantic parser | none |
| Louvain | cluster detection | none |

**Key corrections to prior assumptions:**
- rlmlocal's "Python lane" is **tree-sitter-python**, not Python's `ast`.
- RGI has **TWO perception paths** (`ast` default vs tree-sitter compat) that
  produce different graphs — must be unified before integration.
- The data-flow modules are **semantic twins** (identical op tables/regexes/
  fan-out); the `${...}` interpolation is identical. Risk is drift, not mismatch.
- The real mismatch is **route params**: rlmlocal collapses `:id`/`${x}`/`[id]`/
  `{id}`/`<int:id>` → `*`; RGI only splits at `<`. A `fetch('/users/${id}')` +
  `@app.get('/users/<int:id>')` pair connects in rlmlocal's scheme, not RGI's.

### 8.2 Refactor operation matrix (what's TS vs Python, T0 vs T1)

| Op | TS | Python | Deterministic (T0) or Generative (T1) |
|---|---|---|---|
| File move/rename | ✅ | ✅ | T0 |
| Move fn → module | ✅ | ✅ | T0 |
| Cluster move | ✅ | ✅ | T0 |
| Extract function/carve | ✅ | ❌ (falls to generative coder) | T0 TS / T1 py |
| Decouple (all variants) | ✅ | ❌ | T0 TS / T1 py |
| Extract collaborator | ✅ | ✅ | T0 |
| Method-object | ✅ | ✅ | T0 |
| Rename symbol | ✅ compiler | ⚠ text word-boundary | T0 |
| Converge | ✅ | ✅ | T0 |

**RGI can DRIVE without reimplementing:** every gate is command-string driven
(`move cluster X in <file>`, `decouple X in <file>`, `extract X in <file>`), and
the engine re-derives structure itself (never trusts caller targets). RGI's graph
only needs to *select targets* — verification, types, and edits stay in the TS
stack (or py stack for py files).

### 8.3 The interim integration design (how RGI graph drives rlmlocal gates)

1. **RGI selects targets from its graph** — symbol activation + data-flow +
   call/import edges point at files/functions worth refactoring (the "why").
2. **RGI emits the existing command strings** into rlmlocal's scheduler — the
   same seam the in-repo planner (`filePlan.ts`) uses. Zero rlmlocal engine
   change; the gates already re-derive structure and verify via shadow.
3. **TS ground-truth via `resolveExtractTypes.cjs`** — it already speaks
   tree-sitter coordinates and emits the same hunk shape. RGI shells out to it
   for TS types/refactors; no reimplementation.
4. **Data-flow tables stay in sync** — treat the op sets + regexes as ONE shared
   artifact (generated), not two hand-maintained lists.
5. **Reference graph adopts rlmlocal's param-collapse** — the strictly more
   general `*` collapse + Django/`@Get`/`#[get]` registrations.

### 8.4 Honest gaps to close (in priority order)

1. **Unify RGI's two perception paths** (retire `ast` default in favor of
   tree-sitter compat, or define it as Python-only fallback).
2. **Uplift RGI's structure extractor** — `const foo = () => {}`, Go types,
   Rust struct/enum, non-top-level Python/JS, `callSites` (function-level calls).
3. **Extend RGI language coverage** to rlmlocal's 18 extensions (ruby regex +
   content-only rows).
4. **Reference-graph route param collapse** (RGI adopts rlmlocal's scheme).
5. **Python decouple/carve/rename** — port the tree-sitter-python equivalents
   (the T0 gap in the matrix) if RGI-OS needs Python refactors standalone.

## 9. Artifact layer — a first-class principle (added 2026-08-11)

### 9.1 The principle

**Artifacts are materialized, versioned, content-addressed OUTPUTS; logic is the
pure code that produces them.** Every graph layer, finding, proposal, and run
report becomes an artifact with provenance — retrievable from memory instead of
recomputed. This is the Nix/Bazel build-system insight applied to agent memory:
"give me the import graph for repo X at commit Y" is an O(1) lookup, not a
recompute.

```
parse(file@hash) → structure artifact → import-graph artifact → call-graph artifact
                                      → reference-graph artifact → data-flow artifact
                                      → findings artifact → run-report artifact
```

Each layer is a pure producer: consumes artifacts, produces artifacts, keyed by
content hashes + producer version. Provenance (inputs-hash, producer version,
run id) makes everything replayable — the receipts story.

### 9.2 Why it's the architecture's spine (not just efficiency)

1. **It IS the typed-memory design.** The working/episodic/semantic/procedural
   memory research becomes concrete: *semantic = validated findings, episodic =
   run reports, procedural = successful refactor proposals.* fortmemory-vault is
   the store; artifacts are what it holds. "Called from memory" = retrieval over
   artifacts.
2. **It solves a real current gap.** The deep-dive found rlmlocal rebuilds all
   graph layers in-memory every build (not persisted), and RGI's `data/*.json`
   dumps are not queryable. Artifacts unify both: one store, one schema,
   retrieval instead of recompute.
3. **It IS the audit/receipts story.** An artifact with provenance is replayable
   by construction — the frozen `G=(V,E,S,P)` protocol = the artifact schema; the
   snapshot format (`rgi-graph-snapshot-v1`) = the artifact interchange.
4. **It fixes the C2 failure mode.** The C2 verdict said "perception stores only
   labels, not code bodies." Artifacts carry the bodies, content-addressed — a
   symbol query hits the actual code, not a label.

### 9.3 The invalidation model (adopt, don't invent)

Content-hash + mtime + version keys — rlmlocal's `freshness.ts` + version-anchored
`ConceptStore` is exactly this machinery. Rule: **content hash changed → rebuild
that artifact and downstream dependents.** Do not invent a new staleness model;
adopt theirs, content-addressed.

### 9.4 Scope discipline

- **Artifact-ify the DATA, not the logic.** Parsers, graph builders, refactor
  gates, scanners stay code. Only their outputs become artifacts.
- **Don't block the benchmark.** The benchmark is the honest gate; the artifact
  layer makes its results durable, not the other way around. Benchmark reports
  themselves become versioned artifacts so the verdict is replayable.
- **Local artifact cache first** (RGI `data/` + fortmemory later) — prove the
  content-addressed store + freshness before wiring the memory sidecar.

### 9.5 Phase item (Phase 4 hardening)

- Build a minimal local artifact cache: `store(layer, inputs_hash, producer, data)`
  + `get(layer, inputs_hash)` + `invalidate(downstream)`, keyed by content hash.
- Wire the perception layers to produce/consume artifacts instead of recomputing.
- Then point fortmemory-vault at the same artifact schema (semantic/episodic/
  procedural classes) so retrieval spans sessions.

## 10. Open questions (parked, not blocking)

- Python runtime bundling strategy (PyInstaller vs uv vs system Python) — spike
  in Phase 4.
- Graph snapshot performance for large repos — test with real projects.
- Whether the PWA ever hosts the RGI engine (cloud mode) or stays companion.
- FortSignal policy language / static config vs runtime policy graph.

## 11. Definition of Done for v1 (vertical slice)

- [ ] One download → pick folder → graph builds → ask/scan/investigate → verified
      findings → audited report, against a real LLM.
- [ ] Scanner works from the rlmlocal UI, default engine untouched.
- [ ] RGI engine is an opt-in deep-research mode, flagged off, measured.
- [ ] Every run is audited; nothing lands without shadow-verify + human Approve.
- [ ] All new network surfaces localhost-only; snapshot paths validated.
- [ ] Both repos on `feature/rgi-rlmlocal-adapter`; docs match code.
