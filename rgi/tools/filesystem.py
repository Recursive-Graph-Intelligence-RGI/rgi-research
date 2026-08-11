"""Generic filesystem tools for REPL and subgraph navigation.

These tools only read; they do not write. Write tools (write_file, edit_file,
verify_patch, apply_patch) live elsewhere and carry stronger governance gates.
"""
from pathlib import Path


def list_dir(params: dict) -> dict:
    """List files and directories under a path."""
    root = Path(params["path"])
    if not root.exists():
        return {"error": f"not found: {root}", "entries": []}
    if not root.is_dir():
        return {"error": f"not a directory: {root}", "entries": []}
    entries = []
    for child in sorted(root.iterdir()):
        entries.append({
            "name": child.name,
            "kind": "dir" if child.is_dir() else "file",
            "path": str(child),
        })
    return {"entries": entries}


def find_files(params: dict) -> dict:
    """Recursively find files matching a glob pattern."""
    root = Path(params["root"])
    if not root.exists():
        return {"error": f"not found: {root}", "files": []}
    if not root.is_dir():
        return {"error": f"not a directory: {root}", "files": []}
    pattern = params.get("pattern", "*")
    results = [str(p) for p in root.rglob(pattern) if p.is_file()]
    return {"files": sorted(results)}


def stat_file(params: dict) -> dict:
    """Return metadata for a file or directory."""
    p = Path(params["path"])
    if not p.exists():
        return {"exists": False, "error": f"not found: {p}"}
    s = p.stat()
    return {
        "path": str(p),
        "exists": True,
        "size": s.st_size,
        "is_dir": p.is_dir(),
        "is_file": p.is_file(),
        "mtime": s.st_mtime,
    }
