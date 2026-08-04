import pytest
from rgi.tools.registry import ToolRegistry

VULN_CODE = '''
import jwt

SECRET_KEY = "supersecret123"
API_KEY = "sk-live-abcdef123456"

def decode_token(token):
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

def check_password(stored, provided):
    return stored == provided
'''


@pytest.fixture
def code_file(tmp_path):
    f = tmp_path / "auth.py"
    f.write_text(VULN_CODE)
    return str(f)


async def test_parse_python_file(code_file):
    result = await ToolRegistry().execute("parse_python_file", {"path": code_file})
    assert "decode_token" in result["findings"][0]["functions"]
    assert result["confidence"] == 1.0


async def test_check_jwt_usage_finds_missing_expiration(code_file):
    result = await ToolRegistry().execute("check_jwt_usage", {"path": code_file})
    kinds = [f["kind"] for f in result["findings"]]
    assert "jwt_decode_without_exp_check" in kinds


async def test_find_hardcoded_secrets(code_file):
    result = await ToolRegistry().execute("find_hardcoded_secrets", {"path": code_file})
    assert len(result["findings"]) >= 2
    assert result["confidence"] >= 0.8


async def test_unknown_tool_raises():
    with pytest.raises(ValueError, match="unknown_tool"):
        await ToolRegistry().execute("nope", {})
