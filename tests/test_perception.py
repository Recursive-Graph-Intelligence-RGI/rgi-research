from rgi.core.models import LoopType, NodeType
from rgi.perception.code_parser import PerceptionLayer


async def test_ingest_creates_entities_and_edges(tmp_path):
    (tmp_path / "auth.py").write_text(
        "import jwt\n\nclass JWTManager:\n    def decode(self, t):\n        return jwt.decode(t, 'k')\n"
    )
    (tmp_path / "session.py").write_text(
        "import auth\n\nclass SessionStore:\n    pass\n"
    )
    graph = await PerceptionLayer().ingest_codebase(str(tmp_path))
    assert graph.loop_type == LoopType.KNOWLEDGE
    names = {n.metadata["name"] for n in graph.nodes.values()}
    assert {"JWTManager", "decode", "SessionStore"} <= names
    assert all(n.type == NodeType.MEMORY for n in graph.nodes.values())
    assert len(graph.edges) >= 1  # session.py imports auth
    jwt_node = next(n for n in graph.nodes.values() if n.metadata["name"] == "JWTManager")
    assert jwt_node.confidence == 1.0


async def test_ingest_persists_minimum_entities(tmp_path):
    for i in range(3):
        (tmp_path / f"mod{i}.py").write_text(f"class C{i}:\n    def f(self):\n        pass\n")
    graph = await PerceptionLayer().ingest_codebase(str(tmp_path))
    assert len(graph.nodes) >= 5
