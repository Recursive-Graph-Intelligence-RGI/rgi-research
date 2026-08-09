import json
from rgi.cli import main
from rgi.eval import TARGETS, score_recall


def test_score_recall_term_matching():
    gt = {"vulns": [{"id": "a", "terms": ["expir"]}, {"id": "b", "terms": ["md5"]}]}
    report = {"findings": [{"finding": "tokens never expire"}]}
    assert score_recall(report, gt) == 0.5


def test_score_report_full_dedupes_and_measures_precision():
    from rgi.eval import score_report_full
    gt = {"vulns": [{"id": "a", "terms": ["expir"]},
                    {"id": "b", "terms": ["md5"]},
                    {"id": "c", "terms": ["pickle"]},
                    {"id": "d", "terms": ["ssrf"]}]}
    dupes = [{"finding": "tokens never expire"}] * 50  # findings lottery
    report = {"findings": dupes + [{"finding": "unrelated noise"}]}
    graded = score_report_full(report, gt)
    assert graded["recall"] == 0.25          # one real vuln, not fifty
    assert graded["findings_raw"] == 51
    assert graded["findings_deduped"] == 2
    assert graded["precision"] == 0.5        # 1 of 2 unique findings is relevant


def test_eval_matrix_mock(tmp_path):
    output = tmp_path / "eval.json"
    rc = main(["eval", "--objective", "Analyze authentication security",
               "--runs", "1", "--output", str(output), "--mock"])
    assert rc == 0
    result = json.loads(output.read_text())
    # N targets x 3 conditions x 1 run
    assert len(result["matrix"]) == 3 * len(TARGETS)
    keys = {(m["target"], m["condition"]) for m in result["matrix"]}
    assert ("sample_project", "rgi") in keys
    assert ("vuln_app_2", "fixed") in keys
    assert ("vuln_app_3", "rgi") in keys
    # summary has mean recall/calls per target+condition
    s = result["summary"]["sample_project|rgi"]
    assert 0.0 <= s["mean_recall"] <= 1.0
    assert s["mean_calls"] >= 1
    # mock RGI on its home target should still find planted vulns
    assert s["mean_recall"] > 0.0
