from pathlib import Path

from rgi.tools.verify import run_py_compile, run_pyflakes, run_pytest


def test_py_compile_good_file(tmp_path: Path):
    src = tmp_path / "good.py"
    src.write_text("def add(x, y): return x + y\n")
    result = run_py_compile({"path": str(src)})
    assert result["findings"][0]["ok"] is True


def test_py_compile_bad_file(tmp_path: Path):
    src = tmp_path / "bad.py"
    src.write_text("def add(x, y): return x +\n")
    result = run_py_compile({"path": str(src)})
    assert result["findings"][0]["ok"] is False


def test_pytest_runs_passing_test(tmp_path: Path):
    src = tmp_path / "test_good.py"
    src.write_text("def test_ok(): assert True\n")
    result = run_pytest({"path": str(src)})
    assert result["findings"][0]["ok"] is True


def test_pytest_runs_failing_test(tmp_path: Path):
    src = tmp_path / "test_bad.py"
    src.write_text("def test_fail(): assert False\n")
    result = run_pytest({"path": str(src)})
    assert result["findings"][0]["ok"] is False


def test_pyflakes_missing_is_graceful(tmp_path: Path):
    src = tmp_path / "clean.py"
    src.write_text("x = 1\n")
    result = run_pyflakes({"path": str(src)})
    # pyflakes may not be installed; either way the call should not crash.
    assert "findings" in result
