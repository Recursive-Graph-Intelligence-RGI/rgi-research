"""Activation engine: attention, not retrieval. Seeds relevant nodes by
keyword overlap, propagates one hop with decay, rewards nodes that were
part of past successful corrections. v0.2 swaps internals only."""
import os
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


def _top_k(scores: dict[str, float], n_nodes: int, scale: float = 2.0,
           min_k: int = 10) -> dict[str, float]:
    """Scale attention with graph size: large codebases must not activate
    every node every iteration. K grows sub-linearly (sqrt) so coverage
    increases while per-iteration work stays bounded."""
    if n_nodes <= min_k:
        return scores
    k = max(min_k, int(n_nodes ** 0.5 * scale))
    threshold_score = sorted(scores.values(), reverse=True)[k - 1]
    return {nid: s for nid, s in scores.items() if s >= threshold_score}


class ActivationEngine:
    DECAY = 0.8
    threshold = 0.5
    HISTORY_BONUS = 0.1
    TOP_K_SCALE = float(os.environ.get("RGI_ACTIVATION_TOP_K_SCALE", "2.0"))
    TOP_K_MIN = int(os.environ.get("RGI_ACTIVATION_TOP_K_MIN", "10"))

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

        return _top_k(scores, len(graph.nodes), self.TOP_K_SCALE, self.TOP_K_MIN)

    async def a_propagate(self, graph: CognitiveGraph, query: str) -> dict[str, float]:
        """Async seam: embedding engines implement natively; keyword engine wraps."""
        return self.propagate(graph, query)


class EmbeddingActivationEngine:
    """v0.2: embedding-seeded spreading activation. Seed = cosine relevance;
    spread = multi-hop decay. Falls back to nothing keyword-ish — the seed IS
    the association (status report §4.1, candidate 4)."""

    DECAY = 0.8
    SPREAD_ITERATIONS = 3
    HISTORY_BONUS = 0.1
    TOP_K_SCALE = float(os.environ.get("RGI_ACTIVATION_TOP_K_SCALE", "2.0"))
    TOP_K_MIN = int(os.environ.get("RGI_ACTIVATION_TOP_K_MIN", "10"))

    def __init__(self, provider, cache: dict | None = None, threshold: float = 0.5):
        self.provider = provider
        self.cache: dict[int, list[float]] = cache if cache is not None else {}
        self.threshold = threshold

    async def a_propagate(self, graph: CognitiveGraph, query: str) -> dict[str, float]:
        from rgi.reasoning.embeddings import cosine

        nodes = list(graph.nodes.values())
        missing = [n for n in nodes if hash(n.content) not in self.cache]
        if missing:
            vectors = await self.provider.embed([n.content for n in missing])
            for node, vec in zip(missing, vectors):
                self.cache[hash(node.content)] = vec
        query_vec = (await self.provider.embed([query]))[0]

        scores = {
            n.id: max(0.0, cosine(query_vec, self.cache[hash(n.content)]))
            for n in nodes
        }
        for _ in range(self.SPREAD_ITERATIONS):
            for edge in graph.edges:
                spread = scores.get(edge.source, 0.0) * edge.weight * self.DECAY
                if spread > scores.get(edge.target, 0.0):
                    scores[edge.target] = min(1.0, spread)
        for nid, node in graph.nodes.items():
            if any(h.get("correction_success") for h in node.history):
                scores[nid] = min(1.0, scores.get(nid, 0.0) + self.HISTORY_BONUS)
        return _top_k(scores, len(nodes), self.TOP_K_SCALE, self.TOP_K_MIN)
