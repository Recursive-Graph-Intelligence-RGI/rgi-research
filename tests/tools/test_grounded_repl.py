from pathlib import Path

from rgi.tools.grounded_repl import callers, grep, read_file


def test_read_file_range(tmp_path: Path):
    src = tmp_path / "x.py"
    src.write_text("line1\nline2\nline3\n")
    result = read_file({"path": str(src), "line_start": 2, "line_end": 3})
    assert "line2" in result["findings"][0]["content"]
    assert "line1" not in result["findings"][0]["content"]


def test_read_file_full(tmp_path: Path):
    src = tmp_path / "x.py"
    src.write_text("line1\nline2\n")
    result = read_file({"path": str(src)})
    assert "line1" in result["findings"][0]["content"]
    assert "line2" in result["findings"][0]["content"]


def test_grep(tmp_path: Path):
    (tmp_path / "a.py").write_text("def secret(): pass\n")
    (tmp_path / "b.py").write_text("x = 1\n")
    result = grep({"pattern": "secret", "root": str(tmp_path)})
    assert len(result["findings"]) == 1
    assert result["findings"][0]["file"].endswith("a.py")


def test_callers_filters_by_symbol():
    edges = [
        {"source_file": "a.py", "target_file": "b.py", "symbol": "helper"},
        {"source_file": "c.py", "target_file": "d.py", "symbol": "other"},
    ]
    result = callers({"symbol": "helper", "import_graph_edges": edges})
    assert len(result["findings"]) == 1
    assert result["findings"][0]["source_file"] == "a.py"
