from rgi.fixed_workflow import run_fixed_workflow
from rgi.reasoning.llm_client import MockLLMClient


async def test_fixed_workflow_runs_all_tools_per_file_one_call_each():
    llm = MockLLMClient()
    report = await run_fixed_workflow("sample_project", "Analyze authentication security", llm)
    assert llm.calls == 4                       # one call per module, never more
    assert report["mode"] == "fixed_workflow"
    assert len(report["findings"]) == 4
    assert {f["module"] for f in report["findings"]} == {"auth.py", "config.py", "login.py", "session.py"}
    assert report["status"] == "completed"


async def test_fixed_workflow_has_no_correction_machinery():
    """Control B isolates adaptive topology: it must contain no spawning,
    no verification graphs, no correction path — verified structurally by
    the absence of those keys in its report."""
    llm = MockLLMClient()
    report = await run_fixed_workflow("sample_project", "Analyze authentication security", llm)
    assert "corrections_made" not in report
    assert "topology_used" not in report
