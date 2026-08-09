# Experiment C1: Complexity→Topology Scaling at Constant Model Size

*Pre-registered 2026-08-09, BEFORE the benchmark generator was written.
This document is the falsification contract: it is written so the
experiment can kill its own hypothesis.*

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
