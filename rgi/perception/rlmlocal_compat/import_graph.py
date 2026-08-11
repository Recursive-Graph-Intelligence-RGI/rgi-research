"""Port of rlmlocal's importGraph.ts core edge builder.

Builds import/call edges between files from per-file CodeStructure extractions.
This is a conservative, deterministic builder: an edge is only created when the
target module/symbol can be resolved unambiguously within the analyzed root.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rgi.perception.rlmlocal_compat.language_packs import supported_extensions
from rgi.perception.rlmlocal_compat.structure_extractor import CodeStructure


@dataclass
class ImportGraph:
    edges: list[dict] = field(default_factory=list)
    reverse_edges: dict[str, list[dict]] = field(default_factory=dict)
    symbol_defs: dict[str, list[dict]] = field(default_factory=dict)


def source_files(root: Path) -> list[Path]:
    """All supported-language source files under root, sorted.

    Multi-language: walks every extension the language packs advertise
    (py, js/jsx/mjs/cjs, ts/mts/cts, tsx, go, rs) so the world model is not
    Python-only. Build/vendor directories (node_modules, target, dist, .git,
    __pycache__, venvs) are skipped so compiled artifacts and dependencies do
    not pollute the graph.
    """
    exts = supported_extensions()
    skip_dirs = {
        "node_modules", "target", "dist", "build", ".git", ".hg", ".svn",
        "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
        ".next", ".nuxt", ".gradle", ".idea", ".vscode",
    }
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in exts
        and not any(part in skip_dirs for part in p.relative_to(root).parts[:-1])
    )


def _resolve_import_target(importing: Path, module: str, files_by_relpath: dict[str, Path]) -> Path | None:
    """Resolve a JS/TS-style relative import ('./b', '../utils/x') to a file.

    Strips the leading ./ or ../, tries each supported extension, and matches
    against the importing file's directory. Bare specifiers ('react', 'lodash')
    and non-relative imports resolve to None (external / not in root).
    """
    if not (module.startswith("./") or module.startswith("../")):
        return None
    rel = Path(module)
    # Index files under the importing dir by their path relative to it.
    base = importing.parent
    candidates = []
    if not rel.is_absolute() and not any(p == ".." for p in rel.parts[:-1]):
        pass  # still try below
    for suffix in supported_extensions():
        cand = (base / rel).with_suffix(suffix)
        if cand.is_file():
            candidates.append(cand.resolve())
    if len(candidates) == 1:
        return candidates[0]
    # Directory import: './b' may mean './b/index.js'
    if not candidates:
        for suffix in supported_extensions():
            cand = base / rel / f"index{suffix}"
            if cand.is_file():
                candidates.append(cand.resolve())
        if len(candidates) == 1:
            return candidates[0]
    return None


def build_import_graph(root: Path, structs: dict[Path, CodeStructure]) -> ImportGraph:
    """Build an import graph across all supported languages.

    Args:
        root: The project root (used for relative path reporting).
        structs: Mapping from file Path to extracted CodeStructure.

    Returns:
        ImportGraph with resolved import edges and symbol definition index.
    """
    graph = ImportGraph()

    # Index files by stem (Python: 'import b' -> b.py; Rust: 'crate::b' -> b.rs)
    files_by_stem: dict[str, Path] = {}
    for path in structs.keys():
        files_by_stem.setdefault(path.stem, path)

    # Index files by relative path for JS/TS './x' resolution.
    files_by_relpath: dict[str, Path] = {}
    for path in structs.keys():
        try:
            rel = path.relative_to(root)
            files_by_relpath[rel.as_posix()] = path
        except ValueError:
            pass

    # Index symbol definitions (all languages).
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

    # Build import edges.
    for path, struct in structs.items():
        for imp in struct.imports:
            target: Path | None = None
            symbol: str = ""
            is_from = imp.get("is_from", False)
            module = imp.get("module", "") or ""

            if is_from:
                # Python: from b import helper — module 'b'
                # JS/TS:  import { x } from './b' — module './b' or 'b'
                if module.startswith("."):
                    target = _resolve_import_target(path, module, files_by_relpath)
                else:
                    target = files_by_stem.get(module.split(".")[0])
                symbol = imp["name"]
            else:
                # Python: import b / import b.c
                # Rust:   use crate::b::x
                name = imp["name"]
                head = name
                if name.startswith("crate::"):
                    head = name.split("::")[1] if "::" in name else name
                elif "." in name:
                    head = name.split(".")[0]
                target = files_by_stem.get(head)
                symbol = name

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
