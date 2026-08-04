"""Verification loop: challenges findings, triggers correction. The ACC of
the system — it detects conflict; it does not retry."""
from rgi.core.models import CognitiveEdge, CognitiveGraph, CognitiveNode, NodeType


def initialize(graph: CognitiveGraph, proposal: dict) -> None:
    objective = proposal["objective"]
    verifier = CognitiveNode(
        type=NodeType.VERIFICATION,
        content=f"Challenge findings for: {objective}",
        parent_graph_id=graph.id,
    )
    graph.nodes[verifier.id] = verifier

    for finding in proposal.get("target_findings", []):
        evidence = CognitiveNode(
            type=NodeType.MEMORY,
            content=f"Finding under challenge ({objective}): {finding.get('finding', finding)}",
            confidence=float(finding.get("confidence", 0.5)),
            parent_graph_id=graph.id,
            metadata={"challenged_finding": finding},
        )
        graph.nodes[evidence.id] = evidence
        graph.edges.append(CognitiveEdge(source=verifier.id, target=evidence.id,
                                         edge_type="verifies"))
