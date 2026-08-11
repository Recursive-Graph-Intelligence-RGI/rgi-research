"""Shadow verification tools for RGI findings.

These tools run lightweight, deterministic checks against source code so the
recursive engine can confirm or challenge a finding without relying solely on
LLM confidence.
"""
import py_compile
import subprocess
from pathlib import Path


def run_py_compile(params: dict) -> dict:
    """Check that a Python file compiles without syntax errors."""
    path = Path(params["path"])
    try:
        py_compile.compile(str(path), doraise=True)
        return {"findings": [{"file": str(path), "ok": True}], "confidence": 1.0}
    except py_compile.PyCompileError as exc:
        return {
            "findings": [{"file": str(path), "ok": False, "error": str(exc)}],
            "confidence": 1.0,
        }


def run_pytest(params: dict) -> dict:
    """Run pytest on a file or directory and report the outcome."""
    path = Path(params["path"])
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", str(path), "-q", "--tb=no"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "findings": [
                {
                    "file": str(path),
                    "ok": result.returncode == 0,
                    "output": result.stdout,
                }
            ],
            "confidence": 1.0,
        }
    except Exception as exc:
        return {"findings": [{"file": str(path), "ok": False, "error": str(exc)}], "confidence": 0.5}


def run_pyflakes(params: dict) -> dict:
    """Run pyflakes on a file if it is installed."""
    path = Path(params["path"])
    try:
        result = subprocess.run(
            ["python", "-m", "pyflakes", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "findings": [
                {
                    "file": str(path),
                    "ok": result.returncode == 0,
                    "output": result.stdout,
                }
            ],
            "confidence": 1.0,
        }
    except FileNotFoundError:
        return {
            "findings": [
                {
                    "file": str(path),
                    "ok": True,
                    "error": "pyflakes not installed",
                }
            ],
            "confidence": 0.5,
        }
