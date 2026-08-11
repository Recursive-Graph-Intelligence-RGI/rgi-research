import tempfile
from pathlib import Path

from rgi.tools.security_scan import run_security_scan


class TestSecurityScan:
    def test_finds_hardcoded_secret(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "config.py"
            p.write_text('API_KEY = "sk-live-1234567890"\n')
            findings = run_security_scan(td)
        assert len(findings) == 1
        assert findings[0]["kind"] == "hardcoded_secret"
        assert findings[0]["symbol"] == "API_KEY"

    def test_finds_osgetenv_fallback_secret(self):
        """Default credentials embedded in os.getenv fallbacks are real secrets."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "db.py"
            p.write_text(
                'password = os.getenv("POSTGRES_PASSWORD", "default_password")\n'
            )
            findings = run_security_scan(td)
        assert any(
            f["kind"] == "hardcoded_secret" and "POSTGRES_PASSWORD" in f["detail"]
            for f in findings
        ), findings

    def test_finds_sql_injection(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "db.py"
            p.write_text('query = f"SELECT * FROM users WHERE name = \'{name}\'"\n')
            findings = run_security_scan(td)
        assert any(f["kind"] == "sql_injection" for f in findings), findings

    def test_finds_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "files.py"
            p.write_text('path = os.path.join("/var/data/reports", filename)\n')
            findings = run_security_scan(td)
        assert any(f["kind"] == "path_traversal" for f in findings), findings

    def test_finds_weak_crypto_md5(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "crypto.py"
            p.write_text('return hashlib.md5(password.encode()).hexdigest()\n')
            findings = run_security_scan(td)
        assert any(f["kind"] == "weak_crypto" and "md5" in f["detail"].lower() for f in findings), findings

    def test_finds_command_injection(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "shell.py"
            p.write_text('os.system("ping -c 1 " + host)\n')
            findings = run_security_scan(td)
        assert any(f["kind"] == "command_injection" for f in findings), findings
