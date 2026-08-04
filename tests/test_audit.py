import json
from rgi.core.audit import AuditLog


def test_audit_records_and_persists(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    entry = log.record("spawn_rejected", graph_id="g1", reason="depth_limit")
    assert entry["event"] == "spawn_rejected"
    assert entry["graph_id"] == "g1"
    assert entry["reason"] == "depth_limit"
    assert "timestamp" in entry
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["reason"] == "depth_limit"


def test_audit_appends(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("a")
    log.record("b")
    assert len((tmp_path / "audit.jsonl").read_text().strip().splitlines()) == 2
