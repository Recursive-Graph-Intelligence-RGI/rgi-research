"""Diagnose why C2 topology does not scale with codebase size.

Reads data/real_c2_*.json and data/audit.jsonl, correlates root graph runs
with C2 cells by timestamp overlap, and reports spawn/rejection reasons.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

AUDIT = Path("data/audit.jsonl")


def _parse_ts(s):
    return datetime.fromisoformat(s)


def _c2_cells():
    """Yield (model, target, condition, status, start_ts, end_ts, path) for each cell."""
    models = {
        "qwen2_5_1_5b": "qwen2.5:1.5b",
        "nemotron-3-nano_4b": "nemotron-3-nano:4b",
        "qwen2_5_7b": "qwen2.5:7b",
    }
    for path in sorted(Path("data").glob("real_c2_*.json")):
        if path.name.endswith((".pre_timeout_bump.json", ".stale_mock_fallback.json")):
            continue
        tag = path.stem.replace("real_c2_", "")
        model = models.get(tag)
        if not model:
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        cells = json.loads(path.read_text())
        # Cells are written sequentially; approximate end time from file mtime
        # and walk backwards using wall_seconds.
        cursor = mtime
        for c in reversed(cells):
            wall = c.get("wall_seconds", 0)
            end = cursor
            start = end - timedelta(seconds=wall)
            cursor = start
            yield {
                "model": model,
                "target": c.get("target"),
                "condition": c.get("condition"),
                "status": c.get("status"),
                "start": start,
                "end": end,
                "path": str(path),
            }


def _audit_runs():
    """Return list of root graph runs: {root_id, start, end, events}."""
    events = [json.loads(line) for line in AUDIT.read_text().splitlines() if line.strip()]
    # Sort by timestamp
    events.sort(key=lambda r: r["timestamp"])
    runs = []
    open_runs = {}
    for e in events:
        ev = e["event"]
        gid = e.get("graph_id")
        if ev == "run_started":
            open_runs[gid] = {"root": gid, "start": e["timestamp"], "events": []}
        elif ev == "run_finished" and gid in open_runs:
            run = open_runs.pop(gid)
            run["end"] = e["timestamp"]
            runs.append(run)
        elif gid in open_runs:
            open_runs[gid]["events"].append(e)
    return runs


def _identify_target(events):
    """Try to identify target from coverage_sweep missing filenames."""
    targets = {
        "vulpy": "R1_vulpy",
        "dvpwa": "R2_dvpwa",
        "pygoat": "R4_pygoat",
        "aiohttp": "R3_aiohttp",
    }
    for e in events:
        if e["event"] == "coverage_sweep":
            missing = " ".join(e.get("missing", []))
            for key, target in targets.items():
                if key in missing.lower():
                    return target
    return None


def diagnose():
    if not AUDIT.exists():
        print("No audit log found at", AUDIT)
        return

    cells = list(_c2_cells())
    runs = _audit_runs()

    # Correlate runs with cells by timestamp overlap
    matched = []
    for run in runs:
        run_start = _parse_ts(run["start"])
        run_end = _parse_ts(run["end"])
        best = None
        best_overlap = timedelta(0)
        for c in cells:
            overlap_start = max(run_start, c["start"])
            overlap_end = min(run_end, c["end"])
            overlap = overlap_end - overlap_start
            if overlap > best_overlap:
                best_overlap = overlap
                best = c
        if best and best_overlap.total_seconds() > 1:
            matched.append({
                "run": run,
                "cell": best,
                "target_guess": _identify_target(run["events"]) or best["target"],
            })

    print(f"Matched {len(matched)} audit runs to C2 cells\n")

    # Per-cell summary
    for m in sorted(matched, key=lambda x: (x["cell"]["model"], x["cell"]["target"] or "", x["cell"]["condition"])):
        c = m["cell"]
        run = m["run"]
        events = run["events"]
        approved = [e for e in events if e["event"] == "spawn_approved"]
        rejected = [e for e in events if e["event"] == "spawn_rejected"]
        inhibited = [e for e in events if e["event"] == "spawn_inhibited"]
        timeouts = [e for e in events if e["event"] == "time_limit_exceeded"]
        node_errors = [e for e in events if e["event"] == "node_execution_error"]
        child_errors = [e for e in events if e["event"] == "child_execution_error"]
        reason_counts = Counter(e.get("reason", "unknown") for e in rejected)

        print(f"{c['model']} {m['target_guess']} {c['condition']}: {c['status']}")
        print(f"  spawn approved: {len(approved)}  rejected: {len(rejected)}  inhibited: {len(inhibited)}")
        print(f"  time_limit_exceeded: {len(timeouts)}  node_exec_error: {len(node_errors)}  child_exec_error: {len(child_errors)}")
        if rejected:
            print(f"  rejection reasons: {dict(reason_counts)}")
        print()

    # Aggregate rejection reasons across matched runs
    all_reasons = Counter()
    for m in matched:
        for e in m["run"]["events"]:
            if e["event"] == "spawn_rejected":
                all_reasons[e.get("reason", "unknown")] += 1
    print("Aggregate spawn rejection reasons:")
    for reason, count in all_reasons.most_common():
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    diagnose()
