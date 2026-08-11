# rlmlocal Refactor/Decomposition Engine — Deep-Dive Analysis

**Date:** 2026-08-11
**Status:** reference — feeds the canonical plan §8 (parser map & integration design)
**Source:** subagent deep-dive over `rlmlocal-site/src/features/execution/gates/*`,
`src/features/agent/extract*.ts`, `*Py.ts`, `src/features/execution/fence.ts`,
`src/features/execution/gepa/genDecouple.ts`, plus supporting `Move.ts`,
`couplingSplit.ts`, `isReassigned.ts`, `CrossFileReassigned.ts`,
`functionsTouching.ts`, `clusterCtxFieldsPy.ts`, `moveAlonePy.ts`, `treeSitter.ts`,
`proposeFromEdits.ts`, `platform.ts`, `gates/filePlan.ts`/`filePlanStep.ts`.

---

## 0. Two facts that shape everything

1. **`src/features/agent/decouple.ts` does not exist.** The decouple logic lives in
   four places: the gate `gates/decouple.ts`, the plans in `extractModule.ts`, the
   GEPA task `gepa/genDecouple.ts`, and helpers (`couplingSplit.ts`,
   `isReassigned.ts`, `CrossFileReassigned.ts`, `functionsTouching.ts`).
2. **There is no Python `ast` usage anywhere in this repo.** The "Python lane" is
   the same `web-tree-sitter` WASM with the Python grammar (`treeSitter.ts:29-38`).
   The TypeScript compiler is NOT in this repo — it's the local Tauri executor
   (Rust) behind `ExecPort` (`platform.ts:120-136`).

## 1. Refactor operation inventory + language matrix

| # | Operation | File(s) | TS/JS | Python | Deterministic (T0) or Generative (T1) |
|---|---|---|---|---|---|
| 1 | Move/rename **file** (+importer rewrite, stub) | `gates/fileMove.ts` | ✅ | ✅ | T0 |
| 2 | Move **function → own module** (move-alone) | `gates/moduleMove.ts` → `Move.ts`/`extractModule.ts` (TS), `moveAlonePy.ts` (py) | ✅ | ✅ | T0 |
| 3 | Move **cluster** (fns + shared state) | `gates/moduleMove.ts` → `extractModule.ts`/`Move.ts` (TS), `clusterMovePy.ts` (py) | ✅ | ✅ | T0 |
| 4 | **Extract function / carve** (same-file) | `gates/verifyChange.ts` → `extractFunction.ts` | ✅ deterministic | ❌ (falls to generative coder) | T0 TS / T1 py |
| 5 | **Decouple** — Introduce-Parameter (read-only) | `gates/decouple.ts` → `extractModule.ts` | ✅ | ❌ | T0 |
| 6 | **Decouple** — ctx-hoist (reassigned shared) | `gates/decouple.ts` → `extractModule.ts:451` | ✅ | ❌ | T0 |
| 7 | **Decouple** — TS-compiler encapsulate / generative ctx | `gates/decouple.ts:273/294`, `gepa/genDecouple.ts` | ✅ | ❌ | T0 (compiler) / T1 (coder) |
| 8 | **Extract collaborator** (god-class slice) | `gates/moduleMove.ts` → `extractCollaborator.ts` (TS), `extractCollaboratorPy.ts` (py) | ✅ | ✅ | T0 |
| 9 | **Method-object** | `gates/moduleMove.ts` → `methodObject.ts` (TS), `methodObjectPy.ts` (py) | ✅ | ✅ | T0 |
| 10 | **Rename symbol** (reference-aware) | `gates/moduleMove.ts:1138` | ✅ (TS compiler) | ⚠ text word-boundary only | T0 |
| 11 | **Batch move-alones** | `gates/moduleMove.ts:903` | ✅ | ✅ | T0 |
| 12 | **Converge** (auto-walk to fixed point) | `gates/moduleMove.ts:678` | ✅ | ✅ | T0 |
| 13 | **Cluster map / fields / clusterable files** (read-only) | `gates/moduleMove.ts:203/267/89` | ✅ | ✅ | analysis |

**Honest caveats:** the deterministic **carve** and **all three decouple variants are
TS/JS-only**; Python's extract takes the T1 generative coder. Python's rename is
**not reference-aware**.

## 2. Parser map (what tech drives each)

| Tech | Used by |
|---|---|
| **tree-sitter (web-tree-sitter WASM)** | Everything structural: `extractModule.ts`, `extractFunction.ts`, `extractCollaborator.ts` + Py, `methodObject.ts` + Py, `clusterModulePy.ts`, `clusterMovePy.ts`, `clusterCtxFieldsPy.ts`, `moveAlonePy.ts`, `fence.ts`, `genDecouple.ts`, `verifyChange.ts` |
| **TS compiler / language service (executor, Rust)** | `resolveTypes` (ground-truth types: `decouple.ts:148`, `verifyChange.ts:384`, `extractCollaborator.ts:567`, `moduleMove.ts:460`); `computeRefactor 'extract'/'rename'/'references'/'encapsulate'` |
| **Regex / text** | Command parsing in every gate; `fileMove.ts` specifier candidates; non-JS rename; `parseChanges` SEARCH/REPLACE; import-prune braces; naming regexes |
| **VectorStore index** | `clusterCandidates`, file resolution (`matchBasename`), `callersIndex`/`reverseEdges`/`symbolDefs` for impact |
| **Louvain (Leiden)** | `clusterModule` community detection (`extractModule.ts:1043`) |

## 3. Decision logic (the "intelligence")

- **Cluster-move picks targets:** `clusterModule` builds a weighted fn⇄fn graph
  (private calls with fan-in < 3 + shared-state co-usage) → **Louvain communities**
  → classify `single`/`cluster`/`blob`(≥½ fns)/`pinned`. The mover re-derives the
  cluster from any member, re-inventories the file, refuses state used by
  non-cluster code (`extractModule.ts:979-1073, 827-958`; `clusterMovePy.ts:30-68`).
- **Decouple picks what to split:** `collectCoupling` free-ref scan → coupling vars
  → split read-only vs reassigned (`isReassigned` AST) → `classifyDecouple` cascade
  (`extractModule.ts:167-267, 316-379`). Refuses exported fns, callbacks,
  unresolved types.
- **ExtractFunction picks the boundary:** whole-statement windows (1–3) at the
  span's own nesting level, <85% of body → `cleanCarveCandidates` (cohesive by
  data-flow, ≤5 params) → ranked biggest-first → signature from free-var analysis
  (`extractFunction.ts:435-547, 193-424`).
- **Extract-collaborator picks the slice:** two-axis adaptive peel (field co-usage
  + call cohesion with density gate) → slices; separability gate refuses
  shared/ctor-set/cross-file fields (`extractCollaborator.ts:106-446`).
- **Converge:** re-plan each round, prefer reducers that shrink the file, bank
  decouple+move only as verified pairs with net reduction (`moduleMove.ts:520-603`).

## 4. What RGI can DRIVE vs must REIMPLEMENT

**Drive (feed targets, reuse the TS engine):** every gate is command-string
driven — RGI's graph can emit `move cluster X in <file>`, `move X in <file>`,
`extract collaborator X from <file>`, `method-object X in <file>`,
`decouple X in <file>`, `extract X in <file>`, `rename X to Y in <file>`,
`converge <file>`. The engine re-derives structure and never trusts a caller's
target list — RGI only needs to *select targets*, not supply spans/plans.

**Reimplement in Python (if RGI runs standalone, without the TS executor):**
1. **Verification** — `verifyPatch` semantics (shadow worktree, baseline-diff,
   auto-revert). The executor is the only thing that does this.
2. **TS ground-truth types** — `resolveTypes` feeds every T0 decouple; no Python
   analogue exists.
3. **TS language-service refactor ops** — `rename`/`encapsulate`/`references`
   ref-sets; Python has nothing equivalent in-repo.
4. **The fence** — containment + call-set preservation is tree-sitter-js-specific
   (`fence.ts:61,157` — non-JS is a no-op pass).
5. **The analysis primitives** — `collectCoupling`, `clusterModule` (Louvain),
   `computeExtractSignature`, `clusterCtxFields` — port cleanly to py-tree-sitter.

## 5. Tested vs untested

**Well-tested (vitest):** `extractModule.test.ts` (89), `extractFunction.test.ts`
(22), `extractCollaborator.test.ts` (45), `moveAlonePy.test.ts` (22),
`methodObjectPy.test.ts` (13), `methodObject.test.ts` (8), `clusterMovePy.test.ts`
(5), `clusterModulePy.test.ts` (4), `clusterCtxFieldsPy.test.ts` (6),
`extractCollaboratorPy.test.ts` (4), `fence.test.ts` (22), `genDecouple.test.ts`
(6), `fileMove.test.ts` (7), `verifyChange.test.ts` (10), `filePlan.test.ts` (10),
`convergeSweep.test.ts` (5), sweep tests (extract/move/tsc).

**Thinly tested / untested:**
- `gates/decouple.ts` itself (the gate) — no direct test file; its generative loop
  (reanchor, coder-iterate, fence-in-loop) is untested.
- `gates/moduleMove.ts` gate wiring — only `moveImpact.test.ts` (3) touches it.
- Python gate branches (py method-object/cluster-move/extract-collaborator chat
  paths) — untested (builders tested, gate dispatch not).
- Executor-side `verifyPatch`/`computeRefactor`/`resolveTypes` — not in repo tests.
- `verifyChange.ts` deterministicExtract with a real TS compiler — only
  `extractTscSweep.test.ts` (3).

**Bottom line:** the deterministic T0 engine is mature, heavily unit-tested,
tree-sitter-based, and language-dispatched (TS + py mirrors). The thin, untested
layer is the gate wiring and anything requiring the local TS executor.
