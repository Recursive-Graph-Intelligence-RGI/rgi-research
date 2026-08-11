from rgi.core.models import (
    CognitiveEdge, CognitiveGraph, CognitiveNode, GraphPolicy, GraphState,
    LoopType, NodeType,
)
from rgi.memory.activation import (
    ActivationEngine, extract_symbols, symbol_seed_scores,
)


def _graph():
    g = CognitiveGraph(
        loop_type=LoopType.KNOWLEDGE,
        state=GraphState(objective="x"),
        policy=GraphPolicy(),
    )
    a = CognitiveNode(type=NodeType.MEMORY, content="JWTManager handles authentication security tokens",
                      parent_graph_id=g.id)
    b = CognitiveNode(type=NodeType.MEMORY, content="SessionStore keeps session data",
                      parent_graph_id=g.id)
    c = CognitiveNode(type=NodeType.MEMORY, content="PaymentGateway processes payments",
                      parent_graph_id=g.id)
    for n in (a, b, c):
        g.nodes[n.id] = n
    g.edges.append(CognitiveEdge(source=a.id, target=b.id, edge_type="dependency"))
    return g, a, b, c


def test_keyword_seeding_and_threshold():
    g, a, b, c = _graph()
    scores = ActivationEngine().propagate(g, "authentication security")
    assert scores[a.id] > 0.5          # directly relevant
    assert scores[c.id] < 0.5          # unrelated stays dark
    assert scores[a.id] > scores[c.id]


def test_one_hop_propagation():
    g, a, b, c = _graph()
    scores = ActivationEngine().propagate(g, "authentication tokens")
    assert scores[b.id] > 0.0          # lit up via edge from a
    assert scores[b.id] < scores[a.id] or scores[b.id] <= 1.0


def test_history_bonus():
    g, a, b, c = _graph()
    c.history.append({"correction_success": True})
    scores = ActivationEngine().propagate(g, "unrelated query")
    assert scores[c.id] == 0.1


# ── Symbol-aware activation (Phase 3 substrate) ────────────────────────────────

def _symbol_graph():
    g = CognitiveGraph(
        loop_type=LoopType.KNOWLEDGE,
        state=GraphState(objective="world model"),
        policy=GraphPolicy(auto_spawn=False, require_verification=False),
    )
    auth_mod = CognitiveNode(type=NodeType.MEMORY, content="Module auth",
                             parent_graph_id=g.id, metadata={"name": "auth", "entity_kind": "module"})
    verify = CognitiveNode(type=NodeType.MEMORY, content="Function verify_token",
                           parent_graph_id=g.id, metadata={"name": "verify_token", "entity_kind": "function"})
    session_mod = CognitiveNode(type=NodeType.MEMORY, content="Module session",
                                parent_graph_id=g.id, metadata={"name": "session", "entity_kind": "module"})
    store = CognitiveNode(type=NodeType.MEMORY, content="Class SessionStore",
                          parent_graph_id=g.id, metadata={"name": "SessionStore", "entity_kind": "class"})
    for n in (auth_mod, verify, session_mod, store):
        g.nodes[n.id] = n
    g.edges.append(CognitiveEdge(source=auth_mod.id, target=verify.id, edge_type="contains"))
    g.edges.append(CognitiveEdge(source=session_mod.id, target=store.id, edge_type="contains"))
    return g, verify, store


def test_extract_symbols_dotted_and_bare():
    syms = extract_symbols("Check jwt.decode and follow_symlinks in verify_token")
    assert "jwt.decode" in syms
    assert "follow_symlinks" in syms
    assert "verify_token" in syms
    assert "check" not in syms  # prose word, not a symbol


def test_symbol_seed_scores_matches_node_name():
    g, verify, _ = _symbol_graph()
    seeds = symbol_seed_scores(g, {"verify_token"})
    assert verify.id in seeds, "node named verify_token should be seeded"


def test_symbol_seed_scores_matches_edge_symbol():
    g, verify, _ = _symbol_graph()
    g.edges.append(CognitiveEdge(
        source=verify.id, target=verify.id, edge_type="flow",
        metadata={"symbol": "jwt.decode"},
    ))
    seeds = symbol_seed_scores(g, {"jwt.decode"})
    assert verify.id in seeds, "edge symbol jwt.decode should seed its endpoint"


def test_symbol_activation_dominates_keyword():
    g, verify, _ = _symbol_graph()
    scores = ActivationEngine().propagate(g, "Investigate verify_token handling")
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    assert top, "expected activation"
    assert g.nodes[top[0][0]].metadata["name"] == "verify_token", \
        f"symbol target should top the ranking, got {g.nodes[top[0][0]].metadata['name']}"


def test_symbol_seed_scores_empty_without_symbols():
    g, _, _ = _symbol_graph()
    assert symbol_seed_scores(g, set()) == {}
