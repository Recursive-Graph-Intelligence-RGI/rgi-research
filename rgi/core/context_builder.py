"""Builds targeted LLM context. The LLM never sees the whole system —
activation already decided what is relevant; this just serializes it.

Post-Run 9: source code gets its own budget. Reasoning nodes starved
when tool-returned source competed with neighbor chatter for the same
16k chars — the LLM vibed from fragments instead of reading the code."""
from rgi.core.models import CognitiveGraph, CognitiveNode, NodeState


class ContextBuilder:
    MAX_CHARS = 16000  # ~4000 tokens of chatter (neighbors, memory, policy)
    SOURCE_MAX_CHARS = 32000  # ~8000 tokens of actual source code

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

        # Pull source excerpts OUT of tool results into a dedicated section
        # with its own budget; neighbors keep everything else.
        source_sections = []
        if neighbors:
            parts.append("NEIGHBORS:")
            for n in neighbors[:5]:
                summary = n.result if isinstance(n.result, dict) else n.content[:200]
                summary, sources = self._split_source(summary)
                source_sections.extend(sources)
                parts.append(f"- [{n.type.value}] {summary}")

        if source_sections:
            source = "\n\n".join(source_sections)[: self.SOURCE_MAX_CHARS]
            parts.append(f"SOURCE CODE (read this; do not speculate):\n{source}")

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

        return "\n".join(parts)[: self.MAX_CHARS + self.SOURCE_MAX_CHARS]

    @staticmethod
    def _split_source(summary):
        """Extract source_excerpt fields from a tool-result dict.
        Returns (summary_without_source, [source_sections])."""
        if not isinstance(summary, dict):
            return summary, []
        findings = summary.get("findings")
        if not isinstance(findings, list):
            return summary, []
        sources = [f["source_excerpt"] for f in findings
                   if isinstance(f, dict) and f.get("source_excerpt")]
        if not sources:
            return summary, []
        trimmed = dict(summary)
        trimmed["findings"] = [
            {k: v for k, v in f.items() if k != "source_excerpt"}
            if isinstance(f, dict) else f
            for f in findings
        ]
        return trimmed, sources
