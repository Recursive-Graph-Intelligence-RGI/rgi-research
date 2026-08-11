from pathlib import Path

from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


def test_extracts_function_and_imports(tmp_path: Path):
    src = tmp_path / "demo.py"
    src.write_text("""
import os
from json import loads

def greet(name: str) -> str:
    return f"hello {name}"
""".strip())
    struct = extract_structure(src)
    assert len(struct.functions) == 1
    assert struct.functions[0]["name"] == "greet"
    assert struct.functions[0]["line"] == 4

    import_names = {i["name"] for i in struct.imports}
    assert "os" in import_names
    assert "loads" in import_names


def test_extracts_class_and_method(tmp_path: Path):
    src = tmp_path / "demo.py"
    src.write_text("""
class Greeter:
    def greet(self, name: str) -> str:
        return f"hello {name}"
""".strip())
    struct = extract_structure(src)
    assert len(struct.classes) == 1
    assert struct.classes[0]["name"] == "Greeter"
    assert struct.classes[0]["line"] == 1
    assert len(struct.methods) == 1
    assert struct.methods[0]["name"] == "greet"
    assert struct.methods[0]["class"] == "Greeter"


def test_extracts_call_sites(tmp_path: Path):
    src = tmp_path / "demo.py"
    src.write_text("""
def helper(x):
    return x + 1

def main():
    result = helper(1)
    print(result)
""".strip())
    struct = extract_structure(src)
    callees = {c["callee"] for c in struct.calls}
    assert "helper" in callees
    assert "print" in callees


def test_extracts_from_imports(tmp_path: Path):
    src = tmp_path / "demo.py"
    src.write_text("from collections import OrderedDict, namedtuple\n")
    struct = extract_structure(src)
    names = {i["name"] for i in struct.imports}
    assert "OrderedDict" in names
    assert "namedtuple" in names
    assert all(i.get("module") == "collections" for i in struct.imports)


def test_extracts_javascript_function(tmp_path: Path):
    src = tmp_path / "demo.js"
    src.write_text("function greet(name) { return `hello ${name}`; }\n")
    struct = extract_structure(src)
    assert len(struct.functions) == 1
    assert struct.functions[0]["name"] == "greet"


def test_extracts_typescript_class_and_method(tmp_path: Path):
    src = tmp_path / "demo.ts"
    src.write_text("class Greeter { greet(name: string): string { return `hello ${name}`; } }\n")
    struct = extract_structure(src)
    assert len(struct.classes) == 1
    assert struct.classes[0]["name"] == "Greeter"
    assert len(struct.methods) == 1
    assert struct.methods[0]["name"] == "greet"


def test_extracts_go_function(tmp_path: Path):
    src = tmp_path / "demo.go"
    src.write_text("package main\n\nfunc Add(a, b int) int { return a + b }\n")
    struct = extract_structure(src)
    assert len(struct.functions) == 1
    assert struct.functions[0]["name"] == "Add"


def test_extracts_rust_function(tmp_path: Path):
    src = tmp_path / "demo.rs"
    src.write_text("fn add(a: i32, b: i32) -> i32 { a + b }\n")
    struct = extract_structure(src)
    assert len(struct.functions) == 1
    assert struct.functions[0]["name"] == "add"


def test_unsupported_file_falls_back(tmp_path: Path):
    src = tmp_path / "demo.rb"
    src.write_text("def foo\n  1\nend\n")
    struct = extract_structure(src)
    assert len(struct.functions) == 1
    assert struct.functions[0]["name"] == "foo"
