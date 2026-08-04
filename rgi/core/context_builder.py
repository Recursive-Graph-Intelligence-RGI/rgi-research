"""Builds targeted LLM context. The LLM never sees the whole system —
activation already decided what is relevant; this just serializes it."""
from rgi.core.models import CognitiveGraph, CognitiveNode, NodeState


class ContextBuilder:
    MAX_CHARS = 16000  # ~4000 tokens

    def build(self, node: CognitiveNode, graph: CognitiveGraph) -> str:
        parts = [
            f"OBJECTIVE: {graph.state.objective}",
            f"TASK: {node.content}",
        ]

        neighbors = [
            n for n in graph.nodes.values()
            if n.id != node.id and n.activation > 0.3
        ]
        neighbors.sort(key=lambda n: n.activation, reverse=True)
        if neighbors:
            parts.append("NEIGHBORS:")
            for n in neighbors[:5]:
                summary = n.result if isinstance(n.result, dict) else n.content[:200]
                parts.append(f"- [{n.type.value}] {summary}")

        if graph.memory_snapshot:
            parts.append("MEMORY:")
            for key, value in list(graph.memory_snapshot.items())[:5]:
                parts.append(f"- {key}: {value}")

        parts.append(
            f"POLICY: max_nodes={graph.policy.max_nodes}, "
            f"require_verification={graph.policy.require_verification}"
        )

        if node.history and any(
            h.get("state") in (NodeState.FAILED.value, NodeState.CORRECTING.value)
            or h.get("reason")
            for h in node.history
        ):
            parts.append(f"HISTORY: {node.history[-3:]}")

        return "\n".join(parts)[: self.MAX_CHARS]
