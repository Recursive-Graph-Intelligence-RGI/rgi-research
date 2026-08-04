"""Eval runner: turns the experiment from anecdote into distribution.
Matrix = targets x conditions x repetitions, scored against ground truth.
Mock mode = plumbing; live mode = evidence."""
import asyncio
import json
from pathlib import Path

from rgi.baseline import run_baseline
from rgi.fixed_workflow import run_fixed_workflow
from rgi.reasoning.llm_client import LLMClient, MockLLMClient

TARGETS = [
    {"name": "sample_project", "path": "sample_project",
     "ground_truth": "benchmarks/ground_truth/sample_project.json"},
    {"name": "vuln_app_2", "path": "benchmarks/vuln_app_2",
     "ground_truth": "benchmarks/ground_truth/vuln_app_2.json"},
]
CONDITIONS = ("rgi", "single", "fixed")


def score_recall(report: dict, ground_truth: dict) -> float:
    text = json.dumps(report.get("findings", [])).lower()
    vulns = ground_truth["vulns"]
    hits = sum(1 for v in vulns if any(t.lower() in text for t in v["terms"]))
    return hits / len(vulns) if vulns else 0.0


async def _run_condition(condition, target, objective, mock, provider, model, max_llm_calls, run_idx):
    if condition == "rgi":
        from rgi.cli import run_analysis  # local import: avoids circularity
        return await run_analysis(target["path"], objective,
                                  f"data/eval_{target['name']}_{condition}_{run_idx}.json",
                                  mock, provider, model, max_llm_calls)
    llm = MockLLMClient() if mock else LLMClient(model=model)
    if condition == "single":
        return await run_baseline(target["path"], objective, llm)
    return await run_fixed_workflow(target["path"], objective, llm)


async def run_eval(objective, runs, mock, provider, model, max_llm_calls) -> dict:
    matrix = []
    for target in TARGETS:
        ground_truth = json.loads(Path(target["ground_truth"]).read_text())
        for condition in CONDITIONS:
            for run_idx in range(runs):
                report = await _run_condition(condition, target, objective, mock,
                                              provider, model, max_llm_calls, run_idx)
                matrix.append({
                    "target": target["name"],
                    "condition": condition,
                    "run": run_idx,
                    "recall": round(score_recall(report, ground_truth), 3),
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
