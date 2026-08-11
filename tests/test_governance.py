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


def test_tool_execute_uses_root_key(tmp_path):
    gate = LocalGate(str(tmp_path))
    subdir = tmp_path / "src"
    subdir.mkdir()
    decision = gate.check("tool_execute", {"tool": "grep", "root": str(subdir)})
    assert decision.allowed is True


def test_allowed_tools_policy(tmp_path):
    gate = LocalGate(str(tmp_path), policy={"allowed_tools": ["read_file"]})
    decision = gate.check("tool_execute", {"tool": "grep", "path": str(tmp_path)})
    assert decision.allowed is False
    assert "tool_denied" in decision.reason


def test_denied_tools_policy(tmp_path):
    gate = LocalGate(str(tmp_path), policy={"denied_tools": ["exec"]})
    decision = gate.check("tool_execute", {"tool": "exec", "path": str(tmp_path)})
    assert decision.allowed is False
    assert "tool_denied" in decision.reason


def test_spawn_allowed_by_default(tmp_path):
    gate = LocalGate(str(tmp_path))
    decision = gate.check("spawn", {"depth": 2})
    assert decision.allowed is True


def test_spawn_disabled_by_policy(tmp_path):
    gate = LocalGate(str(tmp_path), policy={"allow_spawn": False})
    decision = gate.check("spawn", {"depth": 1})
    assert decision.allowed is False
    assert decision.reason == "spawn_disabled"


def test_spawn_depth_limit_by_policy(tmp_path):
    gate = LocalGate(str(tmp_path), policy={"max_depth": 2})
    decision = gate.check("spawn", {"depth": 3})
    assert decision.allowed is False
    assert decision.reason == "depth_limit"


def test_policy_loaded_from_file(tmp_path):
    import json
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps({"allow_spawn": False, "max_llm_calls": 10}))
    gate = LocalGate(str(tmp_path), policy_path=str(policy_file))
    assert gate.check("spawn", {"depth": 1}).allowed is False
    assert gate.check("llm_call", {"calls_so_far": 10}).allowed is False


def test_unknown_action_allowed():
    gate = LocalGate("/tmp")
    decision = gate.check("future_action", {})
    assert decision.allowed is True
