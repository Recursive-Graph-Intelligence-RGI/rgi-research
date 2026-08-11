"""Port of rlmlocal's referenceGraph edge builder (URL literal -> handler file).

Builds file-level reference edges from HTTP route handlers to client call
sites: a ``fetch("/api/x")`` / ``requests.get("/api/x")`` in one file is linked
to the file that registers ``@app.route("/api/x")`` (Flask/FastAPI-style
decorators). Like rlmlocal's original, only routes that resolve to a real
handler are promoted; unconfirmed references are dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rgi.perception.rlmlocal_compat.structure_extractor import CodeStructure

# Route decorators: @app.route("/x"), @router.get("/x"), @bp.post("/x"), ...
_ROUTE_DECORATOR_RE = re.compile(
    r"@[\w.]+\.(?:route|get|post|put|delete|patch)\s*\(\s*[\"'](?P<path>[^\"']+)[\"']"
)
# Client call sites: fetch("/x"), axios.get("/x"), requests.get("..."), urlopen
_CLIENT_CALL_RE = re.compile(
    r"(?:fetch|axios\.\w+|requests\.\w+|urlopen|httpx\.\w+|aiohttp\.\w+)"
    r"\s*\(\s*[\"'](?P<path>[^\"']+)[\"']"
)


@dataclass
class ReferenceGraph:
    edges: list[dict] = field(default_factory=list)


def _normalize(path: str) -> str:
    return path.rstrip("/")


def _route_key(path: str) -> str:
    """Turn a route with params into a prefix key: /api/items/<id> -> /api/items."""
    return _normalize(path.split("<")[0])


def _collect_routes(structs: dict[Path, CodeStructure]) -> list[dict]:
    """Collect route-decorated handlers with their source text."""
    routes: list[dict] = []
    for path, struct in structs.items():
        if not path.is_file():
            continue
        source = path.read_text(errors="replace")
        for m in _ROUTE_DECORATOR_RE.finditer(source):
            routes.append({
                "file": str(path),
                "path": m.group("path"),
                "line": source[: m.start()].count("\n") + 1,
            })
    return routes


def build_reference_graph(
    root: Path, structs: dict[Path, CodeStructure]
) -> ReferenceGraph:
    """Build conservative URL-literal reference edges.

    An edge is created when a client call literal matches a registered route:
    exact match, or a route-params prefix match (``/api/items/<id>`` matches a
    call to ``/api/items``). This mirrors rlmlocal's conservative promotion:
    only confirmed routes produce edges.

    Args:
        root: The project root (used for relative path reporting).
        structs: Mapping from file Path to extracted CodeStructure.

    Returns:
        ReferenceGraph with resolved reference edges.
    """
    routes = _collect_routes(structs)
    route_by_key: dict[str, dict] = {}
    for r in routes:
        route_by_key.setdefault(_route_key(r["path"]), r)

    graph = ReferenceGraph()
    seen: set[tuple] = set()

    for path, struct in structs.items():
        if not path.is_file():
            continue
        source = path.read_text(errors="replace")
        for m in _CLIENT_CALL_RE.finditer(source):
            literal = _normalize(m.group("path"))
            match = route_by_key.get(literal) or route_by_key.get(_route_key(literal))
            if match is None:
                continue
            target = match["file"]
            key = (str(path), target, literal)
            if key not in seen:
                seen.add(key)
                graph.edges.append({
                    "source_file": str(path),
                    "target_file": target,
                    "url": literal,
                    "line": source[: m.start()].count("\n") + 1,
                    "kind": "reference",
                    "verified": True,
                })

    return graph
