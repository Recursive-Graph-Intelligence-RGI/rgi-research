# Experiment C1 — Full Results Matrix

Provenance: generated from `data/complexity_c1.json` (qwen2.5:1.5b), `data/complexity_c1_nemotron-3-nano_4b.json` (nemotron-3-nano:4b), and `data/complexity_c1_qwen2_5_7b.json` (qwen2.5:7b), commit 815f74a era. Each file holds 45 cells (5 levels L1–L5 × 3 seeds × 3 conditions); only cells with `status == "completed"` are aggregated here.

Compute disclosure: token counts **were** recorded in C1, but only for the **rgi** condition (`tokens_prompt` / `tokens_completion` in `topology_metrics`, populated by `rgi/reasoning/llm_client.py` via `rgi/cli.py`). The single/fixed baselines do not populate these fields — for them, LLM calls and wall time remain the compute proxy. Uniform token logging across all conditions is future work.

Levels: L1 = 8 files, L2 = 16, L3 = 32, L4 = 64, L5 = 128.

## qwen2.5:1.5b

| level | condition | n_completed | recall mean ± std | precision mean | calls mean | corrections mean | wall_s mean |
|---|---|---|---|---|---|---|---|
| L1 | rgi | 3 | 1.000 ± 0.000 | 0.896 | 11.0 | 0.0 | 53 |
| L1 | single | 3 | 0.417 ± 0.236 | 1.000 | 1.0 | 0.0 | 4 |
| L1 | fixed | 2 | 0.750 ± 0.250 | 0.500 | 8.0 | 0.0 | 33 |
| L2 | rgi | 3 | 0.792 ± 0.295 | 0.523 | 11.3 | 0.0 | 60 |
| L2 | single | 2 | 0.250 ± 0.125 | 1.000 | 1.0 | 0.0 | 6 |
| L2 | fixed | 2 | 0.688 ± 0.062 | 0.438 | 16.0 | 0.0 | 75 |
| L3 | rgi | 3 | 0.750 ± 0.354 | 0.219 | 12.3 | 0.0 | 83 |
| L3 | single | 3 | 0.271 ± 0.058 | 1.000 | 1.0 | 0.0 | 9 |
| L3 | fixed | 2 | 0.844 ± 0.031 | 0.484 | 32.0 | 0.0 | 110 |
| L4 | rgi | 3 | 0.646 ± 0.457 | 0.160 | 6.3 | 0.3 | 48 |
| L4 | single | 3 | 0.312 ± 0.178 | 1.000 | 1.0 | 0.0 | 13 |
| L4 | fixed | 1 | 0.875 ± 0.000 | 0.469 | 64.0 | 0.0 | 215 |
| L5 | rgi | 3 | 0.000 ± 0.000 | 0.000 | 1.0 | 0.0 | 14 |
| L5 | single | 3 | 0.000 ± 0.000 | 0.000 | 1.0 | 0.0 | 10 |
| L5 | fixed | 0 — no completed cells | — | — | — | — | — |

### qwen2.5:1.5b — rgi topology_metrics means

| level | n | graphs | graph_cells | max_depth | max_width | spawn_approved | spawn_inhibited | spawn_rejected | tokens_prompt | tokens_completion |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 | 3 | 10.7 | 30.3 | 2.0 | 4.3 | 9.7 | 1.3 | 2.0 | 8805.0 | 1554.0 |
| L2 | 3 | 11.3 | 32.3 | 1.7 | 4.0 | 10.3 | 1.3 | 0.7 | 13340.3 | 1548.3 |
| L3 | 3 | 12.7 | 37.3 | 2.0 | 5.0 | 11.7 | 1.3 | 0.7 | 24870.0 | 1786.0 |
| L4 | 3 | 7.7 | 29.0 | 1.7 | 4.0 | 6.7 | 0.0 | 1.0 | 11388.7 | 967.3 |
| L5 | 3 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 4.7 | 1714.3 | 151.3 |

## nemotron-3-nano:4b

| level | condition | n_completed | recall mean ± std | precision mean | calls mean | corrections mean | wall_s mean |
|---|---|---|---|---|---|---|---|
| L1 | rgi | 3 | 1.000 ± 0.000 | 0.860 | 23.7 | 0.0 | 491 |
| L1 | single | 3 | 0.667 ± 0.236 | 1.000 | 1.0 | 0.0 | 16 |
| L1 | fixed | 3 | 1.000 ± 0.000 | 0.542 | 8.0 | 0.0 | 132 |
| L2 | rgi | 3 | 1.000 ± 0.000 | 0.902 | 29.3 | 0.0 | 670 |
| L2 | single | 3 | 0.708 ± 0.156 | 1.000 | 1.0 | 0.0 | 22 |
| L2 | fixed | 3 | 1.000 ± 0.000 | 0.583 | 16.0 | 0.0 | 237 |
| L3 | rgi | 3 | 1.000 ± 0.000 | 0.810 | 30.7 | 0.0 | 938 |
| L3 | single | 3 | 0.521 ± 0.281 | 1.000 | 1.0 | 0.0 | 32 |
| L3 | fixed | 3 | 1.000 ± 0.000 | 0.604 | 32.0 | 0.0 | 507 |
| L4 | rgi | 3 | 1.000 ± 0.000 | 0.898 | 16.7 | 0.0 | 553 |
| L4 | single | 3 | 0.479 ± 0.053 | 1.000 | 1.0 | 0.0 | 31 |
| L4 | fixed | 3 | 1.000 ± 0.000 | 0.661 | 64.0 | 0.0 | 948 |
| L5 | rgi | 2 | 0.115 ± 0.053 | 1.000 | 1.0 | 0.0 | 41 |
| L5 | single | 3 | 0.076 ± 0.108 | 0.333 | 1.0 | 0.0 | 29 |
| L5 | fixed | 3 | 1.000 ± 0.000 | 0.510 | 128.0 | 0.0 | 1958 |

### nemotron-3-nano:4b — rgi topology_metrics means

| level | n | graphs | graph_cells | max_depth | max_width | spawn_approved | spawn_inhibited | spawn_rejected | tokens_prompt | tokens_completion |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 | 3 | 21.3 | 64.3 | 2.0 | 5.3 | 20.3 | 4.7 | 1.3 | 32349.3 | 3668.3 |
| L2 | 3 | 26.3 | 81.3 | 2.0 | 6.0 | 25.3 | 3.7 | 0.3 | 49989.0 | 4794.0 |
| L3 | 3 | 29.0 | 87.0 | 2.0 | 6.0 | 28.0 | 3.3 | 0.0 | 67377.7 | 4054.0 |
| L4 | 3 | 15.0 | 44.7 | 2.0 | 6.0 | 14.0 | 1.7 | 2.0 | 5347.7 | 2542.3 |
| L5 | 2 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 5.0 | 2293.5 | 219.5 |

## qwen2.5:7b

| level | condition | n_completed | recall mean ± std | precision mean | calls mean | corrections mean | wall_s mean |
|---|---|---|---|---|---|---|---|
| L1 | rgi | 3 | 1.000 ± 0.000 | 0.748 | 21.0 | 0.0 | 285 |
| L1 | single | 3 | 0.833 ± 0.118 | 1.000 | 1.0 | 0.0 | 15 |
| L1 | fixed | 3 | 1.000 ± 0.000 | 0.708 | 8.0 | 0.0 | 66 |
| L2 | rgi | 3 | 1.000 ± 0.000 | 0.708 | 30.3 | 0.0 | 513 |
| L2 | single | 3 | 0.708 ± 0.156 | 1.000 | 1.0 | 0.0 | 20 |
| L2 | fixed | 3 | 1.000 ± 0.000 | 0.542 | 16.0 | 0.0 | 123 |
| L3 | rgi | 3 | 1.000 ± 0.000 | 0.507 | 32.7 | 0.0 | 754 |
| L3 | single | 3 | 0.313 ± 0.088 | 1.000 | 1.0 | 0.0 | 25 |
| L3 | fixed | 3 | 0.979 ± 0.029 | 0.636 | 32.0 | 0.0 | 248 |
| L4 | rgi | 3 | 1.000 ± 0.000 | 0.707 | 4.0 | 0.0 | 155 |
| L4 | single | 3 | 0.708 ± 0.074 | 1.000 | 1.0 | 0.0 | 52 |
| L4 | fixed | 3 | 1.000 ± 0.000 | 0.583 | 64.0 | 0.0 | 565 |
| L5 | rgi | 3 | 0.000 ± 0.000 | 0.000 | 1.0 | 0.0 | 32 |
| L5 | single | 3 | 0.299 ± 0.094 | 1.000 | 1.0 | 0.0 | 104 |
| L5 | fixed | 3 | 0.993 ± 0.010 | 0.513 | 128.0 | 0.0 | 1203 |

### qwen2.5:7b — rgi topology_metrics means

| level | n | graphs | graph_cells | max_depth | max_width | spawn_approved | spawn_inhibited | spawn_rejected | tokens_prompt | tokens_completion |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 | 3 | 21.0 | 61.0 | 2.0 | 5.3 | 20.0 | 4.3 | 0.3 | 18287.3 | 2671.7 |
| L2 | 3 | 30.3 | 89.0 | 2.0 | 6.0 | 29.3 | 5.3 | 0.0 | 43763.7 | 4301.0 |
| L3 | 3 | 32.7 | 96.0 | 2.0 | 6.0 | 31.7 | 4.3 | 0.0 | 79554.7 | 4311.7 |
| L4 | 3 | 7.0 | 18.7 | 2.0 | 3.0 | 6.0 | 0.0 | 0.0 | 13271.0 | 735.3 |
| L5 | 3 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 6.0 | 1714.3 | 178.0 |

---

*Std is the population standard deviation (÷n) over the completed seeds (≤3 per cell), rounded to 3 decimals.*

Notes on missing / degenerate cells:
- 1.5b L5 fixed: 0 of 3 seeds completed (all errored) — shown as "no completed cells".
- 1.5b file overall: 9 of 45 cells errored (fixed L1/L2/L3/L4/L5 partial, single L2 partial); n_completed < 3 rows reflect that.
- 4b L5 rgi: 2 of 3 seeds completed (1 failed).
- L5 rgi collapse is real data, not an artifact: graphs = 1, max_depth = 0, spawn_rejected ≈ 5–6 — the spawn budget refused every child graph, so RGI degraded to a single-cell run (recall 0.0 for 1.5b/7b, 0.115 for 4b).
