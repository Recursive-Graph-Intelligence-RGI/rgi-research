import json
from pathlib import Path
from rgi.tools.registry import ToolRegistry

GT_DIR = Path("benchmarks/ground_truth")


def test_ground_truth_files_exist_and_parse():
    for name in ("sample_project.json", "vuln_app_2.json"):
        gt = json.loads((GT_DIR / name).read_text())
        assert len(gt["vulns"]) >= 4
        assert all(v["id"] and v["terms"] for v in gt["vulns"])


async def test_vuln_app_2_tools_see_the_code():
    registry = ToolRegistry()
    parsed = await registry.execute("parse_python_file", {"path": "benchmarks/vuln_app_2"})
    excerpt = parsed["findings"][0]["source_excerpt"]
    assert "md5" in excerpt and "os.system" in excerpt and "SELECT" in excerpt
    hits = await registry.execute("grep_security_patterns", {
        "path": "benchmarks/vuln_app_2",
        "keywords": ["injection", "md5", "traversal", "os.system"]})
    assert len(hits["findings"]) >= 4
