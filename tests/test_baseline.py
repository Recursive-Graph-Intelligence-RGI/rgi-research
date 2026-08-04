import json
from rgi.baseline import run_baseline
from rgi.cli import main
from rgi.reasoning.llm_client import MockLLMClient


async def test_baseline_makes_exactly_one_llm_call():
    llm = MockLLMClient()
    report = await run_baseline("sample_project", "Analyze authentication security", llm)
    assert llm.calls == 1
    assert report["mode"] == "single_agent"
    assert report["llm_calls"] == 1
    assert report["objective"] == "Analyze authentication security"
    assert isinstance(report["findings"], list)


async def test_mock_baseline_finds_nothing_without_scaffolding():
    """In mock mode the unscaffolded single agent hits the fallback —
    mechanically illustrating why topology matters (scripted, not evidence)."""
    llm = MockLLMClient()
    report = await run_baseline("sample_project", "Analyze authentication security", llm)
    assert report["confidence"] == 0.5
    assert report["findings"][0]["finding"] == "no finding"


def test_compare_runs_both_conditions(tmp_path):
    output = tmp_path / "compare.json"
    rc = main(["compare", "sample_project",
               "--objective", "Analyze authentication security",
               "--output", str(output), "--mock"])
    assert rc == 0
    comparison = json.loads(output.read_text())
    assert comparison["rgi"]["status"] == "completed"
    assert comparison["baseline"]["mode"] == "single_agent"
    assert comparison["baseline"]["llm_calls"] == 1
    assert comparison["rgi"]["corrections_made"] >= 1
    assert comparison["deltas"]["findings_count"] > 0
    assert "scripted" in comparison["caveat"]


def test_compare_caveat_present_in_mock(tmp_path):
    output = tmp_path / "compare.json"
    main(["compare", "sample_project", "--objective", "x",
          "--output", str(output), "--mock"])
    comparison = json.loads(output.read_text())
    assert "not evidence" in comparison["caveat"]
