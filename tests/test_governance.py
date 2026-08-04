from rgi.core.governance import LocalGate


def test_tool_path_inside_root_allowed(tmp_path):
    gate = LocalGate(str(tmp_path))
    inside = tmp_path / "sample_project" / "auth.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("x = 1")
    decision = gate.check("tool_execute", {"path": str(inside)})
    assert decision.allowed


def test_tool_path_outside_root_denied(tmp_path):
    gate = LocalGate(str(tmp_path / "target"))
    decision = gate.check("tool_execute", {"path": "/etc/passwd"})
    assert not decision.allowed
    assert decision.reason == "path_outside_scope"


def test_llm_budget_enforced():
    gate = LocalGate(".", max_llm_calls=3)
    assert gate.check("llm_call", {"calls_so_far": 2}).allowed
    denied = gate.check("llm_call", {"calls_so_far": 3})
    assert not denied.allowed
    assert denied.reason == "llm_budget_exhausted"
