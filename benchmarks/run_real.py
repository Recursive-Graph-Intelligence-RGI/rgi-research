"""Experiment C2 runner: real-codebase replication matrix.

Targets are real OSS checkouts in data/real/ with ground truth in
benchmarks/real/<name>/ground_truth.json, per the pre-registered contract
(docs/reports/2026-08-10-experiment-c2-real-codebases.md). n=1 per cell
(real projects are singular), three conditions, model from env. Writes
progressively; resume skips completed cells.
"""
import asyncio
import json
import os
import time
from pathlib import Path

from rgi.eval import _run_condition, score_report_full

TARGETS = {  # run order = measured file count (18, 21, 80, 132)
    "R1_vulpy": ("data/real/vulpy/bad", "benchmarks/real/vulpy/ground_truth.json"),
    "R2_dvpwa": ("data/real/dvpwa", "benchmarks/real/dvpwa/ground_truth.json"),
    "R4_pygoat": ("data/real/pygoat", "benchmarks/real/pygoat/ground_truth.json"),
    "R3_aiohttp": ("data/real/aiohttp", "benchmarks/real/aiohttp/ground_truth.json"),
}
CONDITIONS = tuple(os.environ.get("RGI_C2_CONDITIONS", "rgi,single,fixed").split(","))
_ONLY = os.environ.get("RGI_C2_TARGETS")  # e.g. "R1_vulpy"; None = all
_MODEL_TAG = (os.environ.get("RGI_LLM_MODEL") or "mock").replace("/", "_").replace(":", "_").replace(".", "_")
OUT = Path(f"data/real_c2_{_MODEL_TAG}.json")


async def main():
    results = []
    if OUT.exists():  # resume: skip completed cells
        results = json.loads(OUT.read_text())
    done = {(r["target"], r["condition"]) for r in results}

    for name, (path, gt_path) in TARGETS.items():
        if _ONLY and name != _ONLY:
            continue
        n_files = len(list(Path(path).rglob("*.py")))
        target = {"name": name, "path": path, "ground_truth": gt_path,
                  "max_total_nodes": int(os.environ.get("RGI_C1_MAX_NODES", "200")),
                  "max_llm_calls": int(os.environ.get("RGI_C1_MAX_LLM_CALLS", "60"))}
        ground_truth = json.loads(Path(gt_path).read_text())
        for condition in CONDITIONS:
            if (name, condition) in done:
                continue
            # Size-aware time limit: the default 300s wall is too short for
            # larger real-code targets (observed 7b R4 and 4b R3 time out
            # with good recall). Pre/post data preserved for re-runs.
            os.environ["RGI_MAX_SECONDS"] = str(max(300, 180 + n_files * 5))
            started = time.monotonic()
            cell = {"target": name, "n_files": n_files, "condition": condition}
            try:
                report = await _run_condition(
                    condition, target,
                    "Analyze code security across this codebase",
                    mock=False, provider="ollama", model=None,
                    max_llm_calls=target["max_llm_calls"], run_idx=0,
                    max_total_nodes=target["max_total_nodes"], embed=True)
                graded = score_report_full(report, ground_truth)
                cell.update({
                    "status": report.get("status", "unknown"),
                    "recall": graded["recall"], "precision": graded["precision"],
                    "calls": report.get("llm_calls", 0),
                    "corrections": report.get("corrections_made", 0),
                    "topology_metrics": report.get("topology_metrics", {}),
                })
            except Exception as exc:  # cell-level containment
                cell.update({"status": "error", "recall": 0.0,
                             "error": f"{type(exc).__name__}: {exc}"[:300]})
            cell["wall_seconds"] = round(time.monotonic() - started, 1)
            results.append(cell)
            OUT.write_text(json.dumps(results, indent=1))
            print(f"{name} {condition}: recall={cell.get('recall')} "
                  f"calls={cell.get('calls')} status={cell['status']} "
                  f"({cell['wall_seconds']}s)", flush=True)

    print(f"C2 matrix complete: {len(results)} cells -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
