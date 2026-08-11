from rgi.core.harness import Harness, HarnessConfig
from rgi.reasoning.frontier_integration import FrontierConfig


def test_harness_exposes_frontier_config():
    cfg = HarnessConfig(frontier_config=FrontierConfig(enabled=True))
    harness = Harness(cfg)
    assert harness.frontier_config.enabled is True
    assert harness.frontier is not None
