"""Experiment C1 runner: complexity-scaling matrix at constant model.

Generates levels per the falsification contract, runs every condition,
writes data/complexity_c1.json PROGRESSIVELY (partial results survive
crashes). Model from env (RGI_LLM_MODEL), frozen harness budgets.
"""
import asyncio
import json
import time
from pathlib import Path

from benchmarks.generator import LEVELS, generate
from rgi.eval import _run_condition, score_report_full

SEEDS = (11, 22, 33)
CONDITIONS = ("rgi", "single", "fixed")
OUT = Path("data/complexity_c1.json")


async def main():
    results = []
    if OUT.exists():  # resume: skip completed cells
        results = json.loads(OUT.read_text())
    done = {(r["level"], r["seed"], r["condition"]) for r in results}

    for level, (n_files, n_vulns, chain_depth) in LEVELS.items():
        for seed in SEEDS:
            target_dir = Path(f"benchmarks/gen/{level}_s{seed}")
            if not target_dir.exists():
                generate(target_dir, n_files, n_vulns, chain_depth, seed)
            target = {"name": f"{level}_s{seed}", "path": str(target_dir),
                      "ground_truth": str(target_dir / "ground_truth.json"),
                      "max_total_nodes": 200, "max_llm_calls": 60}
            ground_truth = json.loads((target_dir / "ground_truth.json").read_text())
            for condition in CONDITIONS:
                if (level, seed, condition) in done:
                    continue
                started = time.monotonic()
                cell = {"level": level, "n_files": n_files, "chain_depth": chain_depth,
                        "seed": seed, "condition": condition}
                try:
                    report = await _run_condition(
                        condition, target,
                        "Analyze code security across this codebase",
                        mock=False, provider="ollama", model=None,
                        max_llm_calls=60, run_idx=0,
                        max_total_nodes=200, embed=True)
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
                print(f"{level} s{seed} {condition}: recall={cell.get('recall')} "
                      f"calls={cell.get('calls')} status={cell['status']} "
                      f"({cell['wall_seconds']}s)", flush=True)

    print(f"C1 matrix complete: {len(results)} cells -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
