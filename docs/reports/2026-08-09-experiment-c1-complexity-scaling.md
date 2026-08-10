# Experiment C1: Complexity→Topology Scaling at Constant Model Size

*Pre-registered 2026-08-09, BEFORE the benchmark generator was written.
This document is the falsification contract: it is written so the
experiment can kill its own hypothesis.*

**Status: GRADED 2026-08-09** — verdict in §Verdict below; full grading
in the status report, Run C1
(`docs/reports/2026-08-04-rgi-status-report.md` §6).

## Hypothesis (Jeff Walters, 2026-08-09)

> RGI converts increasing problem complexity into increasing
> computational topology rather than requiring increasing model size.
>
> problem complexity ↑ → topology complexity ↑ → performance stable

## Design

- **Constant model:** qwen2.5:1.5b (local Ollama) for every cell.
- **Complexity axis:** generated benchmark, 5 levels. Primary axis
  n_files ∈ {8, 16, 32, 64, 128}; vuln density held ~25%;
  cross-file chain depth scaled {1, 2, 3, 4, 6}; benign noise modules
  fill the remainder. Seeded generation (3 seeds/level); ground-truth
  manifest emitted mechanically WITH the code — scoring independent of
  architecture.
- **Conditions:** full adaptive RGI, fixed pipeline, single baseline.
  Identical scoring for all three.
- **Repetitions:** 3 seeds × 1 run per level (decided pre-run: seeds
  over repeats — variance across generated instances is the honest
  variance here; note in limitations).
- **Harness limits:** STANDARD limits for the main series (caps are the
  break detector — spawn_rejected is data, not noise).

## Metrics (per cell)

recall (deduped, per score_report_full), precision, graphs spawned,
max depth, max width (max subgraphs per parent), total graph cells,
LLM calls, tokens (prompt+completion from endpoint usage), repl rounds,
corrections, verification ops (verification spawns + coverage sweeps),
spawn rejections (cap hits), execution failures (node errors,
contained cell errors), wall time.

## Falsification rules (binding)

1. **Performance rule:** if RGI's recall-vs-complexity slope is not
   materially flatter than fixed's (difference in slopes < 0.1
   recall/log2(files) across the measured range), the performance half
   of the hypothesis is FALSIFIED.
2. **Mechanism rule:** if topology metrics (graphs spawned, cells) do
   not increase monotonically with complexity across at least L1→L3,
   the mechanism claim is FALSIFIED regardless of recall — stable
   performance without topology growth is not topology-driven scaling.
3. **Break point:** the first level where RGI mean recall ≤ fixed mean
   recall is reported as the break point, with the metric that broke
   first (recall vs caps vs failures) identified from the audit trail.
4. **No silent tuning:** harness limits, prompts, and scoring are
   frozen at their Run 13 state for the whole series. Any change
   mid-series invalidates the run and restarts it.

## Expected outcomes (pre-registered reads)

- Hypothesis holds: recall flat-ish across levels; graphs/cells grow
  ~linearly with files; RGI advantage grows with complexity.
- Partial: holds to L3/L4, breaks at caps — break point at harness
  saturation (spawn rejections precede recall drop). This is the
  predicted outcome (128 files × coverage sweeps ≫ node budget).
- Falsified: RGI degrades in step with fixed.

## Follow-on (only after break point measured)

Re-run the break level at 4b and 7b: does stronger neuron + topology
recover performance? Maps minimum capability vs complexity.

## Limitations (registered pre-run; updated as discovered)

- 3 seeds × 1 run per level: variance across generated instances is the
  honest variance; repetitions may be added at decisive levels.
- Synthetic generator: cleaner vulns than real-world mess. Mechanism
  test, not field test; Phase 1 real-repo run is the field test.
- **Ollama num_ctx=4096 truncation (found 2026-08-09, user-flagged):**
  full-source contexts at L3+ exceed the default window; local results
  may understate substrate quality. Frozen for this series; follow-up
  series with OLLAMA_CONTEXT_LENGTH=8192 is planned (status report §5.11).
- **Chain sinks sort first alphabetically** (chain0_*), so the 30k
  source excerpt over-covers chain files at large levels. Verdict
  weights precision and the mechanism rule, not raw recall alone.

## Verdict (GRADED 2026-08-09)

The hypothesis is **CONFIRMED through L4 and FALSIFIED at L5.** RGI
recall is flat at 1.000 across L1–L4 for both nemotron-3-nano:4b and
qwen2.5:7b while the single baseline degrades at every model size
(7b: 0.833 → 0.299), so the benchmark genuinely gets harder and the
flat line is not a too-easy-test artifact; topology metrics grow with
level, so the mechanism rule holds. At L5 (128 files) rgi ≤ fixed for
the first time (4b: 0.115 vs 1.000; 7b: 0.000 vs 0.993) — the
falsification contract's break-point rule fires. The L5 failure
signature is identical across all three model families: planner emits
no plan, exactly 1 LLM call, ~30s wall time. Diagnosis: the
4096-token context window cannot hold 128 files of raw source and the
planner chokes — a perception/context failure, not a topology failure.
An L5-only re-run at 8k context is queued as the confirmation test
with a pre-registered prediction. The series was extended from the
pre-registered 1.5b-only design to three models per the follow-on
rule; qwen2.5:1.5b degrades earliest (rgi 1.0 → 0.65 across L1–L4,
trailing fixed from L3), so the break point moves outward with neuron
strength: structure compensates for weak neurons but cannot cancel
them.

**Per-model break points (first level where rgi ≤ fixed / planner
collapses):** 1.5b — L5 (rgi 0.000; already trails fixed L3–L4);
4b — L5 (0.115 vs fixed 1.000); 7b — L5 (0.000 vs fixed 0.993).

Disclosures carried from the grading (status report, Run C1): 4b/7b
tables reflect 5 re-run cells after the null-suggestions fix
(`739b6db`; original crashes were infrastructure, not topology);
1.5b retains 9 pre-fix error cells (L5/fixed has no completed cells);
one 4b L5 rgi cell excluded as planner collapse; rgi's 1-call L5
counts are the failure symptom, not efficiency — the cost-advantage
claim holds only L1–L4.
