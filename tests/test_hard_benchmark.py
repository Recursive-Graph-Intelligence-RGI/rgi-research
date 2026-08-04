import json
from pathlib import Path
from rgi.cli import main
from rgi.tools.registry import ToolRegistry


def test_ground_truth_parses():
    gt = json.loads(Path("benchmarks/ground_truth/vuln_app_3.json").read_text())
    assert len(gt["vulns"]) == 5
    assert all(v["id"] and v["terms"] for v in gt["vulns"])


async def test_tools_see_all_15_files():
    parsed = await ToolRegistry().execute("parse_python_file", {"path": "benchmarks/vuln_app_3"})
    excerpt = parsed["findings"][0]["source_excerpt"]
    assert "pickle.loads" in excerpt or "SELECT" in excerpt
    assert "require_auth" in excerpt


def test_eval_target_filter_mock(tmp_path):
    output = tmp_path / "eval.json"
    rc = main(["eval", "--objective", "Analyze code security", "--runs", "1",
               "--target", "vuln_app_3", "--output", str(output), "--mock"])
    assert rc == 0
    result = json.loads(output.read_text())
    assert len(result["matrix"]) == 3  # 1 target x 3 conditions x 1 run
    assert all(m["target"] == "vuln_app_3" for m in result["matrix"])
