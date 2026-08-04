"""Deterministic security-analysis tools. Tools are neurons too: structured
output with confidence, no orchestration."""
import ast
import re
from pathlib import Path

_SECRET_RE = re.compile(
    r"""(?P<name>[A-Z_]*(?:SECRET|API_KEY|TOKEN|PASSWORD)[A-Z_]*)\s*=\s*["'](?P<value>[^"']{6,})["']"""
)


def _read_source(path: str) -> str:
    """Tools accept a file OR a directory (all *.py files concatenated)."""
    p = Path(path)
    if p.is_dir():
        return "\n".join(f.read_text() for f in sorted(p.glob("*.py")))
    return p.read_text()


def _py_files(path: str) -> list:
    p = Path(path)
    return sorted(p.glob("*.py")) if p.is_dir() else [p]


class ToolRegistry:
    def __init__(self):
        self.tools = {
            "parse_python_file": self._parse_python_file,
            "grep_security_patterns": self._grep_security_patterns,
            "check_jwt_usage": self._check_jwt_usage,
            "find_hardcoded_secrets": self._find_hardcoded_secrets,
        }

    async def execute(self, tool_name: str, params: dict) -> dict:
        fn = self.tools.get(tool_name)
        if fn is None:
            raise ValueError(f"unknown_tool: {tool_name}")
        return fn(params)

    def _parse_python_file(self, params: dict) -> dict:
        classes, functions, imports = [], [], []
        for py_file in _py_files(params["path"]):
            tree = ast.parse(py_file.read_text())
            classes.extend(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
            functions.extend(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
            imports.extend(
                a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
            )
        return {
            "findings": [{"classes": classes, "functions": functions, "imports": imports}],
            "confidence": 1.0,
        }

    def _grep_security_patterns(self, params: dict) -> dict:
        text = _read_source(params["path"])
        keywords = params.get("keywords", ["jwt", "session", "password", "secret", "token"])
        findings = [
            {"kind": "keyword_hit", "keyword": k, "line": i + 1}
            for i, line in enumerate(text.splitlines())
            for k in keywords
            if k in line.lower()
        ]
        return {"findings": findings, "confidence": 0.75}

    def _check_jwt_usage(self, params: dict) -> dict:
        text = _read_source(params["path"])
        findings = []
        if "jwt.decode" in text:
            exp_checked = '"exp"' in text or "verify_exp" in text or "expired" in text.lower()
            if not exp_checked:
                findings.append({
                    "kind": "jwt_decode_without_exp_check",
                    "severity": "high",
                    "detail": "jwt.decode called without any expiration verification",
                })
        if re.search(r"algorithms\s*=\s*\[\s*[\"']HS256[\"']\s*\]", text):
            findings.append({
                "kind": "jwt_hs256_only",
                "severity": "medium",
                "detail": "Only HS256 allowed; check for algorithm confusion exposure",
            })
        return {"findings": findings, "confidence": 0.8}

    def _find_hardcoded_secrets(self, params: dict) -> dict:
        text = _read_source(params["path"])
        findings = [
            {"kind": "hardcoded_secret", "name": m.group("name"), "line": text[: m.start()].count("\n") + 1}
            for m in _SECRET_RE.finditer(text)
        ]
        return {"findings": findings, "confidence": 0.9}
