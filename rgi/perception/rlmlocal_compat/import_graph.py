"""Port of rlmlocal's importGraph.ts core edge builder.

Builds import/call edges between files from per-file CodeStructure extractions.
This is a conservative, deterministic builder: an edge is only created when the
target module/symbol can be resolved unambiguously within the analyzed root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rgi.perception.rlmlocal_compat.structure_extractor import CodeStructure


@dataclass
class ImportGraph:
    edges: list[dict] = field(default_factory=list)
    reverse_edges: dict[str, list[dict]] = field(default_factory=dict)
    symbol_defs: dict[str, list[dict]] = field(default_factory=dict)


def build_import_graph(root: Path, structs: dict[Path, CodeStructure]) -> ImportGraph:
    """Build an import graph for all Python files under root.

    Args:
        root: The project root (used for relative path reporting).
        structs: Mapping from file Path to extracted CodeStructure.

    Returns:
        ImportGraph with resolved import edges and symbol definition index.
    """
    graph = ImportGraph()
    files_by_stem: dict[str, Path] = {}
    for path in structs.keys():
        if path.suffix == ".py":
            files_by_stem[path.stem] = path

    # Index symbol definitions
    for path, struct in structs.items():
        for fn in struct.functions:
            graph.symbol_defs.setdefault(fn["name"], []).append(
                {"file": str(path), "kind": "function"}
            )
        for cls in struct.classes:
            graph.symbol_defs.setdefault(cls["name"], []).append(
                {"file": str(path), "kind": "class"}
            )
        for method in struct.methods:
            graph.symbol_defs.setdefault(method["name"], []).append(
                {"file": str(path), "kind": "method", "class": method.get("class")}
            )

    # Build import edges
    for path, struct in structs.items():
        for imp in struct.imports:
            target: Path | None = None
            symbol: str = ""
            if imp.get("is_from"):
                module = imp.get("module", "")
                target = files_by_stem.get(module.split(".")[0])
                symbol = imp["name"]
            else:
                top = imp["name"].split(".")[0]
                target = files_by_stem.get(top)
                symbol = imp["name"]

            if target and target != path:
                edge = {
                    "source_file": str(path),
                    "target_file": str(target),
                    "symbol": symbol,
                    "line": imp.get("line"),
                }
                graph.edges.append(edge)
                graph.reverse_edges.setdefault(str(target), []).append(edge)

    return graph
