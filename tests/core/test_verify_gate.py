from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from rgi.core.engine import verify_findings
from rgi.core.models import CognitiveNode, NodeState, NodeType


@pytest.mark.asyncio
async def test_verify_rejects_ungrounded_finding():
    """A reasoning node whose result is ungrounded and below the confidence
    threshold should be auto-challenged, even if no one pre-tagged it with
    `challenged_finding` metadata."""
    node = CognitiveNode(
        type=NodeType.VERIFICATION, content="verify", parent_graph_id="g"
    )
    target = CognitiveNode(
        type=NodeType.REASONING,
        content="reason",
        parent_graph_id="g",
        state=NodeState.COMPLETED,
        confidence=0.55,
        result={"finding": {"kind": "suspicious", "detail": "maybe bad", "confidence": 0.55}},
    )

    harness = SimpleNamespace(
        total_llm_calls=0,
        gate=SimpleNamespace(check=lambda *a, **k: SimpleNamespace(allowed=True)),
        llm_client=AsyncMock(),
        audit=SimpleNamespace(record=lambda **k: None),
    )
    harness.llm_client.reason.return_value = {
        "finding_valid": False,
        "confidence": 0.9,
        "detail": "no file cited",
    }

    result = await verify_findings(node, [target], harness)
    assert result["finding_valid"] is False
