# RGI — Status Report & Evaluation Framework

**Date:** 2026-08-04 (covers v0.1 build + v0.2 testing sprint)
**Status:** v0.1 COMPLETE; v0.2 testing sprint COMPLETE; embeddings + spawn-cap merged (72/72 tests green)
**Next gate:** 100+ file benchmark (requires embedding-based activation)

---

## 1. What Exists Right Now

A working recursive graph intelligence prototype at `/home/jeff/projects/rgi`.
One CLI command runs the full system:

```bash
python -m rgi analyze sample_project --objective "Analyze authentication security" --mock
python -m rgi compare sample_project --objective "Analyze authentication security" --mock
```

### Verified behavior (evidence, not claims)

| Capability | Evidence | Where |
|---|---|---|
| Autonomous recursive spawning | 5 subgraphs from one CLI input | `report.json`, `test_engine.py` |
| Topological self-correction | Verification graph challenges 0.6-confidence JWT finding → NEW execution graph born → original node transits CORRECTING → COMPLETED at 0.84 | `test_self_correction.py`, audit log `correction_completed` |
| Harness hard limits | Depth cap proof: chain of 5 spawn attempts with max_depth=2 → 1 created, rejections audited | `test_recursive_spawn.py` |
| LLM budget binds ALL node types | Post-review fix: verification challenges gated; refusal audited, zero calls made | `test_verification_challenge_refused_when_budget_exhausted` |
| Structured graph memory | 7+ typed entities with dependency edges persisted | `data/knowledge_graph.json`, `test_perception.py` |
| Full auditability | Every spawn/deny/correction/run event in `data/audit.jsonl` | committed `report.json` execution_log |
| Baseline control condition | Single-agent (1 call, no graphs) vs RGI comparison | `compare.json`, `tests/test_baseline.py` |

**Live-run numbers to beat (mock-mode reference):** 6 LLM calls, 29 findings, 1 correction, depth 2, aggregate confidence 0.842, sub-second wall time.

### What is NOT yet proven

The research hypothesis — *recursive graph decomposition outperforms a monolithic
agent* — is untested. The mock LLM is scripted on both sides; the demo proves
the machinery works, not that real reasoning benefits. The experiment is built
and waiting for a live key. This distinction is load-bearing for the paper.

---

## 2. The Grading System (Four Tiers)

Each tier gates the next. A tier's score is meaningless if a lower tier is red.

### Tier 0 — Mechanical Integrity (CI, pass/fail, deterministic)

*What it proves: the system is safe and does what the code says.*

| # | Metric | Threshold | Current |
|---|---|---|---|
| 0.1 | Test suite | 100% green, zero warnings | ✅ 46/46 |
| 0.2 | Depth violations in any run | 0 | ✅ proof-tested |
| 0.3 | Node budget violations | 0 | ✅ proof-tested |
| 0.4 | LLM calls exceeding cap (any node type) | 0 | ✅ proof-tested |
| 0.5 | Unaudited spawn/correction/deny decisions | 0 | ✅ by construction |
| 0.6 | Run termination (no infinite loops) | always, ≤ 300s | ✅ stagnation guard + cap |

**Rule: Tier 0 must be 6/6 in CI on every commit, forever. Any regression blocks merge.**

### Tier 1 — Functional Quality (live LLM, per-run scoring)

*What it proves: the system produces correct, calibrated analysis with a real model.*

Ground truth for `sample_project` (planted, known exactly):

| ID | Vulnerability | File |
|---|---|---|
| V1 | JWT decode without expiration verification | auth.py |
| V2 | Hardcoded weak secret (SECRET_KEY) | auth.py |
| V3 | Session store with no timeout/age check | session.py |
| V4 | Plaintext password comparison | login.py |
| V5 | Hardcoded API key + DB credentials | config.py |

Metrics per live run:

| # | Metric | Formula | Target |
|---|---|---|---|
| 1.1 | Vulnerability recall | planted vulns found / 5 | ≥ 4/5 |
| 1.2 | Precision | true findings / all findings | ≥ 0.8 |
| 1.3 | Confidence calibration | mean \|stated confidence − correctness\| across findings | ≤ 0.15 |
| 1.4 | Correction efficacy | corrections that raised a finding's confidence AND were confirmed correct | ≥ 1 real correction, 0 spurious |
| 1.5 | Budget discipline | LLM calls used | ≤ 20 (hard), ≤ 12 (good) |
| 1.6 | Latency | wall time on 4-file target | ≤ 5 min (hard), ≤ 60s (good) |

Scoring: 1.1–1.4 are quality gates (any miss = investigate, not necessarily fail);
1.5–1.6 are hard gates (miss = fail).

### Tier 2 — Comparative Advantage (the actual hypothesis)

*What it proves: topology beats a monolithic neuron on the same task, same tools, same budget.*

Conditions (all on the same live model, same objective):

- **Control A — Monolithic:** `run_baseline` (exists). 1 call, full code in context.
- **Control B — Fixed workflow (build in v0.2):** same tools and prompts as RGI, but a hardcoded sequential pipeline (parse → analyze jwt → analyze session → report). No spawning, no verification, no correction. This isolates *adaptive topology* from merely *having tools*.

| # | Metric | Comparison | Win condition |
|---|---|---|---|
| 2.1 | Recall delta | RGI recall − A recall, RGI recall − B recall | > 0 vs at least one control |
| 2.2 | Calibration delta | A/B calibration error − RGI calibration error | > 0 |
| 2.3 | Correction value | findings only correct because of the verification→correction path | ≥ 1 |
| 2.4 | Cost ratio | RGI calls / A calls | ≤ 3× (more calls must buy measurable quality) |

**The honest risk, stated in advance:** if a strong model's single call catches
all 5 planted vulns, 2.1 fails on this toy target. That is a *finding*, not a
failure — it means topology pays off at higher task complexity, and Tier 3
becomes the decisive tier.

### Tier 3 — Generalization (held-out targets)

*What it proves: the system wasn't tuned to its demo.*

| # | Test | Pass condition |
|---|---|---|
| 3.1 | Unseen vulnerable app (new file set, different vuln classes — SQL injection, path traversal, XSS) | recall ≥ 0.7 without changing any code or prompts |
| 3.2 | Larger codebase (20+ files, multi-file vulns spanning modules) | completes within budget; finds ≥ 1 cross-file vuln the monolithic control misses |
| 3.3 | Non-security objective ("map the data flow of this codebase") | completes with coherent structured output; proves the architecture isn't security-specific |

### Tier 4 — Plasticity (v0.3 only)

*What it proves: the system gets better with experience — the claim no fixed-workflow framework can make.*

| # | Test | Pass condition |
|---|---|---|
| 4.1 | Same objective, 2nd run | measurably faster activation / fewer LLM calls, from persisted pathway data alone |
| 4.2 | Edge-weight learning | successful correction pathways have stronger weights in run N+1; failing pathways weaker |
| 4.3 | Learned spawn policy (stretch, GNN-style) | spawn decisions outperform the rule-based policy on held-out tasks, trained on ≥ 1k logged pathways |

### Scorecard template (fill per experiment)

```
Date / model / target:
Tier 0: _/6   Tier 1: 1.1 _  1.2 _  1.3 _  1.4 _  1.5 _  1.6 _
Tier 2: 2.1 _  2.2 _  2.3 _  2.4 _
Tier 3: 3.1 _  3.2 _  3.3 _
Verdict + notes:
```

---

## 3. Integration Path to Full-Scope Architecture

v0.1 was built as the reference implementation of the larger design. The seams
are concrete, not aspirational:

| Full-scope component | v0.1 seam | Integration work |
|---|---|---|
| **FortSignal enforcement** | `GovernanceGate` protocol + `FortSignalGate` stub (`rgi/core/governance.py`); audit schema already mirrors receipts (event/reason/graph_id) | Implement `FortSignalGate.check()` mapping spawn/tool/LLM actions to challenge/verify; receipts into audit.jsonl. Phase 2, ~2-3 days |
| **Real spreading activation (v0.2)** | `ActivationEngine.propagate()` interface is brain-shaped (seed → propagate → threshold); engine consumes only `{node_id: score}` | Swap internals: multi-hop with attenuation, activation decay over time, salience from world-model topology. No consumer changes |
| **Parallel loops + cross-inhibition (v0.2)** | Sibling `asyncio.gather` exists; audit event bus exists | Add a signal channel on Harness: verification anomaly → inhibit running execution graph; execution feedback → excite verification |
| **Plasticity / Hebbian learning (v0.3)** | `LearningEngine.record_pathway()` already logs objective→topology→outcome per graph per iteration — the training set is accumulating NOW | Edge-weight updates from pathways; activation engine reads weights (interface already passes `edge.weight` through propagation) |
| **Inhibition-default harness (v0.3)** | All limits are centralized in `request_subgraph_spawn` + `governance_check` | Invert stance: default-allow with inhibitory signals; limits become inhibition rather than permission |
| **Multi-model neurons (Phase 2)** | `reason(task, context) -> dict` interface; mock/real interchangeable; provider by env | Client registry: different node types routed to different models (cheap model for TOOL-adjacent reasoning, strong model for verification) |
| **Protocol spec (Phase 2)** | Pydantic models serialize cleanly to JSON (`model_dump_json` used in persistence) | Freeze G=(V,E,S,P) schema as language-agnostic protocol document |
| **Learned spawn/activation policies (v0.3+, GNN)** | Spawn approval and activation are isolated functions with logged inputs/outputs | Train on `data/pathways.json` once ≥ 1k runs logged |

**What would NOT survive integration unchanged** (known, deliberate): keyword
activation internals, regex-based tools, JSON-file persistence, single-process
execution. These are v0.1 simplifications documented in the spec's non-goals.

---

## 4. Known Limitations (carried from final review triage)

- ~~No exception containment around child `asyncio.gather`~~ — FIXED (readiness task).
- Report findings are duplicated (~4×) and directory-mode line numbers lack filenames. Report hygiene, v0.2.
- ~~`verify_findings` passes empty context~~ — FIXED (readiness task).
- ~~Real client returns unvalidated JSON~~ — FIXED (readiness task).
- Sample project is a toy target (4 files, planted vulns). Tier 3 exists precisely because of this.

### 4.1 World-model seeding threshold (diagnosed in live Run 2, OPEN)

**Symptom:** the root planning graph's first pass returned confidence 0.2 with
reasoning "world-model is empty," forcing a verification → correction cycle to
recover. The architecture self-healed (the best possible advertisement), but a
correct first pass would have saved 2 LLM calls and a full correction cycle.

**Root cause (code-level):** `rgi/cli.py` primes `root.memory_snapshot["world_model"]`
with knowledge-graph entities scoring **> 0.5** from `ActivationEngine.propagate()`.
The keyword seeder (`rgi/memory/activation.py`) scores `hits/len(keywords) + 0.3`
when any query keyword matches node content. Objective "Analyze authentication
security" yields keywords {analyze, authentication, security}; entity contents
like "Module config in config.py" or "Class LoginHandler in login.py: methods: [...]"
match **zero** keywords (they say "auth", "login", "config" — never "authentication"
or "security") → score 0.0 → snapshot empty or near-empty.

So the planner was grounded on paper (Run 2 prompt fix) but starved by seeding:
the vocabulary mismatch between objective language and code-entity language.

**Why it matters:** this is THE v0.2 spreading-activation problem in miniature.
Attention that depends on exact keyword overlap between query and entity text
is brittle; brains solve it with association (login ↔ authentication), which is
what embeddings or synonym expansion approximate.

**Candidate fixes (pick in v0.2):**
1. Synonym/alias expansion at seed time (static map: auth/login/token/jwt/session ↔ authentication/security). Cheap, keeps zero deps.
2. Lower the world-model priming threshold for `memory_snapshot` (e.g. > 0.3) and let the graph-internal threshold stay 0.5. One-line, partial.
3. Seed from the security-tool vocabulary instead of the raw objective (tools already know the domain keywords).
4. Embedding-based seeding (deferred from v0.1 spec) — the real fix, adds an embedding dependency; matches the v0.2 "real spreading activation" roadmap item.

Also note: propagation only travels knowledge-graph edges, and the sample graph
is sparse (few cross-module edges), so propagation cannot rescue zero-seeded
entities today.

## 5. Immediate Next Actions (ordered)

1. ~~Live-run readiness~~ — DONE (merged `d99dfba`).
2. ~~First live run + grounding fixes~~ — DONE (Runs 1–2 in §6; merged `0929fbd`).
3. ~~World-model seeding fix~~ — DONE (synonym expansion, §4.1 candidate 1; merged on testing sprint branch).
4. ~~Control B + held-out target + eval runner~~ — DONE (v0.2 testing sprint: `fixed_workflow.py`, `benchmarks/vuln_app_2`, `rgi eval` matrix).
5. ~~Live matrix grading~~ — DONE (Runs 3–4 in §6 scorecard; ceiling effect on both targets).
6. GitHub org remote + push (needs org name).
7. ~~Embeddings for seeding~~ — DONE (§4.1 candidate 4; merged `df2e7e2` + `82980df`,
   OpenAI-compatible + offline hash provider, `--embed` / `RGI_EMBED_BASE_URL`).
8. ~~Spawn-round cap~~ — DONE (`c39cb65`; Run 5 diagnosis: chatty small models
   re-seed spawn suggestions every merge until the graph dies `failed`).
9. **Small-model context-pressure matrix** (IN PROGRESS): re-run vuln_app_3 ×
   3 conditions × 3 runs on a weak local model post-spawn-cap → record as Run 5
   in §6. Run 4 showed the discriminating variable is context pressure, not file
   count; a weak model creates that pressure without a 100+ file benchmark.
10. v0.2 report hygiene: findings dedup, per-file line attribution.

---

## 6. Live Experiment Log (DeepSeek `deepseek-chat`, 2026-08-04)

### Run 1 — pre-grounding (v0.1 + readiness)

```
Tier 0: 6/6 ✅ (50 spawn rejections logged, limits held under real load)
Tier 1: recall 2/5 ❌ | precision low ❌ | calibration ❌ (0.75-confident
        "no issues" on vulnerable module) | corrections 0 ❌ | calls 18 ⚠️
Tier 2: baseline 4/5 @ 1 call vs RGI 2/5 @ 18 calls — BASELINE WINS ❌
Verdict: hypothesis FAILS as scaffolded. Diagnosis: (1) ungrounded planning
(hallucinated topics), (2) execution reasoning never saw code, (3) spawn
proliferation starved verification.
```

### Run 2 — post-grounding (v0.2 grounding fixes)

```
Tier 0: 6/6 ✅ (rejections 50 → 8; salience gate effective)
Tier 1: recall 5/5 ✅ | precision high (heavy duplication, all true) ✅ |
        calibration ✅ (0.2 on empty-snapshot pass was honest) |
        corrections 1 REAL ✅ (verification fired on 0.2-conf planner →
        strict re-analysis 0.95 drove successful decomposition) |
        calls 13 (hard ✅, good-gate ≤12 missed by 1) ⚠️
Tier 2: RGI 5/5 vs baseline 4/5 @ 0.97 — RGI WINS on recall ✅;
        baseline confidently incomplete (missed config secrets);
        cost ratio 13:1 fails ≤3× gate ⚠️ (topology buys quality with calls)
Verdict: system is now capable of the experiment. n=1, toy target, one
model — hypothesis NOT yet confirmed. Next: Tier 3 held-out targets,
Control B (fixed workflow), and a look at why root world-model seeding
was empty on first pass (activation threshold).
```

### Run 3 — live matrix (2 targets × 3 conditions × 3 runs, DeepSeek)

```
Tier 0: 6/6 ✅ (18/18 cells completed, exit 0, budgets held)
Tier 1: RGI recall 1.000 on both targets ✅ | calls 13–14 ⚠️ (hard gate pass,
        good gate miss) | corrections 0 across ALL 6 RGI runs — mechanism
        never fired because nothing needed correcting (by design, but the
        signature capability is UNTESTED at this difficulty)
Tier 2: sample_project: RGI 1.000 = fixed 1.000 > single 0.800 — TIE vs
        Control B at 3× the cost ❌
        vuln_app_2 (unseen): ALL conditions 1.000 — ceiling effect,
        zero discrimination ❌
Tier 3: vuln_app_2 did not discriminate — single-shot one-shot it too ❌
Verdict: CEILING EFFECT. Hypothesis untestable at this difficulty — neither
confirmed nor refuted. Topology buys nothing and costs 3–13× when the model
one-shots the task. Decisive next experiment: a 15–20 file target with
CROSS-FILE vulnerabilities (taint flow, secret defined here/misused there,
auth bypass in a sibling endpoint) where single-pass and per-module
pipelines structurally cannot connect evidence.
```

### Run 4 — decisive hard-target matrix (vuln_app_3: 15 files, 5 cross-file vulns)

```
Tier 0: 6/6 ✅ (9/9 cells completed; per-target budgets 120 nodes/40 calls
        held — RGI used 30)
Tier 1: RGI recall 1.000 ✅ | calls 30/40 ⚠️ | corrections 1 of 3 runs ✅ —
        FIRST live correction: verification fired on an under-confident pass,
        strict re-analysis completed at 0.9, aggregate 0.897. The signature
        mechanism works with a real model when the problem warrants it.
Tier 2: rgi 1.000 = fixed 1.000 = single 1.000 — CEILING AGAIN ❌
        The single-shot baseline connected all 5 cross-file chains in ONE
        call. 15 small files (~few KB) fit comfortably in a frontier model's
        context; there is nothing for topology to connect that the model
        doesn't already hold.
Verdict: pre-registered outcome "everything ties again." Hypothesis
unconfirmed at every tested scale. The discriminating variable is CONTEXT
PRESSURE, not file count: topology should pay when the problem exceeds what
one call can hold — 100+ files / 50k+ LOC — which requires the v0.2/v0.3
attention machinery (real activation) to even attempt. At small scale the
architecture's honest value today is the safety/audit layer and the live
self-correction, not recall.
Cost note: RGI spent 30 calls to match what 1 call achieved. At small scale,
topology is a tax; the bet is that it becomes insurance at large scale.
```

### Run 5 — small-model context-pressure matrix (vuln_app_3, local Ollama)

**Model:** `nemotron-3-nano:4b` (local, free; original partial run used an
unrecorded small model — methodology bug, fixed here). RGI condition ran with
`--embed` (nomic-embed-text) after keyword seeding produced a zero-entity
world model for the generic objective (§4.1 confirmed live: strong models
improvise a decomposition anyway; a 4B model answers "no code provided" and
finishes in 1 call). Fixes landed mid-run: per-graph spawn-round cap
(`c39cb65`), configurable LLM timeout (`854f67f`), empty-key auth header
(`f9d434e`).

```
Tier 0: FAILURES — 3/3 RGI runs status "failed" on time_limit_exceeded
        (harness max_seconds=300). Controls have NO equivalent limit:
        baseline/fixed never run under the harness. Asymmetric budget —
        see fairness note below.
Tier 1: rgi recall 0.467 (0.6/0.2/0.6) ❌ | calls 15.7 | corrections 0 ❌
Tier 2: fixed 0.800 (stable 0.8×3) > single 0.600 (1.0/0.2/0.6)
        > rgi 0.467 — RGI LOSES to both controls at this pressure level ❌
Verdict: hypothesis still unconfirmed — and this time the loss is
informative, not a ceiling. Three distinct problems, ranked by how much
they explain:
  1. TIME-LIMIT ASYMMETRY (experimental fairness): RGI died at 300s
     mid-expansion on every run; the controls were never at risk of the
     same death. Failing runs scored on partial findings. Fix: make the
     time budget explicit per condition (configurable max_seconds), or
     enforce an equal wall-clock budget on controls.
  2. SPAWN ECONOMICS (architecture): the per-graph round cap works but
     recursion routes around it — 13–22 graphs/run, each with its own
     2-round budget. A weak model's noisy decompositions multiply graphs
     faster than they add findings. Fix candidate: GLOBAL spawn/node
     budget enforced at the spawn gate (model-agnostic — a property of
     the run, not the model). NOTE: max_total_nodes=50 was configured
     yet 22 graphs spawned — the existing global limit does not bind at
     the spawn gate.
  3. ZERO CORRECTIONS, EVERYWHERE: verification never fired on any
     condition, including runs containing visibly wrong findings
     ("deserialize is safe" on a target with a pickle vuln). The
     signature mechanism from Run 4 did not engage with a weak model.
Bright spots vs the pre-fix partial run (unknown small model, artifacts
in docs/reports/run5-small-model/): rgi recall 0.333 → 0.467 and the
crash mode changed from spawn-until-max_iterations to clean
time-limit termination with 68–91 findings collected per run.
Single-shot variance (1.0/0.2/0.6) vs fixed's stability (0.8×3) is
itself a result: on weak models, ANY structure beats none — the open
question is whether ADAPTIVE structure can beat fixed structure.
Next data points (in order): configurable max_seconds re-run (isolate
fairness), global spawn budget (isolate economics), then the model
ladder (nemotron-4b → qwen2.5:7b → DeepSeek) to map the crossover.
```

### Run 6 — model ladder step 1: qwen2.5:7b, same 300s budget

**Model:** `qwen2.5:7b` (local Ollama, GTX 1660 Super), `--embed`
(nomic-embed-text), vuln_app_3, 3 runs × 3 conditions, spawn-round cap in
force. Pre-registered expectation: if Run 5's loss was mostly model
weakness, recall should rise; if it was mostly the 300s asymmetry, roots
should still die on `time_limit_exceeded`.

```
Tier 0: FAILURES — 3/3 RGI runs status "failed", ALL on
        time_limit_exceeded at 300s (audit trail confirms; zero
        spawn_inhibited/stagnation deaths). Spawn-cap fix holds: the
        Run 5 crash mode (spawn-until-max_iterations) is gone.
Tier 1: rgi recall 0.400 (0.4×3, stable) | calls 26.7 | corrections 0
Tier 2: fixed 0.533 (0.6/0.6/0.4) > rgi 0.400 > single 0.200 (0.2×3)
Verdict: BOTH Run 5 explanations confirmed, disentangled:
  1. Model strength matters: doubling-ish model size moved single-shot
     variance away (0.2×3 stable) and RGI recall became CONSISTENT
     (0.4×3 vs nemotron's 0.6/0.2/0.6 spread).
  2. The binding constraint is the wall clock, not the topology: with
     ~20-30s/call on this GPU, 26 calls cannot fit in 300s. The
     spawn-cap fix did its job — deaths are now clean time-limit
     terminations, audit-stamped.
Fix landed: RGI_MAX_SECONDS env (dae2c8c) — raises the harness wall for
local-model benchmarking without weakening the 300s demo default.
Run 7 (in flight): same matrix with max_seconds=3600 — the fairness
isolation re-run Run 5 prescribed. Prediction: roots complete; the
question is whether recall passes fixed's 0.533.
```

### Run 7 — fairness isolation: qwen2.5:7b with a 1-hour budget

Identical to Run 6 except `RGI_MAX_SECONDS=3600`. Pre-registered
prediction (recorded in conversation before the run): roots complete,
recall ~0.5, probably doesn't pass fixed; corrections the signal that
matters.

```
Tier 0: GREEN — 3/3 RGI runs status "completed". First fully-finished
        live local-model RGI runs. Time-limit asymmetry confirmed as
        Run 6's entire failure mode.
Tier 1: rgi recall 0.533 (0.4/0.6/0.6) | calls 27.3 | corrections 0
Tier 2: fixed 0.600 (0.6×3) > rgi 0.533 > single 0.200 (0.2×3)
Verdict: prediction exact. Fairness fix recovered +0.133 recall
        (0.400 → 0.533) — the Run 6 penalty was entirely truncated
        consolidation. But RGI still loses to fixed by 0.067 while
        spending 1.8× the LLM calls (27.3 vs 15.0). At 7B, adaptive
        topology is currently a tax you pay, not insurance you collect.
        Corrections STILL zero on every condition: the 7B never flags
        its own findings as under-confident, so verification never
        spawns — RGI ran as a recursive decomposer, not a
        self-corrector. That mechanism is the entire architectural bet,
        and it remains untested by any live run.
Run 8 (auto-chained): same matrix on DeepSeek V3 API — the strong-neuron
test. Decision rule pre-registered: corrections fire + recall ≥ fixed
→ pursue confidently; corrections fire + recall < fixed → v0.3 tuning;
corrections never fire → verification trigger redesign first.
```

---

*Bottom line: v0.1 is a verified machine with an honest grading framework and
concrete seams into the full architecture. The research claim is staged, not
won — and thanks to local Ollama models, the next data point costs nothing
but wall-clock time. Run 5 turned the "context pressure" hypothesis into a
controlled variable and produced the framework's first informative loss:
RGI's adaptive topology currently loses to a fixed workflow on weak models,
and the scorecard now says exactly why (time-limit asymmetry, per-graph cap
routed around by recursion, zero corrections).*
