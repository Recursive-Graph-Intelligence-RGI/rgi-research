# RGI Strategy: Give Away the Recipe, Own the Restaurant

*Decided 2026-08-08, after Run 12 (first clean win: RGI 0.711 vs fixed 0.355
at qwen2.5:7b on vuln_app_hard).*

## Core position

The architecture, engine, harness, benchmarks, and evaluation corpus are
public (this repo). The moat is not the idea — ideas in this field are cheap
and independently reinvented within a year. The moat is:

- the **working system** with hard governance and a full audit trail
- the **evaluation discipline** — pre-registered predictions, controlled
  ablations, honest negative results (the scorecard in
  `docs/reports/2026-08-04-rgi-status-report.md`)
- the **finding** — topology as insurance for weak neurons (the crossover
  curve), timestamped and citable
- the **name and the community** that forms around the reference implementation

Frameworks die. Protocols live. Paradigms win.

## What is actually defensible (no overclaiming)

Spawning subgraphs and recursive decomposition exist (RLM, AutoGen,
LangGraph). Ours in combination, and by evidence:

1. **The crossover finding** — adaptive topology's value scales inversely
   with neuron strength; structure substitutes for parameters at the
   weak-model tier. (Ladder + pre-fix control in flight to confirm.)
2. **Audit-trail verification** — verification fires on what the system
   provably never read (coverage gate), not on LLM self-doubt, which we
   demonstrated does not work (zero self-triggered corrections across all
   live runs).
3. **The safety kernel** — depth/node/call/time limits enforced in code,
   every spawn decision audited. Nobody else in this space has one.

## IP posture

- **LICENSE is currently MIT.** Revisit deliberately: Apache 2.0 adds an
  explicit patent grant + retaliation clause, which protects contributors
  and users better at no cost to openness. Decision point: before the
  arXiv preprint.
- **Patent clock**: public disclosure (2026-08-08 push) starts the US
  1-year grace period; most other jurisdictions require filing before
  disclosure. If any claim is worth protecting (candidate: audit-trail
  coverage verification), an IP consult must happen *before* the arXiv
  post. Expected outcome: mostly not patentable — confirm cheaply, then
  proceed open with confidence.
- **Defensive publication** (repo + preprint) prevents others patenting
  the same mechanisms out from under the project.
- **arXiv preprint early** — first-and-honest beats polished-and-second.
  The preprint is the ownership claim that matters in research.

## The claim ladder (each rung has a gate that may say no)

| Phase | Goal | Gate to proceed |
|---|---|---|
| 0. Airtight | Ladder (4b/7b-coder/1.5b/9b) + pre-fix control + precision/dedup grading + 5-run cells | Curve holds; control shows fixes caused the win |
| 1. Scale | Real repos (50–500 files) vs real CVEs; REPL as load-bearing substrate | Advantage survives 500 files |
| 2. Domain transfer | Same engine on literature review, incident triage, data debugging | Not secretly "a security scanner with extra steps" |
| 3. Paper | Workshop first (NeurIPS/ICLR agent tracks): *"Topology as Insurance"* | Results replicated, grading hostile-reviewed |
| 4. Protocol + runtime | Freeze G=(V,E,S,P) as language-agnostic protocol; FortSignal as governance boundary | Science holds; community interest exists |

## Kill / pivot criteria (pre-committed)

- Pre-fix control also wins → fixes weren't the cause; new mystery, honest
  re-investigation before any claim.
- Curve flat or noisy across the ladder → 7b win was a fluke; publish
  negative result, pivot to verification-as-value.
- Precision/dedup grading erases the margin → report the corrected numbers.
- Advantage vanishes at 500-file scale → "interesting mechanism, no
  demonstrated value at scale yet"; publish that or pivot.

## Sequencing if results are outstanding

1. Don't announce — replicate (5-run cells, second domain, external eyes
   on grading).
2. Timestamp via arXiv preprint.
3. Keep the failure corpus (Run 9's decisive loss is part of the story;
   it is what makes the turnaround credible).
4. FortSignal integration becomes the governance differentiator — the
   safety kernel is the piece no lab will bother to build and every
   serious deployment will need.
