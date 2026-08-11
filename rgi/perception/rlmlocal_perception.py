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
from rgi.perception.rlmlocal_compat.call_graph import build_call_graph
from rgi.perception.rlmlocal_compat.import_graph import build_import_graph, source_files
from rgi.perception.rlmlocal_compat.language_packs import lang_family
from rgi.perception.rlmlocal_compat.reference_graph import build_reference_graph
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

        src_files = source_files(root)
        structs = {p: extract_structure(p) for p in src_files}
        import_graph = build_import_graph(root, structs)
        call_graph = build_call_graph(root, structs, import_graph.symbol_defs)
        reference_graph = build_reference_graph(root, structs)

        file_to_node: dict[Path, str] = {}
        for src_file in src_files:
            node = CognitiveNode(
                type=NodeType.MEMORY,
                content=f"Module {src_file.stem} in {src_file.name}",
                confidence=1.0,
                parent_graph_id=graph.id,
                metadata={
                    "file": str(src_file),
                    "name": src_file.stem,
                    "entity_kind": "module",
                    "language": lang_family(src_file.suffix) or "unknown",
                },
            )
            graph.nodes[node.id] = node
            file_to_node[src_file] = node.id

        for src_file, struct in structs.items():
            module_node_id = file_to_node[src_file]
            language = lang_family(src_file.suffix) or "unknown"

            for fn in struct.functions:
                node = CognitiveNode(
                    type=NodeType.MEMORY,
                    content=f"Function {fn['name']} in {src_file.name}",
                    confidence=1.0,
                    parent_graph_id=graph.id,
                    metadata={
                        "file": str(src_file),
                        "name": fn["name"],
                        "entity_kind": "function",
                        "line": fn.get("line"),
                        "language": language,
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
                    content=f"Class {cls['name']} in {src_file.name}",
                    confidence=1.0,
                    parent_graph_id=graph.id,
                    metadata={
                        "file": str(src_file),
                        "name": cls["name"],
                        "entity_kind": "class",
                        "line": cls.get("line"),
                        "language": language,
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

        # Call edges: file A calls a symbol defined unambiguously in file B.
        for edge in call_graph.edges:
            src = Path(edge["source_file"])
            tgt = Path(edge["target_file"])
            if src in file_to_node and tgt in file_to_node:
                graph.edges.append(
                    CognitiveEdge(
                        source=file_to_node[src],
                        target=file_to_node[tgt],
                        edge_type="flow",
                        weight=0.85,
                        metadata={"symbol": edge.get("symbol"), "line": edge.get("line")},
                    )
                )

        # Reference edges: a client call literal resolves to a registered route.
        for edge in reference_graph.edges:
            src = Path(edge["source_file"])
            tgt = Path(edge["target_file"])
            if src in file_to_node and tgt in file_to_node:
                graph.edges.append(
                    CognitiveEdge(
                        source=file_to_node[src],
                        target=file_to_node[tgt],
                        edge_type="dependency",
                        weight=0.8,
                        metadata={"url": edge.get("url"), "line": edge.get("line")},
                    )
                )

        return graph
