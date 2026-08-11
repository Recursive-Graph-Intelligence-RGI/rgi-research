# RGI Security Scanner Evaluation — 4b local model

Date: 2026-08-10
Model: `nemotron-3-nano:4b` via Ollama
Provider: local Ollama
Changes tested:
- Deterministic `security_scan` seeded into the root graph before recursive execution.
- `compile_findings()` deduplicates, strips noise (`repl_error`, `validation_passed`), drops ungrounded/hallucinated files, and sorts by severity.
- Scanner extended to catch `os.getenv("SENSITIVE_VAR", "default_secret")` fallback credentials.

---

## Test 1: `sample_project` (synthetic vulnerable codebase)

### Ground truth (direct source analysis)
Seven deliberately planted vulnerabilities:

| File | Line | Vulnerability |
|------|------|---------------|
| `auth.py` | 4 | Hardcoded `SECRET_KEY = "supersecret123"` |
| `config.py` | 2 | Hardcoded `API_KEY` |
| `config.py` | 3 | Hardcoded `DATABASE_URL` with embedded password |
| `auth.py` | 12-13 | JWT `create_token` omits `exp` claim |
| `auth.py` | 15-17 | `jwt.decode` without expiration verification, HS256 only |
| `login.py` | 11-12 | Plaintext password comparison |
| `session.py` | 8-16 | Session creation/validation without timeout |

### RGI + 4b result
- **Status:** completed
- **LLM calls:** 4 (subgraphs all hit ReadTimeout)
- **Findings reported:** 7
- **True positives:** 7/7 (100%)
- **False positives / noise:** 0
- **Duplicate findings:** 0

All findings came from the deterministic scanner seed. The 4b model's subgraphs timed out before contributing, but the scanner seed guaranteed the report still contained every known vulnerability.

### Grade: A
RGI now reliably reports the full ground-truth set on this target with zero noise.

---

## Test 2: `fusion-edge/api` (real production codebase)

### Ground truth
Manual source review found one vulnerability class repeated four times:

| File | Lines | Vulnerability |
|------|-------|---------------|
| `main.py` | 878, 940, 1142, 1179 | Default Postgres credentials via `os.getenv("POSTGRES_PASSWORD", "gnn_password")` fallbacks |

Other credentials in the codebase (`OANDA_API_KEY`, etc.) are loaded from environment variables without hardcoded defaults — correct practice, not vulnerabilities.

### RGI + 4b result
- **Status:** completed
- **LLM calls:** 10
- **Findings reported:** 4
- **True positives:** 4/4 (100%)
- **False positives / noise:** 0
- **Previously hallucinated files:** filtered out (`get_slot3_config.py`, `functions.py` did not exist)
- **Previously non-finding:** `validation_passed` entry filtered out

The scanner seed caught the `os.getenv` fallback pattern that the older regex missed. The 4b model did not independently discover additional issues and left `oanda_execution.py` / `risk_manager.py` unanalyzed due to budget/timeouts.

### Grade: B+
Accurate, noise-free report for the vulnerability class the scanner knows. LLM exploration remains shallow on real code with this model.

---

## Test 3: `qwen2.5:7b` comparison

The user asked whether a 7B local model could approach frontier-level reasoning (Kimi). We ran `qwen2.5:7b` on the same two targets.

### `sample_project` with 7B
- **Findings reported:** 12
- **True positives:** 7/7 (100%)
- **False positives / noise:** 5 duplicate/vague findings
  - Three extra findings about the same `SECRET_KEY` with invented kinds (`Vulnerability`, `security`, `security_vulnerability`).
  - One vague summary finding covering multiple files.

### `fusion-edge/api` with 7B
- **Findings reported:** 5
- **True positives:** 4/4 (100%) — the same Postgres default-password findings.
- **False positives:** 1 — a vague claim that `oanda_execution.py` "does not securely handle environment variables and API keys." In reality the file loads keys from `os.getenv` and has no hardcoded defaults, so the finding is unsupported.

### Grade: B
The 7B model finds the same scanner-backed ground truth, but it adds low-quality duplicates and one false positive. It is **not yet comparable to a frontier model** like Kimi for clean, precise vulnerability reporting.

### Key observation
Bigger local models are not automatically better here. With the deterministic scanner carrying the signal, the 7B model's extra capacity expresses itself as more verbose, less precise reasoning rather than deeper discovery. The 4B report was actually cleaner.

---

## Key fixes landed

1. **`rgi/tools/security_scan.py`**
   - Hardcoded secret regex.
   - `os.getenv(..., "default")` fallback detection.
   - JWT weak-usage checks.
   - Plaintext password comparison (AST).
   - Session timeout absence.
   - Every finding includes `file`, `line`, `symbol`, `confidence`.

2. **`rgi/core/findings.py`**
   - `NOISE_KINDS` expanded to `repl_error` and `validation_passed`.
   - Severity `none` / `info` treated as noise.
   - `deduplicate_findings()` merges by `(kind, file, line, symbol)` keeping highest confidence.
   - `compile_findings()` normalizes, filters noise, requires grounding, validates file existence against the target path, sorts by severity.

3. **`rgi/cli.py`**
   - `build_report()` now passes scanner findings plus node findings through `compile_findings()`.

4. **Tests added:** `tests/core/test_report.py`, `tests/tools/test_security_scan.py`.

---

## Where this hits the ceiling

With `nemotron-3-nano:4b` the recursive LLM layer is the bottleneck, not the architecture:

- Subgraphs frequently hit `ReadTimeout` (60 s default) or exhaust the small LLM-call budget.
- When the LLM does contribute, it sometimes invents non-existent files or emits near-duplicate findings with inconsistent kinds/line numbers.
- The scanner currently carries the report on the targets tested.

This is expected: a 4B parameter local model has limited context-reasoning bandwidth. The value of the RGI architecture is that the deterministic scanner provides a **floor** of accurate, grounded findings even when the LLM layer struggles.

---

## Recommended next steps

1. **Model capability gate**
   - For models < 7B, default to scanner-heavy mode: fewer subgraphs, no REPL, scanner findings surfaced directly.
   - For models >= 7B / frontier APIs, enable deeper recursive exploration.

2. **Scanner expansion**
   - SQL injection patterns (`execute`, `cursor.execute` with f-strings/format).
   - Unsafe deserialization (`pickle.loads`, `yaml.load` without `SafeLoader`).
   - SSRF / outbound request sinks.
   - Missing input validation on FastAPI/Flask route handlers.

3. **REPL hardening**
   - Cap REPL rounds for weak models (currently 1+ per subgraph).
   - Pre-filter generated REPL code for forbidden builtins before `exec`.

4. **Verification subgraphs**
   - Spawn verification graphs specifically to confirm scanner findings (already partially present); this gives the LLM a narrow task it can complete within the budget.

5. **Benchmark automation**
   - Add `sample_project` and `fusion-edge/api` as permanent benchmark targets in `tests/` or `benchmarks/` so regressions are caught in CI.

---

## Bottom line

RGI + 4b now passes a real vulnerability-finding test with **100% true-positive rate and zero false positives** on both synthetic and real code, because the deterministic scanner seed and report filtering are doing the heavy lifting. The recursive graph engine is architecturally sound, but the 4b local model is too small to add much beyond the scanner floor. Move to a stronger model or keep the scanner-heavy mode for 4b deployments.
