# C2 Benchmark Session Notes — 2026-08-10

*Live notes from the C2 real-codebase benchmark run and architectural discussion.*

## Current run status

- Background task: `bash-90qmc4mf` running `data/restart_c2_with_topology_fix.sh`
- 1.5b matrix: **complete (12 cells)**
- 4b matrix: **R3 aiohttp rgi just finished with recall 0.667 but status `failed` at 859.6s** (20s over the 840s limit)
- 7b matrix: pending after 4b finishes

## Key findings so far

### Topology-scaling fix is working
- Dynamic top-K activation (`K ≈ max(10, 2·√N_nodes)`) + size-aware node budget kept graphs from exploding.
- 4b R3 aiohttp rgi achieved **0.667 recall** (2 of 3 CVEs) before timing out — up from 0.333 timeout and 1.5b's 0.0.
- This is strong evidence that RGI *can* find real vulnerabilities in real OSS when topology and time budget are scaled together.

### Time limit is still the binding constraint
- 4b R3 needed ~860s; the size-aware formula gave 840s.
- Recommendation: bump to `max(300, 240 + n_files*5)` or `max(300, 180 + n_files*6)` for the next re-run if needed.

### Fixed-workflow JSON parse errors persist on 1.5b
- R4_pygoat fixed and R3_aiohttp fixed errored with `JSONDecodeError` under 1.5b.
- A robustness patch was added to `rgi/fixed_workflow.py` after this run started; it will convert unparseable responses into low-recall completions instead of crashes on future runs.

## Harness fixes applied during C2

1. `benchmarks/mem_watchdog.sh`: broader pattern to catch `run_complexity` and `run_real`.
2. `rgi/reasoning/embeddings.py`: configurable `RGI_EMBED_TIMEOUT` (raised to 180s).
3. `benchmarks/run_real.py`: size-aware wall-clock limit `RGI_MAX_SECONDS = max(300, 180 + n_files*5)`.
4. `rgi/memory/activation.py`: dynamic top-K activation.
5. `benchmarks/run_real.py`: size-aware node budget `max(200, 100 + n_files*3)`.
6. `rgi/fixed_workflow.py`: catch unparseable LLM responses (post-run patch).

## Architectural analysis: why small code works, big code doesn't

### Works on small vulnerable targets (R1/R2/R4)
- Knowledge graph is small; keyword activation can accidentally land near relevant code.
- Generic subgraphs (`"JWT Security Analysis"`) still hit the right files because there are few files.
- LLM context is enough to cover the project.
- Ground truth is dense (purposely vulnerable).

### Struggles on real OSS (R3 aiohttp, 132 files)
- Perception stores only labels (`"Module X in file Y"`), not code bodies.
- Activation can't route to specific vulnerable symbols (e.g., `follow_symlinks`).
- Subgraphs get generic objectives and become random walks.
- REPL exploration is underpowered — no `read_file`, `grep`, `callers`, `callees` primitives.
- Verification doesn't filter noise, so precision collapses (e.g., 4b R4 rgi: 0.846 recall, 0.021 precision).

## rlmlocal relationship

- `rlmlocal` already built a code-grounded graph: `StructureExtractor`, import/call/data-flow/reference graphs, `VectorStore` with embeddings, semantic concepts, freshness/re-healing, gate cascade, and verified execution.
- RGI's recursive orchestration is valid; its **substrate** is too shallow.
- The most direct path to broad applicability is porting rlmlocal's graph-building concepts into RGI's Python stack (perception, activation, grounded REPL tools).

## Research → building transition

C2 has answered the first research question: *recursive topology helps, but only when grounded.*

- **v0.2** should close with C2 + honest verdict.
- **v0.3** should be an engineering build: "RGI with a code-grounded world model."
- v0.3 roadmap items (learned topology, inhibition-default harness, neurogenesis) should be built *on top of* the richer substrate, not instead of it.

## Options going forward

1. **Keep RGI as pure research** — continue v0.3 experiments on shallow perception. Not recommended; ceiling is visible.
2. **Upgrade RGI's substrate** — port rlmlocal's parsing/embedding/semantic concepts into RGI while keeping its recursive orchestration. Recommended.
3. **Merge RGI into rlmlocal** — possible, but loses the standalone engine/research identity.

## Recommended next steps

1. Let `bash-90qmc4mf` finish to collect 7b and remaining 4b data.
2. Regenerate report and figures with final data.
3. If high-recall cells still fail on time, do one more re-run with a looser time formula.
4. Write final C2 verdict.
5. Begin v0.3 substrate engineering: richer perception, embedding-based activation, grounded REPL tools, adversarial verification.

## Open questions

- What is the right time-limit formula for 7b on 80/132-file targets?
- Can the robust fixed-workflow patch give us complete fixed cells on 1.5b?
- Which rlmlocal modules are most mature/stable for porting?
- Should RGI remain Python, or should the engine move closer to rlmlocal's TypeScript stack?
