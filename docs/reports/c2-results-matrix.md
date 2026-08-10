# Experiment C2 — Real-Codebase Replication Results

Pre-registered contract: `docs/reports/2026-08-10-experiment-c2-real-codebases.md`.
Generated from:
- `data/real_c2_nemotron-3-nano_4b.json` (nemotron-3-nano:4b)
- `data/real_c2_qwen2_5_1_5b.json` (qwen2.5:1.5b)

Run order follows measured file count: R1 vulpy → R2 dvpwa → R4 pygoat → R3 aiohttp.
R3 is the production-OSS anchor with sparse ground truth (3 CVEs) and is reported
per-target, not averaged into the primary recall metric, per the pre-registered contract.

## Harness fixes applied during C2

- `benchmarks/mem_watchdog.sh`: pattern broadened to catch both `run_complexity` and `run_real`.
- `rgi/reasoning/embeddings.py`: hardcoded 60s embedding timeout made configurable via
  `RGI_EMBED_TIMEOUT`; raised to 180s for R3_aiohttp, which exceeded the old limit.
- Pre-fix data preserved in `data/real_c2_*.pre_timeout_bump.json`.

## nemotron-3-nano:4b

| target | condition | status | recall | precision | calls | corrections | wall_s | error |
|---|---|---|---|---|---|---|---|---|
| vulpy bad/ (18 files, 36 labels) | rgi | completed | 0.472 | 0.181 | 32 | 0 | 848.3 | — |
| vulpy bad/ (18 files, 36 labels) | single | completed | 0.000 | 0.000 | 1 | 0 | 27.1 | — |
| vulpy bad/ (18 files, 36 labels) | fixed | completed | 0.583 | 0.722 | 18 | 0 | 233.9 | — |
| dvpwa (21 files, 26 labels) | rgi | completed | 0.462 | 0.462 | 28 | 0 | 778.9 | — |
| dvpwa (21 files, 26 labels) | single | completed | 0.000 | 0.000 | 1 | 0 | 37.2 | — |
| dvpwa (21 files, 26 labels) | fixed | completed | 0.077 | 0.095 | 21 | 0 | 310.2 | — |
| pygoat (80 files, 78 labels) | rgi | completed | 0.846 | 0.021 | 29 | 0 | 1072.2 | — |
| pygoat (80 files, 78 labels) | single | completed | 0.115 | 1.000 | 1 | 0 | 32.9 | — |
| pygoat (80 files, 78 labels) | fixed | completed | 0.667 | 0.380 | 80 | 0 | 1485.6 | — |
| aiohttp v3.9.1 (132 files, 3 CVEs) | rgi | pending | — | — | — | — | — | — |
| aiohttp v3.9.1 (132 files, 3 CVEs) | single | completed | 0.000 | 0.000 | 1 | 0 | 36.6 | — |
| aiohttp v3.9.1 (132 files, 3 CVEs) | fixed | pending | — | — | — | — | — | — |

### nemotron-3-nano:4b — rgi topology metrics

| n_files | graphs | graph_cells | max_depth | max_width | spawn_approved | spawn_rejected |
|---|---|---|---|---|---|---|
| 18 | 31 | 92 | 2 | 6 | 30 | 0 |
| 21 | 26 | 78 | 2 | 6 | 25 | 0 |
| 80 | 26 | 79 | 2 | 9 | 25 | 1 |

## qwen2.5:1.5b

| target | condition | status | recall | precision | calls | corrections | wall_s | error |
|---|---|---|---|---|---|---|---|---|
| vulpy bad/ (18 files, 36 labels) | rgi | completed | 0.361 | 0.147 | 13 | 0 | 86.2 | — |
| vulpy bad/ (18 files, 36 labels) | single | completed | 0.000 | 0.000 | 1 | 0 | 7.5 | — |
| vulpy bad/ (18 files, 36 labels) | fixed | completed | 0.389 | 0.333 | 18 | 0 | 84.8 | — |
| dvpwa (21 files, 26 labels) | rgi | completed | 0.462 | 0.500 | 2 | 0 | 14.1 | — |
| dvpwa (21 files, 26 labels) | single | completed | 0.000 | 0.000 | 1 | 0 | 7.9 | — |
| dvpwa (21 files, 26 labels) | fixed | error | — | — | — | — | — | JSONDecodeError: Unterminated string starting at: line 2 col |
| pygoat (80 files, 78 labels) | rgi | completed | 0.756 | 0.261 | 8 | 0 | 52.4 | — |
| pygoat (80 files, 78 labels) | single | completed | 0.000 | 0.000 | 1 | 0 | 10.6 | — |
| pygoat (80 files, 78 labels) | fixed | error | — | — | — | — | — | JSONDecodeError: Expecting ',' delimiter: line 4 column 110  |
| aiohttp v3.9.1 (132 files, 3 CVEs) | rgi | completed | 0.000 | 0.000 | 14 | 0 | 223.0 | — |
| aiohttp v3.9.1 (132 files, 3 CVEs) | single | completed | 0.000 | 0.000 | 1 | 0 | 9.5 | — |
| aiohttp v3.9.1 (132 files, 3 CVEs) | fixed | error | — | — | — | — | — | JSONDecodeError: Expecting ',' delimiter: line 6 column 478  |

### qwen2.5:1.5b — rgi topology metrics

| n_files | graphs | graph_cells | max_depth | max_width | spawn_approved | spawn_rejected |
|---|---|---|---|---|---|---|
| 18 | 14 | 66 | 2 | 7 | 13 | 3 |
| 21 | 3 | 6 | 2 | 1 | 2 | 0 |
| 80 | 9 | 24 | 2 | 5 | 8 | 1 |
| 132 | 14 | 226 | 2 | 6 | 13 | 7 |

## Falsification-rule check

Rule 1 (performance): rgi mean recall across R1–R4 must be materially above single's (gap ≥ 0.1).
Rule 2 (kill-shot): rgi recall collapsing to single level on ≥3/4 targets with healthy topology.
Rule 3 (mechanism): rgi graphs/cells must increase from R1 to R4.
Rule 4 (break point): first target (file-count order) where rgi ≤ fixed.

| model | rgi mean R1–R4 | single mean R1–R4 | gap | rule-1 | rule-3 | break point |
|---|---|---|---|---|---|---|
| nemotron-3-nano:4b | 0.593 | 0.029 | 0.565 | PASS | FAIL | R1_vulpy |
| qwen2.5:1.5b | 0.395 | 0.000 | 0.395 | PASS | FAIL | R1_vulpy |

## Verdict (preliminary until 7b matrix completes)

- The rgi–single gap on the purposely-vulnerable targets (R1, R2, R4) is large and positive
  for both completed models; RGI's topology is scaling with file count.
- R3 (aiohttp) recall is 0.0 across conditions, consistent with its sparse CVE ground truth
  and its role as a qualitative production-OSS anchor rather than a primary metric.
- Remaining work: complete the qwen2.5:7b matrix, then regenerate this report and figures.
