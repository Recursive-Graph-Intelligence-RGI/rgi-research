"""Tests for the eval scorer term normalization (underscore/hyphen vs space)."""
import pytest

from rgi.eval import score_recall, score_report_full


GT = {"vulns": [
    {"id": "v1", "terms": ["sql injection", "sqli"]},
    {"id": "v2", "terms": ["stored xss", "cross-site scripting", "xss"]},
    {"id": "v3", "terms": ["hardcoded credential", "hardcoded secret"]},
]}


def test_score_recall_matches_underscore_kind():
    report = {"findings": [{"kind": "sql_injection", "file": "a.py", "line": 1}]}
    assert score_recall(report, GT) == pytest.approx(1 / 3)


def test_score_report_full_normalizes_underscore():
    report = {"findings": [
        {"kind": "sql_injection", "file": "a.py", "line": 1},
        {"kind": "hardcoded_secret", "file": "b.py", "line": 2},
    ]}
    graded = score_report_full(report, GT)
    # scorer rounds to 3 decimals
    assert graded["recall"] == pytest.approx(round(2 / 3, 3))  # sql_injection + hardcoded_secret both match
    assert graded["precision"] == 1.0  # both findings match a term


def test_score_report_full_matches_llm_space_wording():
    report = {"findings": [
        {"kind": "vulnerability", "detail": "SQL injection in query", "file": "a.py"},
    ]}
    graded = score_report_full(report, GT)
    assert graded["recall"] == pytest.approx(round(1 / 3, 3))


def test_score_report_full_dedupes():
    report = {"findings": [
        {"kind": "sql_injection", "file": "a.py", "line": 1},
        {"kind": "sql_injection", "file": "a.py", "line": 1},
    ]}
    graded = score_report_full(report, GT)
    assert graded["findings_raw"] == 2
    assert graded["findings_deduped"] == 1
