"""Port of rlmlocal's call-graph edge builder (importGraph call edges).

Builds file-level call edges from per-file CodeStructure call sites. Like
``import_graph`` this is conservative: an edge is created only when the callee
resolves to a single unambiguous definition within the analyzed root, so the
graph never fabricates call relationships.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rgi.perception.rlmlocal_compat.structure_extractor import CodeStructure


@dataclass
class CallGraph:
    edges: list[dict] = field(default_factory=list)


def _index_symbol_defs(structs: dict[Path, CodeStructure]) -> dict[str, list[dict]]:
    symbol_defs: dict[str, list[dict]] = {}
    for path, struct in structs.items():
        for fn in struct.functions:
            symbol_defs.setdefault(fn["name"], []).append(
                {"file": str(path), "kind": "function"}
            )
        for cls in struct.classes:
            symbol_defs.setdefault(cls["name"], []).append(
                {"file": str(path), "kind": "class"}
            )
        for method in struct.methods:
            symbol_defs.setdefault(method["name"], []).append(
                {"file": str(path), "kind": "method", "class": method.get("class")}
            )
    return symbol_defs


def _files_by_stem(structs: dict[Path, CodeStructure]) -> dict[str, Path]:
    files_by_stem: dict[str, Path] = {}
    for path in structs.keys():
        files_by_stem.setdefault(path.stem, path)
    return files_by_stem


def build_call_graph(
    root: Path,
    structs: dict[Path, CodeStructure],
    symbol_defs: dict[str, list[dict]] | None = None,
) -> CallGraph:
    """Build conservative file-level call edges across all supported languages.

    Resolution order for a callee:
      1. Dotted callee (``module.func``): the head resolves to a module file.
      2. Rust ``crate::mod::func``: the module part resolves to a file stem.
      3. Bare symbol: must have exactly one definition, in a different file.

    Args:
        root: The project root (used for relative path reporting).
        structs: Mapping from file Path to extracted CodeStructure.
        symbol_defs: Optional prebuilt symbol index (from import_graph).

    Returns:
        CallGraph with resolved call edges.
    """
    if symbol_defs is None:
        symbol_defs = _index_symbol_defs(structs)

    files_by_stem = _files_by_stem(structs)

    graph = CallGraph()
    seen: set[tuple] = set()

    for path, struct in structs.items():
        for call in struct.calls:
            callee = (call.get("callee") or "").strip()
            if not callee:
                continue
            target: Path | None = None
            symbol = callee

            if callee.startswith("crate::"):
                parts = callee.split("::")
                if len(parts) >= 2:
                    t = files_by_stem.get(parts[1])
                    if t and t != path:
                        target = t
            elif "." in callee:
                head = callee.split(".")[0]
                t = files_by_stem.get(head)
                if t and t != path:
                    target = t
            else:
                defs = symbol_defs.get(callee, [])
                files = {d["file"] for d in defs}
                if len(files) == 1 and str(path) not in files:
                    target = Path(next(iter(files)))

            if target is not None:
                key = (str(path), str(target), symbol, call.get("line"))
                if key not in seen:
                    seen.add(key)
                    graph.edges.append({
                        "source_file": str(path),
                        "target_file": str(target),
                        "symbol": symbol,
                        "line": call.get("line"),
                        "kind": "call",
                    })

    return graph
