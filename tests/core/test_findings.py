import pytest
from rgi.core.findings import normalize_finding, is_noise


class TestFindingNormalization:
    def test_accepts_grounded_vulnerability(self):
        raw = {
            "kind": "sql_injection",
            "severity": "high",
            "file": "api/main.py",
            "line": 42,
            "detail": "User input concatenated into SQL",
            "confidence": 0.8,
        }
        out = normalize_finding(raw)
        assert out["kind"] == "sql_injection"
        assert out["severity"] == "high"
        assert out["grounded"] is True

    def test_rejects_keyword_hit_noise(self):
        raw = {"kind": "keyword_hit", "keyword": "of", "line": 12}
        assert normalize_finding(raw) is None
        assert is_noise(raw) is True

    def test_rejects_source_dump(self):
        raw = {"classes": [], "functions": [], "imports": [], "source_excerpt": "..."}
        assert normalize_finding(raw) is None

    def test_adds_default_severity(self):
        raw = {"kind": "weak_secret", "detail": "short secret"}
        out = normalize_finding(raw)
        assert out["severity"] == "medium"
