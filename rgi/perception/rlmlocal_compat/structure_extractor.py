"""Port of rlmlocal's StructureExtractor.ts to Python.

Extracts structural facts from a source file: functions, classes, methods,
imports, and call sites. Python is fully supported; other language families
fall back to a conservative regex/label-only extraction until their tree-sitter
walkers are implemented.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Tree

from rgi.perception.rlmlocal_compat.language_packs import lang_family
from rgi.perception.rlmlocal_compat.tree_sitter_loader import parse_file


@dataclass
class CodeStructure:
    functions: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    methods: list[dict] = field(default_factory=list)
    imports: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    call_sites: list[dict] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _first_child_of_type(node: Node, node_type: str) -> Node | None:
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def _extract_python(tree: Tree, source: bytes) -> CodeStructure:
    struct = CodeStructure()
    root = tree.root_node

    def walk(node: Node) -> None:
        # Top-level functions and classes
        if node.parent == root:
            if node.type == "function_definition":
                name_node = _first_child_of_type(node, "identifier")
                if name_node:
                    struct.functions.append({
                        "name": _node_text(name_node, source),
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })
            elif node.type == "class_definition":
                class_name = _first_child_of_type(node, "identifier")
                if class_name:
                    class_name_text = _node_text(class_name, source)
                    struct.classes.append({
                        "name": class_name_text,
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })
                    body = _first_child_of_type(node, "block")
                    if body:
                        for child in body.children:
                            if child.type == "function_definition":
                                method_name = _first_child_of_type(child, "identifier")
                                if method_name:
                                    struct.methods.append({
                                        "name": _node_text(method_name, source),
                                        "class": class_name_text,
                                        "line": child.start_point[0] + 1,
                                        "span": (child.start_byte, child.end_byte),
                                    })

        # Imports
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    struct.imports.append({
                        "name": _node_text(child, source),
                        "line": node.start_point[0] + 1,
                        "is_from": False,
                    })
                elif child.type == "aliased_import":
                    dotted = _first_child_of_type(child, "dotted_name")
                    if dotted:
                        struct.imports.append({
                            "name": _node_text(dotted, source),
                            "line": node.start_point[0] + 1,
                            "is_from": False,
                        })
        elif node.type == "import_from_statement":
            dotted_names = [c for c in node.children if c.type == "dotted_name"]
            if len(dotted_names) >= 2:
                module_name = _node_text(dotted_names[0], source)
                for name_node in dotted_names[1:]:
                    struct.imports.append({
                        "name": _node_text(name_node, source),
                        "module": module_name,
                        "line": node.start_point[0] + 1,
                        "is_from": True,
                    })

        # Call sites
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func:
                struct.calls.append({
                    "callee": _node_text(func, source),
                    "line": node.start_point[0] + 1,
                    "span": (node.start_byte, node.end_byte),
                })

        for child in node.children:
            walk(child)

    walk(root)
    return struct


def _extract_js(tree: Tree, source: bytes) -> CodeStructure:
    """Extract structure from JavaScript / TypeScript source."""
    struct = CodeStructure()
    root = tree.root_node

    def _name(node: Node) -> str | None:
        ident = _first_child_of_type(node, "identifier")
        if ident:
            return _node_text(ident, source)
        # property "name" for method definitions: { foo() {} }
        prop = node.child_by_field_name("name")
        if prop:
            return _node_text(prop, source)
        return None

    def walk(node: Node) -> None:
        # Top-level declarations, including export-wrapped ones (export function
        # x() {} has parent export_statement, not program).
        parent = node.parent
        at_top = parent == root or (
            parent is not None
            and parent.type == "export_statement"
            and parent.parent == root
        )
        if at_top:
            if node.type in ("function_declaration", "function_expression", "arrow_function"):
                name = _name(node)
                if name:
                    struct.functions.append({
                        "name": name,
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })
            elif node.type == "class_declaration":
                name = _name(node)
                if name:
                    struct.classes.append({
                        "name": name,
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })
                    body = _first_child_of_type(node, "class_body")
                    if body:
                        for child in body.children:
                            if child.type == "method_definition":
                                mname = _name(child)
                                if mname:
                                    struct.methods.append({
                                        "name": mname,
                                        "class": name,
                                        "line": child.start_point[0] + 1,
                                        "span": (child.start_byte, child.end_byte),
                                    })

        if node.type == "import_statement":
            # Child order varies: [import, import_clause, from, string] or
            # [import, string, from, import_clause]. Resolve the source first
            # so the clause branch can attach it.
            source_value = None
            for child in node.children:
                if child.type == "string":
                    source_value = _node_text(child, source).strip("'\"")
            for child in node.children:
                if child.type == "import_clause":
                    for sub in child.children:
                        if sub.type == "identifier":
                            struct.imports.append({
                                "name": _node_text(sub, source),
                                "module": source_value,
                                "line": node.start_point[0] + 1,
                                "is_from": True,
                            })
                        elif sub.type == "namespace_import":
                            ident = _first_child_of_type(sub, "identifier")
                            if ident:
                                struct.imports.append({
                                    "name": _node_text(ident, source),
                                    "module": source_value,
                                    "line": node.start_point[0] + 1,
                                    "is_from": True,
                                })
                        elif sub.type == "named_imports":
                            for spec in sub.children:
                                if spec.type == "import_specifier":
                                    ident = _first_child_of_type(spec, "identifier")
                                    if ident:
                                        struct.imports.append({
                                            "name": _node_text(ident, source),
                                            "module": source_value,
                                            "line": node.start_point[0] + 1,
                                            "is_from": True,
                                        })

        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                struct.calls.append({
                    "callee": _node_text(func, source),
                    "line": node.start_point[0] + 1,
                    "span": (node.start_byte, node.end_byte),
                })

        for child in node.children:
            walk(child)

    walk(root)
    return struct


def _extract_go(tree: Tree, source: bytes) -> CodeStructure:
    """Extract structure from Go source."""
    struct = CodeStructure()
    root = tree.root_node

    def walk(node: Node) -> None:
        if node.parent == root:
            if node.type == "function_declaration":
                name = _first_child_of_type(node, "identifier")
                if name:
                    struct.functions.append({
                        "name": _node_text(name, source),
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })
            elif node.type == "method_declaration":
                name = _first_child_of_type(node, "field_identifier")
                if name:
                    struct.methods.append({
                        "name": _node_text(name, source),
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })

        if node.type == "import_declaration":
            spec = _first_child_of_type(node, "import_spec")
            if spec:
                path_node = _first_child_of_type(spec, "interpreted_string_literal")
                if path_node:
                    struct.imports.append({
                        "name": _node_text(path_node, source).strip('"'),
                        "line": node.start_point[0] + 1,
                        "is_from": False,
                    })

        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                struct.calls.append({
                    "callee": _node_text(func, source),
                    "line": node.start_point[0] + 1,
                    "span": (node.start_byte, node.end_byte),
                })

        for child in node.children:
            walk(child)

    walk(root)
    return struct


def _extract_rust(tree: Tree, source: bytes) -> CodeStructure:
    """Extract structure from Rust source."""
    struct = CodeStructure()
    root = tree.root_node

    def walk(node: Node) -> None:
        if node.parent == root:
            if node.type == "function_item":
                name = _first_child_of_type(node, "identifier")
                if name:
                    struct.functions.append({
                        "name": _node_text(name, source),
                        "line": node.start_point[0] + 1,
                        "span": (node.start_byte, node.end_byte),
                    })

        if node.type == "use_declaration":
            for child in node.children:
                if child.type in ("identifier", "scoped_identifier"):
                    struct.imports.append({
                        "name": _node_text(child, source),
                        "line": node.start_point[0] + 1,
                        "is_from": False,
                    })

        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                struct.calls.append({
                    "callee": _node_text(func, source),
                    "line": node.start_point[0] + 1,
                    "span": (node.start_byte, node.end_byte),
                })

        for child in node.children:
            walk(child)

    walk(root)
    return struct


def _regex_fallback(path: Path, source: str) -> CodeStructure:
    """Minimal fallback for unsupported languages: functions/classes by regex."""
    struct = CodeStructure()
    lines = source.splitlines()
    function_pattern = re.compile(r"^\s*(?:def|function|func)\s+(\w+)")
    class_pattern = re.compile(r"^\s*(?:class)\s+(\w+)")
    for i, line in enumerate(lines, start=1):
        m = function_pattern.match(line)
        if m:
            struct.functions.append({"name": m.group(1), "line": i})
        m = class_pattern.match(line)
        if m:
            struct.classes.append({"name": m.group(1), "line": i})
    return struct


def extract_structure(path: Path) -> CodeStructure:
    """Extract structural facts from a source file.

    Uses tree-sitter for supported languages; falls back to conservative regex
    for unsupported extensions. Missing or unparseable files return an empty
    structure instead of crashing the ingestion pipeline.
    """
    if not path.is_file():
        return CodeStructure()
    family = lang_family(path.suffix)
    try:
        tree = parse_file(path)
    except Exception:
        return _regex_fallback(path, path.read_text(errors="replace"))
    if tree is None:
        return _regex_fallback(path, path.read_text(errors="replace"))

    source = path.read_bytes()
    if family == "python":
        return _extract_python(tree, source)
    if family == "js":
        return _extract_js(tree, source)
    if family == "go":
        return _extract_go(tree, source)
    if family == "rust":
        return _extract_rust(tree, source)

    return _regex_fallback(path, source.decode("utf-8", errors="replace"))
