import json
from rgi.cli import main
from rgi.reasoning.frontier_integration import FrontierConfig


def test_frontier_config_from_env_values():
    cfg = FrontierConfig(
        enabled=True,
        model="kimi-k2",
        max_arbitration_calls=2,
    )
    assert cfg.enabled
    assert cfg.model == "kimi-k2"
    assert cfg.max_arbitration_calls == 2


def test_e2e_mock_run(tmp_path, capsys):
    output = tmp_path / "report.json"
    rc = main(["analyze", "sample_project",
               "--objective", "Analyze authentication security",
               "--output", str(output), "--mock"])
    assert rc == 0
    report = json.loads(output.read_text())

    # SUCCESS CRITERIA
    assert report["status"] == "completed"
    assert report["graphs_spawned"] >= 3            # autonomous spawning
    assert report["corrections_made"] >= 1          # self-correction happened
    assert report["max_depth_reached"] <= 2         # depth limit held (root=0)
    assert report["llm_calls"] <= 20                # budget held
    assert report["aggregate_confidence"] >= 0.7
    assert report["findings"]                       # non-empty
    assert report["topology_used"]["subgraphs"]     # topology reported
    assert report["execution_log"]                  # auditable
    assert any("verification" in s for s in report["topology_used"]["subgraphs"])
