from rgi.core.models import CognitiveGraph, CognitiveNode, GraphPolicy, GraphState, LoopType, NodeType
from rgi.memory.activation import ActivationEngine


def _knowledge():
    g = CognitiveGraph(loop_type=LoopType.KNOWLEDGE, state=GraphState(objective="x"), policy=GraphPolicy())
    nodes = [
        CognitiveNode(type=NodeType.MEMORY, content="Class JWTManager in auth.py: methods: ['create_token', 'decode_token']", parent_graph_id=g.id),
        CognitiveNode(type=NodeType.MEMORY, content="Class LoginHandler in login.py: methods: ['check_password']", parent_graph_id=g.id),
        CognitiveNode(type=NodeType.MEMORY, content="Module config in config.py", parent_graph_id=g.id),
        CognitiveNode(type=NodeType.MEMORY, content="Class PaymentGateway in payments.py", parent_graph_id=g.id),
    ]
    for n in nodes:
        g.nodes[n.id] = n
    return g, [n.id for n in nodes]


def test_objective_language_activates_code_entities():
    """The Run-2 failure: 'authentication security' must light up auth/login/config
    entities even though they never say those exact words."""
    g, (jwt_id, login_id, config_id, payment_id) = _knowledge()
    scores = ActivationEngine().propagate(g, "Analyze authentication security")
    assert scores[jwt_id] > 0.5
    assert scores[login_id] > 0.5
    assert scores[payment_id] < 0.5   # unrelated stays dark
