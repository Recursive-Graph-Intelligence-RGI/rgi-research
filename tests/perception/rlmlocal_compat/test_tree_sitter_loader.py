from pathlib import Path

from rgi.perception.rlmlocal_compat.tree_sitter_loader import load_parser, parse_file
from rgi.perception.rlmlocal_compat.language_packs import LANGUAGE_PACKS


def test_load_python_parser():
    parser = load_parser(LANGUAGE_PACKS["python"])
    assert parser is not None


def test_parse_python_file(tmp_path: Path):
    src = tmp_path / "hello.py"
    src.write_text("def foo():\n    return 1\n")
    tree = parse_file(src)
    assert tree is not None
    assert tree.root_node.type == "module"
    assert any(child.type == "function_definition" for child in tree.root_node.children)


def test_parse_javascript_file(tmp_path: Path):
    src = tmp_path / "hello.js"
    src.write_text("function foo() { return 1; }\n")
    tree = parse_file(src)
    assert tree is not None
    assert tree.root_node.type == "program"


def test_parse_typescript_file(tmp_path: Path):
    src = tmp_path / "hello.ts"
    src.write_text("function foo(): number { return 1; }\n")
    tree = parse_file(src)
    assert tree is not None
    assert tree.root_node.type == "program"


def test_parse_go_file(tmp_path: Path):
    src = tmp_path / "hello.go"
    src.write_text("package main\n\nfunc foo() int { return 1 }\n")
    tree = parse_file(src)
    assert tree is not None
    assert tree.root_node.type == "source_file"


def test_parse_rust_file(tmp_path: Path):
    src = tmp_path / "hello.rs"
    src.write_text("fn foo() -> i32 { 1 }\n")
    tree = parse_file(src)
    assert tree is not None
    assert tree.root_node.type == "source_file"


def test_parse_unsupported_extension(tmp_path: Path):
    src = tmp_path / "config.yaml"
    src.write_text("key: value\n")
    assert parse_file(src) is None
