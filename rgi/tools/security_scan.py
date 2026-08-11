"""Deterministic security scanner that seeds RGI with grounded findings.

The scanner runs a fixed set of SAST-style checks over the target codebase and
returns findings that already cite file, line, and symbol. This lets small
local models focus on verification and explanation instead of discovery.
"""
import ast
import re
from pathlib import Path


_SECRET_RE = re.compile(
    r"(?P<name>[A-Z_]*(?:SECRET|API_KEY|TOKEN|PASSWORD|DATABASE_URL)[A-Z_]*)\s*=\s*['\"](?P<value>[^'\"]{6,})['\"]"
)

# Default credentials embedded in os.getenv fallbacks are not externally
# visible like hardcoded literals, but they still let the app start with a
# predictable secret when the environment variable is unset.
_ENVGET_RE = re.compile(
    r'os\.getenv\(\s*["\'](?P<name>[A-Z_]*(?:SECRET|API_KEY|TOKEN|PASSWORD|DATABASE_URL)[A-Z_]*)["\']\s*,\s*["\'](?P<value>[^"\']{4,})["\']\s*\)'
)


def _py_files(path: str) -> list[Path]:
    p = Path(path)
    return sorted(p.rglob("*.py")) if p.is_dir() else [p]


def find_hardcoded_secrets(path: str) -> list[dict]:
    """Find hardcoded secrets in Python source."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        for m in _SECRET_RE.finditer(text):
            findings.append({
                "kind": "hardcoded_secret",
                "severity": "critical",
                "detail": f"Hardcoded secret {m.group('name')}",
                "file": str(py_file),
                "line": text[: m.start()].count("\n") + 1,
                "symbol": m.group("name"),
                "confidence": 0.99,
            })
    return findings


def check_jwt_usage(path: str) -> list[dict]:
    """Find weak JWT usage patterns."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if "jwt.decode" in line:
                exp_checked = '"exp"' in text or "verify_exp" in text or "expired" in text.lower()
                if not exp_checked:
                    findings.append({
                        "kind": "jwt_decode_without_exp_check",
                        "severity": "high",
                        "detail": "jwt.decode called without expiration verification",
                        "file": str(py_file),
                        "line": i,
                        "symbol": "jwt.decode",
                        "confidence": 0.99,
                    })
            if re.search(r"algorithms\s*=\s*\[\s*['\"]HS256['\"]\s*\]", line):
                findings.append({
                    "kind": "jwt_hs256_only",
                    "severity": "medium",
                    "detail": "Only HS256 allowed; check for algorithm confusion exposure",
                    "file": str(py_file),
                    "line": i,
                    "symbol": "jwt.decode",
                    "confidence": 0.99,
                })
    return findings


def check_plaintext_passwords(path: str) -> list[dict]:
    """Find plaintext password comparisons."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        try:
            tree = ast.parse(py_file.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                # Look for `stored == provided_password` style comparisons
                # inside functions whose name suggests password checking.
                func = None
                # Walk up to enclosing function
                # ast.walk doesn't give parent; use simple heuristic: line context
                text = py_file.read_text(errors="replace")
                lines = text.splitlines()
                line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                if ("password" in line.lower() or "passwd" in line.lower()) and any(
                    isinstance(op, ast.Eq) for op in node.ops
                ):
                    findings.append({
                        "kind": "plaintext_password_comparison",
                        "severity": "critical",
                        "detail": "Plaintext password comparison without hashing",
                        "file": str(py_file),
                        "line": node.lineno,
                        "symbol": line.strip()[:80],
                        "confidence": 0.99,
                    })
    return findings


def _strip_comments(text: str) -> str:
    """Remove Python comments and docstrings from source text."""
    # Remove triple-quoted strings (docstrings).
    text = re.sub(r'"""[\s\S]*?"""', '""""""', text)
    text = re.sub(r"'''[\s\S]*?'''", "'''''", text)
    lines = []
    for line in text.splitlines():
        # Simple comment stripping; sufficient for keyword checks.
        if "#" in line:
            line = line[: line.index("#")]
        lines.append(line)
    return "\n".join(lines)


def check_session_timeout(path: str) -> list[dict]:
    """Find session stores without timeout/age checks."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        code_only = _strip_comments(text)
        if "session" in text.lower():
            has_expiry = (
                "expir" in code_only.lower()
                or "timeout" in code_only.lower()
                or "age" in code_only.lower()
                or "datetime" in code_only.lower()
                or "time.time" in code_only.lower()
            )
            has_validate = "validate_session" in text.lower() or "check_session" in text.lower()
            if has_validate and not has_expiry:
                for i, line in enumerate(text.splitlines(), start=1):
                    if "validate_session" in line.lower() or "create_session" in line.lower():
                        findings.append({
                            "kind": "session_without_timeout",
                            "severity": "high",
                            "detail": "Session validation does not check expiry/timeout",
                            "file": str(py_file),
                            "line": i,
                            "symbol": line.strip()[:80],
                            "confidence": 0.99,
                        })
                        break
    return findings


def find_env_fallback_secrets(path: str) -> list[dict]:
    """Find default secrets embedded in os.getenv(var, 'default') fallbacks."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        for m in _ENVGET_RE.finditer(text):
            findings.append({
                "kind": "hardcoded_secret",
                "severity": "high",
                "detail": f"Default {m.group('name')} in os.getenv fallback",
                "file": str(py_file),
                "line": text[: m.start()].count("\n") + 1,
                "symbol": m.group("name"),
                "confidence": 0.95,
            })
    return findings


def check_sql_injection(path: str) -> list[dict]:
    """Find SQL queries built from f-strings, .format(), or string concat."""
    findings = []
    sql_keywords = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|FROM|WHERE)\b", re.I)
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if not sql_keywords.search(line):
                continue
            stripped = line.strip()
            # f-string or .format() interpolation inside a SQL string
            if re.search(r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|DROP)', stripped, re.I):
                findings.append({
                    "kind": "sql_injection",
                    "severity": "critical",
                    "detail": "SQL query built with f-string interpolation",
                    "file": str(py_file),
                    "line": i,
                    "symbol": stripped[:80],
                    "confidence": 0.95,
                })
            elif ".format(" in stripped and sql_keywords.search(stripped):
                findings.append({
                    "kind": "sql_injection",
                    "severity": "critical",
                    "detail": "SQL query built with str.format() interpolation",
                    "file": str(py_file),
                    "line": i,
                    "symbol": stripped[:80],
                    "confidence": 0.9,
                })
            elif re.search(r"[\"'].*%s.*[\"']", stripped) and sql_keywords.search(stripped):
                findings.append({
                    "kind": "sql_injection",
                    "severity": "high",
                    "detail": "SQL query uses printf-style parameter placeholder; verify parameterization",
                    "file": str(py_file),
                    "line": i,
                    "symbol": stripped[:80],
                    "confidence": 0.7,
                })
    return findings


def check_path_traversal(path: str) -> list[dict]:
    """Find file reads where the path includes a user-controlled component."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            # os.path.join(base, filename) or base + filename near an open/read
            has_user_path = re.search(r"os\.path\.join\s*\([^)]*\b\w+name\b", stripped) or \
                            re.search(r"open\s*\(\s*os\.path\.join", stripped)
            if not has_user_path:
                continue
            findings.append({
                "kind": "path_traversal",
                "severity": "high",
                "detail": "File path built from user-controlled filename without validation",
                "file": str(py_file),
                "line": i,
                "symbol": stripped[:80],
                "confidence": 0.85,
            })
    return findings


def check_weak_crypto(path: str) -> list[dict]:
    """Find use of broken hash algorithms for passwords or secrets."""
    findings = []
    weak_algo = re.compile(r"hashlib\.(md5|sha1)\s*\(")
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            m = weak_algo.search(line)
            if not m:
                continue
            findings.append({
                "kind": "weak_crypto",
                "severity": "high",
                "detail": f"{m.group(1).upper()} is not suitable for password or secret hashing",
                "file": str(py_file),
                "line": i,
                "symbol": line.strip()[:80],
                "confidence": 0.95,
            })
    return findings


def check_command_injection(path: str) -> list[dict]:
    """Find shell commands built from user input."""
    findings = []
    for py_file in _py_files(path):
        if not py_file.is_file():
            continue
        text = py_file.read_text(errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            # os.system/subprocess.call with string concatenation or shell=True
            if re.search(r"os\.system\s*\(\s*['\"][^'\"]*['\"]\s*\+", stripped):
                findings.append({
                    "kind": "command_injection",
                    "severity": "critical",
                    "detail": "Shell command built by concatenating user input",
                    "file": str(py_file),
                    "line": i,
                    "symbol": stripped[:80],
                    "confidence": 0.95,
                })
            elif re.search(r"subprocess\.\w+\s*\([^)]*shell\s*=\s*True", stripped):
                findings.append({
                    "kind": "command_injection",
                    "severity": "high",
                    "detail": "subprocess invoked with shell=True; verify argument escaping",
                    "file": str(py_file),
                    "line": i,
                    "symbol": stripped[:80],
                    "confidence": 0.85,
                })
    return findings


def run_security_scan(path: str) -> list[dict]:
    """Run all deterministic security checks and return grounded findings."""
    findings = []
    findings.extend(find_hardcoded_secrets(path))
    findings.extend(find_env_fallback_secrets(path))
    findings.extend(check_jwt_usage(path))
    findings.extend(check_plaintext_passwords(path))
    findings.extend(check_session_timeout(path))
    findings.extend(check_sql_injection(path))
    findings.extend(check_path_traversal(path))
    findings.extend(check_weak_crypto(path))
    findings.extend(check_command_injection(path))
    return findings
