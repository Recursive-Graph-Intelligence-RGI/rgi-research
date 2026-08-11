"""Grounded exploration primitives ported from rlmlocal's gate/tool patterns.

These tools give the recursive engine direct, read-only access to the
filesystem and the import graph, mirroring the rlmlocal REPL style without
introducing any UI or Cloudflare dependencies.
"""
import re
from pathlib import Path


def read_file(params: dict) -> dict:
    """Return the contents of a file, optionally bounded by line numbers."""
    path = Path(params["path"])
    line_start = params.get("line_start")
    line_end = params.get("line_end")
    lines = path.read_text().splitlines()
    if line_start is not None and line_end is not None:
        snippet = "\n".join(lines[line_start - 1 : line_end])
    else:
        snippet = path.read_text()
    return {"findings": [{"file": str(path), "content": snippet}], "confidence": 1.0}


def grep(params: dict) -> dict:
    """Search files under ``root`` matching ``glob`` for ``pattern``."""
    pattern = re.compile(params["pattern"])
    root = Path(params["root"])
    glob = params.get("glob", "*.py")
    findings = []
    for path in root.rglob(glob):
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                findings.append({"file": str(path), "line": i, "content": line})
    return {"findings": findings, "confidence": 1.0}


def callers(params: dict) -> dict:
    """Return import-graph edges that mention ``symbol``."""
    symbol = params["symbol"]
    edges = params.get("import_graph_edges", [])
    results = [e for e in edges if e.get("symbol") == symbol]
    return {"findings": results, "confidence": 0.9}
