from pathlib import Path
from rgi.tools.registry import ToolRegistry

SAMPLE = Path(__file__).parent.parent / "sample_project"


async def test_tools_detect_all_planted_vulnerabilities():
    registry = ToolRegistry()

    jwt_result = await registry.execute("check_jwt_usage", {"path": str(SAMPLE / "auth.py")})
    assert any(f["kind"] == "jwt_decode_without_exp_check" for f in jwt_result["findings"])

    secrets = await registry.execute("find_hardcoded_secrets", {"path": str(SAMPLE / "config.py")})
    assert len(secrets["findings"]) >= 2

    login_hits = await registry.execute("grep_security_patterns",
                                        {"path": str(SAMPLE / "login.py"),
                                         "keywords": ["password"]})
    assert login_hits["findings"]

    session_hits = await registry.execute("grep_security_patterns",
                                          {"path": str(SAMPLE / "session.py"),
                                           "keywords": ["session"]})
    assert session_hits["findings"]
