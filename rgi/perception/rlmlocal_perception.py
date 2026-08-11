"""RGI perception layer backed by rlmlocal-style structural extraction.

This layer replaces/augments the AST-only `PerceptionLayer` in
`rgi/perception/code_parser.py` with a richer substrate: functions, classes,
methods, imports, and call edges extracted via tree-sitter.
"""
from pathlib import Path

from rgi.core.models import (
    CognitiveEdge,
    CognitiveGraph,
    CognitiveNode,
    GraphPolicy,
    GraphState,
    LoopType,
    NodeType,
)
from rgi.perception.rlmlocal_compat.import_graph import build_import_graph
from rgi.perception.rlmlocal_compat.structure_extractor import extract_structure


class RlmlocalPerceptionLayer:
    """Build a CognitiveGraph from a codebase using rlmlocal-compatible extraction."""

    async def ingest_codebase(self, path: str) -> CognitiveGraph:
        root = Path(path)
        graph = CognitiveGraph(
            loop_type=LoopType.KNOWLEDGE,
            state=GraphState(objective=f"World model for {root}"),
            policy=GraphPolicy(auto_spawn=False, require_verification=False),
        )

        py_files = sorted(p for p in root.rglob("*.py") if p.is_file())
        structs = {p: extract_structure(p) for p in py_files}
        import_graph = build_import_graph(root, structs)

        file_to_node: dict[Path, str] = {}
        for py_file in py_files:
            node = CognitiveNode(
                type=NodeType.MEMORY,
                content=f"Module {py_file.stem} in {py_file.name}",
                confidence=1.0,
                parent_graph_id=graph.id,
                metadata={
                    "file": str(py_file),
                    "name": py_file.stem,
                    "entity_kind": "module",
                },
            )
            graph.nodes[node.id] = node
            file_to_node[py_file] = node.id

        for py_file, struct in structs.items():
            module_node_id = file_to_node[py_file]

            for fn in struct.functions:
                node = CognitiveNode(
                    type=NodeType.MEMORY,
                    content=f"Function {fn['name']} in {py_file.name}",
                    confidence=1.0,
                    parent_graph_id=graph.id,
                    metadata={
                        "file": str(py_file),
                        "name": fn["name"],
                        "entity_kind": "function",
                        "line": fn.get("line"),
                    },
                )
                graph.nodes[node.id] = node
                graph.edges.append(
                    CognitiveEdge(
                        source=module_node_id,
                        target=node.id,
                        edge_type="contains",
                        weight=1.0,
                    )
                )

            for cls in struct.classes:
                node = CognitiveNode(
                    type=NodeType.MEMORY,
                    content=f"Class {cls['name']} in {py_file.name}",
                    confidence=1.0,
                    parent_graph_id=graph.id,
                    metadata={
                        "file": str(py_file),
                        "name": cls["name"],
                        "entity_kind": "class",
                        "line": cls.get("line"),
                    },
                )
                graph.nodes[node.id] = node
                graph.edges.append(
                    CognitiveEdge(
                        source=module_node_id,
                        target=node.id,
                        edge_type="contains",
                        weight=1.0,
                    )
                )

        for edge in import_graph.edges:
            src = Path(edge["source_file"])
            tgt = Path(edge["target_file"])
            if src in file_to_node and tgt in file_to_node:
                graph.edges.append(
                    CognitiveEdge(
                        source=file_to_node[src],
                        target=file_to_node[tgt],
                        edge_type="imports",
                        weight=0.9,
                        metadata={"symbol": edge.get("symbol"), "line": edge.get("line")},
                    )
                )

        return graph
