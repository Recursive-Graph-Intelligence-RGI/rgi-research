"""Tests for finding normalization and compilation."""
from pathlib import Path

import pytest

from rgi.core.findings import (
    compile_findings,
    deduplicate_findings,
    format_finding_for_prompt,
    is_noise,
    normalize_finding,
)


def test_is_noise_rejects_strings_without_structure():
    assert is_noise("plain string") is True


def test_is_noise_rejects_keyword_hits():
    assert is_noise({"kind": "keyword_hit", "keyword": "jwt"}) is True


def test_normalize_dict_finding():
    raw = {
        "kind": "sql_injection",
        "severity": "critical",
        "detail": "f-string SQL",
        "file": "auth.py",
        "line": 34,
        "symbol": "login",
        "confidence": 0.9,
    }
    f = normalize_finding(raw)
    assert f["kind"] == "sql_injection"
    assert f["grounded"] is True


def test_normalize_string_finding_parses_location():
    raw = "sql_injection at auth.py:34 - f-string SQL in login"
    f = normalize_finding(raw)
    assert f["kind"] == "sql_injection"
    assert f["file"] == "auth.py"
    assert f["line"] == 34
    assert "login" in f["detail"]
    assert f["grounded"] is True


def test_normalize_string_finding_falls_back_to_note():
    raw = "something looks odd here"
    f = normalize_finding(raw)
    assert f["kind"] == "note"
    assert f["detail"] == raw
    assert f["grounded"] is False


def test_deduplicate_findings_keeps_highest_confidence():
    findings = [
        {"kind": "x", "file": "a.py", "line": 1, "confidence": 0.5},
        {"kind": "x", "file": "a.py", "line": 1, "confidence": 0.9},
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 1
    assert result[0]["confidence"] == 0.9


def test_compile_findings_drops_ungrounded_when_required():
    scanner = [{"kind": "x", "detail": "grounded", "file": "a.py", "line": 1}]
    node = [{"kind": "y", "detail": "ungrounded"}]
    result = compile_findings(scanner, node, require_grounded=True)
    assert len(result) == 1
    assert result[0]["kind"] == "x"


def test_compile_findings_sorts_by_severity():
    findings = [
        {"kind": "low", "file": "a.py", "line": 1, "severity": "low", "confidence": 0.9},
        {"kind": "high", "file": "a.py", "line": 2, "severity": "high", "confidence": 0.9},
    ]
    result = compile_findings(findings, [])
    assert result[0]["kind"] == "high"


def test_format_finding_for_prompt_includes_location():
    f = {"kind": "x", "severity": "high", "detail": "d", "file": "a.py", "line": 1, "symbol": "s"}
    text = format_finding_for_prompt(f)
    assert "a.py:1" in text
    assert "s" in text


def test_compile_filters_nonexistent_files(tmp_path: Path):
    raw = {"kind": "x", "file": "does_not_exist.py", "line": 1, "detail": "d"}
    result = compile_findings([raw], [], target_path=str(tmp_path))
    assert result == []
