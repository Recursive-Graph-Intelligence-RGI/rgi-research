"""Verification loop: challenges findings, triggers correction. The ACC of
the system — it detects conflict; it does not retry."""
from rgi.core.models import CognitiveEdge, CognitiveGraph, CognitiveNode, NodeType


def _format_finding(finding):
    if isinstance(finding, dict):
        inner = finding.get("finding")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, dict):
            finding = inner
        return (
            f"{finding.get('kind', 'finding')} ({finding.get('severity', '?')}) — "
            f"{finding.get('detail', '')} @ {finding.get('file', '?')}:{finding.get('line', '?')} "
            f"[{finding.get('symbol', '?')}]"
        )
    return str(finding)


def initialize(graph: CognitiveGraph, proposal: dict) -> None:
    objective = proposal["objective"]
    threshold = proposal.get("confidence_threshold", graph.state.confidence_threshold)
    graph.state.confidence_threshold = threshold
    verifier = CognitiveNode(
        type=NodeType.VERIFICATION,
        content=f"Challenge findings for: {objective}",
        parent_graph_id=graph.id,
        metadata={"confidence_threshold": threshold},
    )
    graph.nodes[verifier.id] = verifier

    for finding in proposal.get("target_findings", []):
        evidence = CognitiveNode(
            type=NodeType.MEMORY,
            content=f"Finding under challenge ({objective}): {_format_finding(finding)}",
            confidence=float(finding.get("confidence", 0.5)),
            parent_graph_id=graph.id,
            metadata={"challenged_finding": finding},
        )
        graph.nodes[evidence.id] = evidence
        graph.edges.append(CognitiveEdge(source=verifier.id, target=evidence.id,
                                         edge_type="verifies"))
