"""Activation engine: attention, not retrieval. Seeds relevant nodes by
keyword overlap, propagates one hop with decay, rewards nodes that were
part of past successful corrections. v0.2 swaps internals only."""
import os
import re

from rgi.core.models import CognitiveGraph

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")

# Symbol extraction: dotted names (jwt.decode, utils.follow_symlinks),
# snake_case, camelCase, and bare identifiers that could be a function/class.
_DOTTED_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*")
_IDENT_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

# Vocabulary bridge: objective language -> code language (see status report §4.1).
# v0.2 candidate 1; embeddings (candidate 4) replace this with real association.
SEED_ALIASES: dict[str, set[str]] = {
    "authentication": {"auth", "login", "jwt", "token", "session", "password", "credential"},
    "security": {"secret", "password", "vulnerability", "injection", "config", "key"},
    "authorization": {"auth", "permission", "access", "role"},
}


def extract_symbols(query: str) -> set[str]:
    """Candidate symbol names from the objective.

    Dotted names first (``jwt.decode``), then bare identifiers that look like
    code (snake_case / camelCase / short tokens). Pure prose words like
    ``security`` are excluded — they are keyword territory, not symbols.
    """
    symbols: set[str] = set()
    for m in _DOTTED_RE.finditer(query):
        symbols.add(m.group(0))
    for m in _IDENT_RE.finditer(query):
        tok = m.group(0)
        if "_" in tok or (tok[:1].isupper() and len(tok) > 1):
            symbols.add(tok)
        elif len(tok) >= 4 and tok not in SEED_ALIASES:
            # bare lowercase identifier that isn't a stopword alias — could be
            # a function/module name (e.g. 'verify_token', 'session_store')
            symbols.add(tok)
    return symbols


def symbol_seed_scores(graph: CognitiveGraph, symbols: set[str]) -> dict[str, float]:
    """Seed activation from graph symbols: nodes whose name matches a symbol,
    and both endpoints of edges whose symbol matches. Returns {node_id: score}.
    """
    if not symbols:
        return {}
    seeds: dict[str, float] = {}
    # 1. Node metadata names (functions, classes, modules, methods).
    for nid, node in graph.nodes.items():
        name = str(node.metadata.get("name") or "").strip()
        if name and name in symbols:
            seeds[nid] = max(seeds.get(nid, 0.0), 1.0)
    # 2. Edge symbols (imports/calls carry the symbol that crosses files).
    for edge in graph.edges:
        sym = str(edge.metadata.get("symbol") or "").strip()
        if not sym:
            continue
        # Exact match, or dotted-symbol head/tail match (jwt.decode vs decode).
        hit = sym in symbols or any(
            s in sym or sym in s for s in symbols
        )
        if hit:
            seeds[edge.source] = max(seeds.get(edge.source, 0.0), 0.9)
            seeds[edge.target] = max(seeds.get(edge.target, 0.0), 0.9)
    return seeds


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

        # 1b. Symbol-aware seed: objective names a symbol (jwt.decode,
        # follow_symlinks) -> activate the nodes/edges that carry it.
        symbol_seeds = symbol_seed_scores(graph, extract_symbols(query))
        for nid, s in symbol_seeds.items():
            scores[nid] = max(scores.get(nid, 0.0), s)

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
        # Symbol-aware seed: objective names a symbol -> activate the graph
        # entities that carry it (node names + edge symbols), max-merged so a
        # direct symbol hit outranks a fuzzy cosine.
        for nid, s in symbol_seed_scores(graph, extract_symbols(query)).items():
            scores[nid] = max(scores.get(nid, 0.0), s)
        for _ in range(self.SPREAD_ITERATIONS):
            for edge in graph.edges:
                spread = scores.get(edge.source, 0.0) * edge.weight * self.DECAY
                if spread > scores.get(edge.target, 0.0):
                    scores[edge.target] = min(1.0, spread)
        for nid, node in graph.nodes.items():
            if any(h.get("correction_success") for h in node.history):
                scores[nid] = min(1.0, scores.get(nid, 0.0) + self.HISTORY_BONUS)
        return _top_k(scores, len(nodes), self.TOP_K_SCALE, self.TOP_K_MIN)
