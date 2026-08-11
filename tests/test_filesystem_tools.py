"""Tests for generic filesystem tools."""
from rgi.tools.filesystem import find_files, list_dir, stat_file


def test_list_dir(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "sub").mkdir()
    result = list_dir({"path": str(tmp_path)})
    assert "error" not in result
    names = {e["name"] for e in result["entries"]}
    assert "a.py" in names
    assert "sub" in names


def test_list_dir_missing(tmp_path):
    result = list_dir({"path": str(tmp_path / "missing")})
    assert "error" in result


def test_find_files(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("z")
    result = find_files({"root": str(tmp_path), "pattern": "*.py"})
    assert "error" not in result
    files = result["files"]
    assert any("a.py" in f for f in files)
    assert any("c.py" in f for f in files)
    assert not any("b.txt" in f for f in files)


def test_stat_file(tmp_path):
    f = tmp_path / "demo.py"
    f.write_text("hello")
    result = stat_file({"path": str(f)})
    assert result["exists"] is True
    assert result["is_file"] is True
    assert result["size"] == 5


def test_stat_missing(tmp_path):
    result = stat_file({"path": str(tmp_path / "missing")})
    assert result["exists"] is False
