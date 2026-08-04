"""Activation engine: attention, not retrieval. Seeds relevant nodes by
keyword overlap, propagates one hop with decay, rewards nodes that were
part of past successful corrections. v0.2 swaps internals only."""
import re

from rgi.core.models import CognitiveGraph

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")

# Vocabulary bridge: objective language -> code language (see status report §4.1).
# v0.2 candidate 1; embeddings (candidate 4) replace this with real association.
SEED_ALIASES: dict[str, set[str]] = {
    "authentication": {"auth", "login", "jwt", "token", "session", "password", "credential"},
    "security": {"secret", "password", "vulnerability", "injection", "config", "key"},
    "authorization": {"auth", "permission", "access", "role"},
}


class ActivationEngine:
    DECAY = 0.8
    HISTORY_BONUS = 0.1

    def propagate(self, graph: CognitiveGraph, query: str) -> dict[str, float]:
        original_keywords = {w.lower() for w in _WORD_RE.findall(query)}
        keywords = original_keywords | {alias for k in original_keywords
                                        for alias in SEED_ALIASES.get(k, set())}
        scores: dict[str, float] = {}

        # 1. Seed: keyword overlap between query and node content
        for nid, node in graph.nodes.items():
            text = node.content.lower()
            hits = sum(1 for k in keywords if k in text)
            base = hits / len(original_keywords) if original_keywords else 0.0
            scores[nid] = min(1.0, base + 0.3) if hits else 0.0

        # 2. One-hop propagation: child gets parent_score * weight * decay
        for edge in graph.edges:
            propagated = scores.get(edge.source, 0.0) * edge.weight * self.DECAY
            if propagated > scores.get(edge.target, 0.0):
                scores[edge.target] = min(1.0, propagated)

        # 3. History bonus for nodes in past successful corrections
        for nid, node in graph.nodes.items():
            if any(h.get("correction_success") for h in node.history):
                scores[nid] = min(1.0, scores.get(nid, 0.0) + self.HISTORY_BONUS)

        return scores
