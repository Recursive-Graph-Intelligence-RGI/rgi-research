import tempfile
from pathlib import Path

import pytest
from rgi.core.findings import compile_findings, deduplicate_findings, normalize_finding


class TestFindingReporting:
    def test_repl_error_is_noise(self):
        raw = {"kind": "repl_error", "detail": "__import__ not found"}
        assert normalize_finding(raw) is None

    def test_deduplicate_keeps_highest_confidence(self):
        findings = [
            {"kind": "hardcoded_secret", "file": "config.py", "line": 2,
             "symbol": "API_KEY", "confidence": 0.9},
            {"kind": "hardcoded_secret", "file": "config.py", "line": 2,
             "symbol": "API_KEY", "confidence": 0.95},
            {"kind": "hardcoded_secret", "file": "config.py", "line": 3,
             "symbol": "DATABASE_URL", "confidence": 0.9},
        ]
        out = deduplicate_findings(findings)
        assert len(out) == 2
        api = next(f for f in out if f["line"] == 2)
        assert api["confidence"] == 0.95

    def test_compile_includes_scanner_and_dedupes(self):
        scanner = [
            {"kind": "hardcoded_secret", "severity": "critical", "detail": "x",
             "file": "a.py", "line": 1, "symbol": "X", "confidence": 0.99},
            {"kind": "hardcoded_secret", "severity": "critical", "detail": "x",
             "file": "a.py", "line": 1, "symbol": "X", "confidence": 0.5},
        ]
        node = [
            {"kind": "hardcoded_secret", "severity": "medium", "detail": "",
             "file": None, "line": 1, "confidence": 0.9},
            {"kind": "repl_error", "detail": "boom"},
        ]
        out = compile_findings(scanner, node)
        assert len(out) == 1
        assert out[0]["file"] == "a.py"
        assert out[0]["confidence"] == 0.99

    def test_compile_sorts_by_severity(self):
        scanner = [
            {"kind": "info", "severity": "low", "file": "a.py", "line": 1,
             "confidence": 0.9},
        ]
        node = [
            {"kind": "xss", "severity": "critical", "file": "b.py", "line": 2,
             "confidence": 0.9},
        ]
        out = compile_findings(scanner, node)
        assert out[0]["severity"] == "critical"
        assert out[1]["severity"] == "low"

    def test_validation_passed_is_noise(self):
        raw = {"kind": "validation_passed", "severity": "none",
               "detail": "complies", "file": "a.py", "line": 1}
        assert normalize_finding(raw) is None

    def test_compile_filters_nonexistent_files(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "real.py").write_text("x = 1\n")
            scanner = [{"kind": "xss", "severity": "high", "file": "real.py",
                        "line": 1, "confidence": 0.9}]
            node = [{"kind": "xss", "severity": "high", "file": "fake.py",
                     "line": 1, "confidence": 0.9}]
            out = compile_findings(scanner, node, target_path=td)
        assert len(out) == 1
        assert out[0]["file"] == "real.py"
