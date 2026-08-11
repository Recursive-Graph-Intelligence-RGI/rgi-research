"""Eval runner: turns the experiment from anecdote into distribution.
Matrix = targets x conditions x repetitions, scored against ground truth.
Mock mode = plumbing; live mode = evidence."""
import asyncio
import json
import os
import re
from pathlib import Path

from rgi.baseline import run_baseline
from rgi.fixed_workflow import run_fixed_workflow
from rgi.reasoning.llm_client import LLMClient, MockLLMClient

TARGETS = [
    {"name": "sample_project", "path": "sample_project",
     "ground_truth": "benchmarks/ground_truth/sample_project.json",
     "max_total_nodes": 50, "max_llm_calls": 20},
    {"name": "vuln_app_2", "path": "benchmarks/vuln_app_2",
     "ground_truth": "benchmarks/ground_truth/vuln_app_2.json",
     "max_total_nodes": 50, "max_llm_calls": 20},
    {"name": "vuln_app_3", "path": "benchmarks/vuln_app_3",
     "ground_truth": "benchmarks/ground_truth/vuln_app_3.json",
     "max_total_nodes": 120, "max_llm_calls": 40},
    # Hard target: 13 files, 15 graded vulns, several cross-file chains.
    # Built after Run 8 saturated vuln_app_3 (rgi = fixed = 1.0 on DeepSeek).
    {"name": "vuln_app_hard", "path": "benchmarks/vuln_app_hard",
     "ground_truth": "benchmarks/ground_truth/vuln_app_hard.json",
     "max_total_nodes": 200, "max_llm_calls": 60},
]
CONDITIONS = ("rgi", "single", "fixed")


def _normalize(text: str) -> str:
    """Normalize finding text for term matching: lowercase, collapse
    underscore/hyphen to space so 'sql_injection' matches the ground-truth
    term 'sql injection' (the deterministic scanner emits underscores; the
    LLM emits spaces — same meaning, one scorer)."""
    return text.lower().replace("_", " ").replace("-", " ")


def score_recall(report: dict, ground_truth: dict) -> float:
    text = _normalize(json.dumps(report.get("findings", [])))
    vulns = ground_truth["vulns"]
    hits = sum(1 for v in vulns if any(_normalize(t) in text for t in v["terms"]))
    return hits / len(vulns) if vulns else 0.0


def score_report_full(report: dict, ground_truth: dict) -> dict:
    """Tightened grading (post-Run 12 review): dedupe findings before
    scoring — the raw scorer gave more findings more lottery tickets for
    keyword hits, and RGI produces 10-30× more findings than fixed.
    Also reports precision (fraction of unique findings that mention a
    real vuln term) so noise is measured, not hidden."""
    findings = report.get("findings", [])
    seen, unique = set(), []
    for f in findings:
        t = " ".join(json.dumps(f, sort_keys=True).lower().split())
        if t not in seen:
            seen.add(t)
            unique.append(t)
    text = _normalize(" ".join(unique))
    vulns = ground_truth["vulns"]
    hits = sum(1 for v in vulns if any(_normalize(term) in text for term in v["terms"]))
    relevant = sum(
        1 for t in unique
        if any(_normalize(term) in _normalize(t) for v in vulns for term in v["terms"])
    )
    return {
        "recall": round(hits / len(vulns), 3) if vulns else 0.0,
        "precision": round(relevant / len(unique), 3) if unique else 0.0,
        "findings_raw": len(findings),
        "findings_deduped": len(unique),
    }


async def _run_condition(condition, target, objective, mock, provider, model, max_llm_calls,
                         run_idx, max_total_nodes=50, embed=False):
    if condition == "rgi":
        from rgi.cli import run_analysis  # local import: avoids circularity
        # Cell output goes to a throwaway path; the canonical per-cell copy
        # is written by run_eval into data/cells/ with a model tag. (A
        # CWD-relative path here let pytest pollute data/ and overwrite a
        # live 4b cell during the overnight ladder.)
        import tempfile
        throwaway = str(Path(tempfile.gettempdir()) / "rgi_eval_throwaway.json")
        return await run_analysis(target["path"], objective, throwaway,
                                  mock, provider, model, max_llm_calls,
                                  max_total_nodes=max_total_nodes, embed=embed)
    llm = MockLLMClient() if mock else LLMClient(model=model)
    if condition == "single":
        return await run_baseline(target["path"], objective, llm)
    return await run_fixed_workflow(target["path"], objective, llm)


async def run_eval(objective, runs, mock, provider, model, max_llm_calls,
                   target_filter=None, embed=False) -> dict:
    matrix = []
    for target in TARGETS:
        if target_filter is not None and target["name"] != target_filter:
            continue
        ground_truth = json.loads(Path(target["ground_truth"]).read_text())
        budget = max(max_llm_calls, target.get("max_llm_calls", 0))
        for condition in CONDITIONS:
            for run_idx in range(runs):
                try:
                    report = await _run_condition(condition, target, objective, mock,
                                                  provider, model, budget, run_idx,
                                                  max_total_nodes=target.get("max_total_nodes", 50),
                                                  embed=embed)
                except Exception as exc:
                    # Cell-level containment (1.5b ladder crash, Run O1): a
                    # model whose output breaks parsing in baseline/fixed
                    # (no node-level containment there) must not kill the
                    # whole matrix. Record the crater, keep going.
                    matrix.append({
                        "target": target["name"], "condition": condition,
                        "run": run_idx, "recall": 0.0, "precision": 0.0,
                        "findings_raw": 0, "findings_deduped": 0, "calls": 0,
                        "corrections": 0, "status": "error",
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    })
                    continue
                # Preserve every cell's raw report for offline re-grading
                # (Run 12 lesson: only RGI cells wrote files, so fixed/single
                # could never be re-scored when the rubric tightened).
                tag = re.sub(r"[^A-Za-z0-9_.-]", "_",
                             model or os.environ.get("RGI_LLM_MODEL") or "mock")
                cell_path = Path("data/cells") / f"{target['name']}_{condition}_{run_idx}_{tag}.json"
                cell_path.parent.mkdir(exist_ok=True)
                cell_path.write_text(json.dumps(report))
                graded = score_report_full(report, ground_truth)
                matrix.append({
                    "target": target["name"],
                    "condition": condition,
                    "run": run_idx,
                    "recall": graded["recall"],
                    "precision": graded["precision"],
                    "findings_raw": graded["findings_raw"],
                    "findings_deduped": graded["findings_deduped"],
                    "calls": report.get("llm_calls", 0),
                    "corrections": report.get("corrections_made", 0),
                    "status": report.get("status", "unknown"),
                })
    summary = {}
    for entry in matrix:
        key = f"{entry['target']}|{entry['condition']}"
        bucket = summary.setdefault(key, {"recalls": [], "calls": [], "corrections": 0})
        bucket["recalls"].append(entry["recall"])
        bucket["calls"].append(entry["calls"])
        bucket["corrections"] += entry["corrections"]
    return {
        "objective": objective,
        "runs": runs,
        "matrix": matrix,
        "summary": {
            key: {
                "mean_recall": round(sum(b["recalls"]) / len(b["recalls"]), 3),
                "mean_calls": round(sum(b["calls"]) / len(b["calls"]), 1),
                "total_corrections": b["corrections"],
            }
            for key, b in summary.items()
        },
    }
