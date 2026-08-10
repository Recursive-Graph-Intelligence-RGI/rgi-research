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

    def test_is_noise_rejects_non_dict(self):
        assert is_noise("plain string") is True
        assert is_noise(None) is True
        assert is_noise(["list"]) is True

    def test_findings_list_skips_noise(self):
        raw_findings = [
            {"kind": "sql_injection", "file": "api/main.py", "confidence": 0.8},
            {"kind": "keyword_hit", "keyword": "of", "line": 12},
            {"kind": "xss", "file": "web/app.py", "confidence": 0.7},
        ]
        normalized = [f for f in map(normalize_finding, raw_findings) if f is not None]
        assert len(normalized) == 2
        assert normalized[0]["kind"] == "sql_injection"
        assert normalized[1]["kind"] == "xss"

    def test_malformed_confidence_defaults(self):
        raw = {"kind": "sql_injection", "file": "api/main.py", "confidence": "not-a-number"}
        out = normalize_finding(raw)
        assert out["confidence"] == 0.5

    def test_missing_confidence_defaults(self):
        raw = {"kind": "sql_injection", "file": "api/main.py"}
        out = normalize_finding(raw)
        assert out["confidence"] == 0.5
