import math
from rgi.reasoning.embeddings import HashEmbeddings, cosine
from rgi.memory.activation import EmbeddingActivationEngine
from rgi.core.models import (
    CognitiveEdge, CognitiveGraph, CognitiveNode, GraphPolicy, GraphState,
    LoopType, NodeType,
)


async def test_hash_embeddings_deterministic_and_distinct():
    emb = HashEmbeddings()
    a1 = await emb.embed(["jwt token authentication"])
    a2 = await emb.embed(["jwt token authentication"])
    b = await emb.embed(["payment gateway processing"])
    assert a1 == a2                      # deterministic
    assert len(a1[0]) == 64
    assert abs(math.sqrt(sum(x * x for x in a1[0])) - 1.0) < 1e-6  # normalized
    assert cosine(a1[0], b[0]) < cosine(a1[0], a2[0])              # distinct


def test_cosine_bounds():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([1.0, 0.0], [-1.0, 0.0]) == -1.0
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def _graph():
    g = CognitiveGraph(loop_type=LoopType.KNOWLEDGE,
                       state=GraphState(objective="x"), policy=GraphPolicy())
    a = CognitiveNode(type=NodeType.MEMORY, content="JWTManager handles authentication tokens",
                      parent_graph_id=g.id)
    b = CognitiveNode(type=NodeType.MEMORY, content="SessionStore keeps session data",
                      parent_graph_id=g.id)
    c = CognitiveNode(type=NodeType.MEMORY, content="PaymentGateway processes payments",
                      parent_graph_id=g.id)
    for n in (a, b, c):
        g.nodes[n.id] = n
    g.edges.append(CognitiveEdge(source=a.id, target=b.id, edge_type="dependency"))
    g.edges.append(CognitiveEdge(source=b.id, target=c.id, edge_type="dependency"))
    return g, a, b, c


async def test_embedding_activation_seeds_and_spreads_multihop():
    g, a, b, c = _graph()
    engine = EmbeddingActivationEngine(HashEmbeddings())
    scores = await engine.a_propagate(g, "authentication security")
    assert scores[a.id] > scores[c.id]       # relevant beats unrelated
    assert scores[b.id] > 0.0                # one hop from a
    # c is seeded low but receives two-hop spread if b lights up
    assert 0.0 <= scores[c.id] <= 1.0


async def test_embedding_activation_caches_node_embeddings():
    g, a, b, c = _graph()
    provider = HashEmbeddings()
    engine = EmbeddingActivationEngine(provider)
    await engine.a_propagate(g, "authentication")
    assert len(engine.cache) == 3            # one entry per node
    await engine.a_propagate(g, "sessions")
    assert len(engine.cache) == 3            # reused, not recomputed


async def test_keyword_engine_has_async_wrapper():
    from rgi.memory.activation import ActivationEngine
    g, a, b, c = _graph()
    scores = await ActivationEngine().a_propagate(g, "authentication security")
    assert scores[a.id] > 0.5                # keyword path unchanged


from rgi.memory.activation import EmbeddingActivationEngine as _RealEmbeddingEngine


class _LowThresholdEngine:
    """Test stub: hash embeddings score low; force threshold 0.2."""

    def __init__(self, provider, **_ignored):
        self._inner = _RealEmbeddingEngine(provider, threshold=0.2)
        self.threshold = self._inner.threshold

    async def a_propagate(self, graph, query):
        return await self._inner.a_propagate(graph, query)


async def test_embed_live_path_audit_llm_mode_is_string(tmp_path, monkeypatch):
    """Regression: the embeddings provider local must not shadow the provider
    string — a live embed run crashed serializing llm_mode (Run 5 attempt 1)."""
    import rgi.cli as cli
    from rgi.reasoning import embeddings as emb_mod
    from rgi.reasoning.llm_client import MockLLMClient

    monkeypatch.setattr(emb_mod, "OpenAICompatibleEmbeddings",
                        lambda *a, **kw: emb_mod.HashEmbeddings())
    # Hash embeddings score low (~0.27); a real provider scores higher.
    # Inject a low-threshold engine to keep the offline test behavior parity.
    import rgi.memory.activation as act_mod
    monkeypatch.setattr(act_mod, "EmbeddingActivationEngine", _LowThresholdEngine)
    monkeypatch.setattr(cli, "LLMClient", lambda model=None: MockLLMClient())
    monkeypatch.setenv("RGI_LLM_API_KEY", "dummy")

    report = await cli.run_analysis(
        "sample_project", "Analyze authentication security",
        str(tmp_path / "r.json"), False, "kimi", None, 20, embed=True)
    assert report["status"] == "completed"
    started = [e for e in report["execution_log"] if e["event"] == "run_started"]
    assert started
    assert all(isinstance(e["llm_mode"], str) for e in started)
