"""Perception: converts raw code into a structured world-model KNOWLEDGE graph.
Confidence: 1.0 for parsed syntax, 0.7 for inferred relationships."""
import ast
from pathlib import Path

from rgi.core.models import (
    CognitiveEdge, CognitiveGraph, CognitiveNode, GraphPolicy, GraphState,
    LoopType, NodeType,
)


class PerceptionLayer:
    async def ingest_codebase(self, path: str) -> CognitiveGraph:
        root = Path(path)
        graph = CognitiveGraph(
            loop_type=LoopType.KNOWLEDGE,
            state=GraphState(objective=f"World model for {root}"),
            policy=GraphPolicy(auto_spawn=False, require_verification=False),
        )
        module_nodes: dict[str, str] = {}  # module name -> node id

        for py_file in sorted(p for p in root.rglob("*.py") if p.is_file()):
            try:
                tree = ast.parse(py_file.read_text())
            except SyntaxError:
                continue
            module = py_file.stem

            mod_node = CognitiveNode(
                type=NodeType.MEMORY,
                content=f"Module {module} in {py_file.name}",
                confidence=1.0,
                parent_graph_id=graph.id,
                metadata={"file": str(py_file), "name": module, "entity_kind": "module"},
            )
            graph.nodes[mod_node.id] = mod_node
            module_nodes[module] = mod_node.id

            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)

            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    self._add_entity(graph, py_file, "Class", node.name,
                                     f"methods: {[m.name for m in node.body if isinstance(m, ast.FunctionDef)]}")
                    for m in node.body:
                        if isinstance(m, ast.FunctionDef):
                            self._add_entity(graph, py_file, "Function", m.name,
                                             f"method of {node.name}")
                elif isinstance(node, ast.FunctionDef):
                    self._add_entity(graph, py_file, "Function", node.name, "")

            mod_node.metadata["imports"] = imports

        # Inferred dependency edges between local modules (confidence 0.7)
        for py_file in sorted(p for p in root.rglob("*.py") if p.is_file()):
            module = py_file.stem
            src_id = module_nodes.get(module)
            if src_id is None:
                continue
            for imp in graph.nodes[src_id].metadata.get("imports", []):
                top = imp.split(".")[0]
                if top in module_nodes and top != module:
                    graph.edges.append(CognitiveEdge(
                        source=src_id, target=module_nodes[top],
                        edge_type="dependency", weight=0.7,
                        metadata={"confidence": 0.7, "kind": "imports"},
                    ))
        return graph

    def _add_entity(self, graph, py_file, kind, name, summary):
        node = CognitiveNode(
            type=NodeType.MEMORY,
            content=f"{kind} {name} in {py_file.name}: {summary}".rstrip(": "),
            confidence=1.0,
            parent_graph_id=graph.id,
            metadata={"file": str(py_file), "name": name, "entity_kind": kind.lower()},
        )
        graph.nodes[node.id] = node
        return node
