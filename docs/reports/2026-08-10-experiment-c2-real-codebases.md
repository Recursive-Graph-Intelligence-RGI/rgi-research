# Experiment C2: Real-Codebase Replication

*Pre-registered 2026-08-10, BEFORE any real-target run. This document is
the falsification contract: it is written so the experiment can kill its
own hypothesis. C1 (`2026-08-09-experiment-c1-complexity-scaling.md`)
proved the mechanism on synthetic generated apps; C2 is the field test
C1's limitations section promised.*

## Hypothesis

> RGI's recall and cost advantages, proven on synthetic apps (8→128
> files, C1 post-fix: rgi ≥ 0.927 at every level, 4 calls vs fixed's
> 128 at L5), hold on real, messy open-source Python code with known
> vulnerabilities — scored independently of the architecture.

## Language scope (decided pre-run, binding)

- The perception layer (`rgi/perception/code_parser.py`), baseline,
  fixed workflow, and tools are **Python-only and `ast`-based**; every
  file enumeration is `glob("*.py")`. Java (OWASP Benchmark) and JS
  (Juice Shop) are OUT: ingesting them means a new parser grammar, not
  a config change. Registered as C3 scope.
- **C2 harness delta (the only one, pre-registered):** `glob("*.py")` →
  `rglob("*.py")` at the five call sites (parser, baseline, fixed,
  registry ×2, engine coverage sweep), because real repos are nested.
  On C1's flat targets rglob ≡ glob; the delta is validated by
  re-running one C1 level (numbers must reproduce within seed noise)
  BEFORE C2 starts, then frozen. Any further change mid-series
  invalidates the run (C1 rule 4 inherited).

## Targets (ordered by file count; pinned commits recorded in meta)

| level | target | ~.py files | ground-truth source |
|-------|--------|-----------|---------------------|
| R1 | vulpy (`bad/`) | 18 (measured) | RealVuln labels pinned to our checkout + README (36) |
| R2 | dvpwa | 21 (measured) | RealVuln + README vuln list (26) |
| R3 | aiohttp @ v3.9.1 | 132 (measured) | NVD/GitHub advisories, 3.9.x-fix window (3) |
| R4 | OWASP PyGoat | 80 (measured) | RealVuln labels pinned to our checkout (78) |

*Measured-count note (2026-08-10): checkout measurement swapped the
estimated size order — pygoat (80) is smaller than aiohttp (132). Run
order follows measured file count: R1, R2, R4, R3. Ground-truth entry
counts (36/26/78/3) are the RealVuln/advisory counts at our pinned
commits, which differ from the pre-run estimates (~54/22/~70/handful);
the contract rule "prefer the documented list over hitting numbers"
governs. aiohttp CVE window: only CVEs with a 3.9.x patch release are
included (CVE-2024-23334, -27306, -30251); advisory ranges without a
3.9.x fix are excluded, reasoning in meta.*

Reserve: dsvpwa (32 labels) if any target proves un-runnable.
Disclosure registered pre-run: R1/R2/R4 are *purposely vulnerable* —
real code, but written-to-be-broken; only R3 is unmodified production
OSS. R3's ground truth is sparse (a handful of CVEs), so its recall is
coarse-grained and it is graded as a qualitative anchor, not averaged
into the primary recall metric. n_files measured at checkout, reported,
not tuned to fit the table.

## Ground truth construction (scoring unchanged)

`score_report_full` runs UNCHANGED. Per target,
`benchmarks/real/<name>/ground_truth.json` in the C1 schema:
`{"vulns": [{"id": ..., "terms": [...]}], "meta": {"repo", "commit",
"n_files", "source_urls"}}`. Each documented vuln class maps to one
entry; `terms` = the vuln-class keyword plus synonyms a finding could
plausibly use (e.g. `["sql injection", "sqli"]`, `["xss", "cross-site
scripting"]`, `["path traversal", "directory traversal", "lfi"]`).
Term lists are written from the documentation/CVE text BEFORE any run
— never from RGI output. Registered scoring weakness (inherited from
C1, sharper on real code): substring matching misses findings that
describe a vuln without a listed term. Mitigation: post-run, all
false-negative ground-truth entries are manually audited against raw
cell reports (cells are preserved per the Run-12 protocol) and the
audit is published alongside the keyword scores.

## Matrix

- Levels: R1–R4 (real projects are fixed artifacts; no seeds).
- Repetitions: n=1 per project × condition, disclosed — the honest
  variance in C1 was across generated instances; that variance does not
  exist here. n=3 runs added ONLY at cells decisive for the verdict
  (rgi vs single gap < 0.1 recall), per C1's follow-on precedent.
  Prompt-order shuffling rejected: it perturbs RGI's own planning, so
  it measures the harness, not the claim.
- Conditions: rgi / single / fixed, identical scoring.
- Models: qwen2.5:1.5b, nemotron-3-nano:4b, qwen2.5:7b (C1 matrix).
- Harness limits: STANDARD — `max_total_nodes=200`, `max_llm_calls=60`
  (env `RGI_C1_MAX_NODES` / `RGI_C1_MAX_LLM_CALLS` left at defaults).
  Caps are the break detector; spawn rejections are data.
- num_ctx stays 4096 (frozen to C1 main-series state; the C1 8k
  side-series showed single improves at 8k — noted, not adopted).
- Runner: a `run_real.py` clone of `run_complexity.py` (targets list
  instead of generator, level = target name), progressive JSON writes,
  cell-level exception containment, raw cell reports preserved.

## Metrics (per cell, as C1)

recall, precision (deduped, score_report_full), graphs spawned, max
depth/width, total cells, LLM calls, tokens, corrections, verification
ops, spawn rejections, execution failures, wall time.

## Falsification rules (binding)

1. **Performance rule:** if rgi mean recall across R1–R4 is not
   materially above single's (gap < 0.1) — i.e. the C1 advantage
   vanishes on real code — the performance claim is FALSIFIED for real
   codebases.
2. **Kill-shot:** if rgi recall collapses to single-baseline level on
   ≥ 3 of 4 targets WHILE topology metrics are healthy (graphs/cells
   grow with file count as in C1), the conclusion is registered
   verbatim: the neurons cannot judge real code and topology does not
   rescue them.
3. **Mechanism rule:** if graphs spawned / cells do not increase from
   R1 to R4, the mechanism claim is FALSIFIED regardless of recall.
4. **Break point:** the first target (file-count order) where rgi ≤
   fixed is reported as the real-code break point, with the audit-trail
   signature (caps vs planner collapse vs node errors) identified.
5. **Infra-vs-topology disclosure:** crashes, OOMs, and timeouts are
   recorded as `status="error"` cells and disclosed in the verdict —
   never deleted, never silently re-run into the means. If an error
   pattern turns out to be a harness bug (C1 errata precedent), the fix
   triggers a full re-run of affected cells with pre/post data kept.
6. **No silent tuning:** after the rglob delta is validated, harness,
   prompts, ground truth, and scoring are frozen for the series.

## Expected outcomes (pre-registered reads)

- **Hypothesis holds:** rgi ≥ fixed ≥ single on R1–R4; the rgi–single
  gap widens from R1 to R4; rgi calls ≪ fixed's 1-call-per-file on
  R3/R4 (the C1 L5 efficiency gap repeats on real code).
- **Partial:** rgi wins on the purposely-vulnerable targets but not R3
  (subtle CVEs, sparse ground truth) — claim narrows to documented-
  vuln-class code; disclosed as narrowing, not victory.
- **Falsified:** rgi ≈ single across the matrix, or rgi ≤ fixed at R2
  with healthy topology.

## Cost / runtime estimate

Grounded in C1 7b cells (rgi 291–878s; fixed ~9.4s/file; single
15–104s): per model ≈ R1 8 min + R2 16 min + R3 29 min + R4 37 min
≈ 90 min. **Full n=1 matrix: 36 cells, ~4–6 h wall across 3 models**
(GTX 1660 6GB, sequential). Decisive-cell repetitions add ≤ ~2 h.
Runtime is reported per cell; overruns past 2× estimate are data
(registered as a cost-claim caveat), not grounds for deletion.

## Limitations (registered pre-run)

- n=1 per cell: real projects are singular; repetition plan above is
  the disclosed substitute for seeds.
- 3 of 4 targets are purposely vulnerable — "real mess" is only
  genuinely tested by R3; results are reported per-target, never only
  as a pooled mean.
- Keyword-substring scoring on real code (see Ground truth); the FN
  audit is part of the deliverable.
- Purposely-vulnerable apps over-represent textbook vuln classes our
  prompts and tools already name; R3 exists to counterweight this.
