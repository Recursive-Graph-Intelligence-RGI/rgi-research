"""RGI CLI: python -m rgi analyze <path> --objective <text> [--mock]

Orchestration lives HERE (engineered code): perception -> world model ->
root planning graph -> recursive engine -> report. The LLM never sees this."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from rgi.baseline import MOCK_CAVEAT, run_baseline
from rgi.core.engine import execute_graph
from rgi.core.findings import normalize_finding
from rgi.core.harness import Harness, HarnessConfig
from rgi.core.models import CognitiveGraph, GraphPolicy, GraphState, LoopType
from rgi.loops import initialize_graph_nodes
from rgi.perception.code_parser import PerceptionLayer
from rgi.perception.rlmlocal_perception import RlmlocalPerceptionLayer
from rgi.reasoning.llm_client import LLMClient, MockLLMClient


def build_report(root, harness, knowledge) -> dict:
    graphs = [g for g in harness.graphs.values() if g.id != knowledge.id]
    findings = []
    for graph in graphs:
        for f in graph.memory_snapshot.get("merged_findings", []):
            findings.append({"graph": graph.state.objective, **f})
        for node in graph.nodes.values():
            if not isinstance(node.result, dict):
                continue
            if "finding" in node.result:
                normalized = normalize_finding(node.result["finding"])
                if normalized is not None:
                    normalized["confidence"] = node.confidence
                    findings.append({"graph": graph.state.objective, **normalized})
            for raw in node.result.get("findings", []):
                normalized = normalize_finding(raw)
                if normalized is not None:
                    normalized["confidence"] = node.confidence
                    findings.append({"graph": graph.state.objective, **normalized})
    completed = [n for g in graphs for n in g.nodes.values()
                 if n.state.value == "completed"]
    aggregate = (sum(n.confidence for n in completed) / len(completed)) if completed else 0.0
    return {
        "objective": root.state.objective,
        "status": root.state.status,
        "aggregate_confidence": round(aggregate, 3),
        "corrections_made": sum(1 for e in harness.audit.events
                                if e["event"] == "correction_completed"),
        "graphs_spawned": len(graphs) - 1,  # exclude the root itself
        "max_depth_reached": max((harness.depth_of(g) for g in graphs), default=0),
        "llm_calls": harness.total_llm_calls,
        # Experiment C1 instrumentation: the full topology/cost profile
        # per run, from the audit trail and graph registry.
        "topology_metrics": {
            "graphs": len(graphs),
            "graph_cells": sum(len(g.nodes) for g in graphs),
            "max_depth": max((harness.depth_of(g) for g in graphs), default=0),
            "max_width": max((len(g.subgraph_ids) for g in graphs), default=0),
            "spawn_approved": sum(1 for e in harness.audit.events
                                  if e["event"] == "spawn_approved"),
            "spawn_inhibited": sum(1 for e in harness.audit.events
                                   if e["event"] == "spawn_inhibited"),
            "spawn_rejected": sum(1 for e in harness.audit.events
                                  if e["event"] == "spawn_rejected"),
            "verification_ops": sum(1 for g in graphs
                                    if g.loop_type.value == "verification")
                                + sum(1 for e in harness.audit.events
                                      if e["event"] == "coverage_sweep"),
            "repl_rounds": sum(1 for e in harness.audit.events
                               if e["event"] == "repl_exploration"),
            "exec_failures": sum(1 for e in harness.audit.events
                                 if e["event"] in ("node_execution_error",
                                                   "child_execution_error")),
            "tokens_prompt": getattr(harness.llm_client, "tokens_prompt", 0),
            "tokens_completion": getattr(harness.llm_client, "tokens_completion", 0),
        },
        "findings": findings,
        "topology_used": {
            "root": f"{root.loop_type.value}:{root.id}",
            "subgraphs": [
                f"{g.loop_type.value}:{g.state.objective}"
                for g in graphs if g.parent_graph_id is not None
            ],
        },
        "execution_log": harness.audit.events,
    }


async def run_analysis(path, objective, output, mock, provider, model, max_llm_calls,
                       max_total_nodes=50, embed: bool = False) -> dict:
    data_dir = Path("data")
    # Local providers such as ollama do not require an API key; only fall back
    # to the deterministic mock when no key is set for cloud endpoints.
    is_local_provider = provider in ("ollama",)
    use_mock = mock or (not is_local_provider and not os.environ.get("RGI_LLM_API_KEY"))
    if is_local_provider and not os.environ.get("RGI_LLM_BASE_URL"):
        os.environ.setdefault("RGI_LLM_BASE_URL", "http://localhost:11434/v1")
    if is_local_provider and not os.environ.get("RGI_LLM_API_KEY"):
        os.environ.setdefault("RGI_LLM_API_KEY", "ollama")
    llm = MockLLMClient() if use_mock else LLMClient(model=model)
    config = HarnessConfig(target_path=path, max_llm_calls=max_llm_calls,
                           max_total_nodes=max_total_nodes,
                           # Local models blow past the 300s demo limit; RGI_MAX_SECONDS
                           # raises it for benchmarking without weakening the default.
                           max_seconds=int(os.environ.get("RGI_MAX_SECONDS", "300")),
                           llm_client=llm, data_dir=str(data_dir))
    if embed or os.environ.get("RGI_EMBED_BASE_URL"):
        from rgi.memory.activation import EmbeddingActivationEngine
        from rgi.reasoning.embeddings import OpenAICompatibleEmbeddings
        embed_provider = OpenAICompatibleEmbeddings(
            base_url=os.environ.get("RGI_EMBED_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.environ.get("RGI_EMBED_API_KEY", ""),
            model=os.environ.get("RGI_EMBED_MODEL", "nomic-embed-text"),
        )
        embed_threshold = float(os.environ.get("RGI_EMBED_THRESHOLD", "0.5"))
        config.activation_engine = EmbeddingActivationEngine(embed_provider, threshold=embed_threshold)
    harness = Harness(config)

    # Step 1: Perception builds the world model
    perception = RlmlocalPerceptionLayer() if os.environ.get("RGI_RLMLocal_PERCEPTION") == "1" else PerceptionLayer()
    knowledge = await perception.ingest_codebase(path)
    harness.graphs[knowledge.id] = knowledge
    (data_dir / "knowledge_graph.json").write_text(knowledge.model_dump_json(indent=2))

    # Step 2: Root planning graph, primed with the activated world model
    # Size-aware graph state: large real codebases need more iterations and a
    # slightly lower confidence bar to consolidate before the wall-clock budget.
    max_iterations = int(os.environ.get("RGI_MAX_ITERATIONS", "10"))
    confidence_threshold = float(os.environ.get("RGI_CONFIDENCE_THRESHOLD", "0.7"))
    root = CognitiveGraph(
        loop_type=LoopType.PLANNING,
        state=GraphState(
            objective=objective,
            max_iterations=max_iterations,
            confidence_threshold=confidence_threshold,
        ),
        policy=GraphPolicy(),
    )
    initialize_graph_nodes(root, {"objective": objective})
    # Magentic-style ledger: structured run state the verification and
    # replan machinery can read without re-parsing prose findings.
    root.memory_snapshot["ledger"] = {"facts": [], "gaps": [], "guesses": []}
    activated = await harness.activation_engine.a_propagate(knowledge, objective)
    root.memory_snapshot["world_model"] = {
        knowledge.nodes[nid].metadata["name"]: knowledge.nodes[nid].content
        for nid, score in activated.items()
        if score > getattr(harness.activation_engine, "threshold", 0.5) and nid in knowledge.nodes
    }
    harness.graphs[root.id] = root
    harness.audit.record("run_started", graph_id=root.id, objective=objective,
                         llm_mode="mock" if use_mock else provider)

    # Step 3: Recursive execution
    root = await execute_graph(root, harness)

    # Step 4: Persist and report
    for graph in harness.graphs.values():
        (data_dir / f"graph_{graph.id}.json").write_text(graph.model_dump_json(indent=2))
    report = build_report(root, harness, knowledge)
    Path(output).write_text(json.dumps(report, indent=2))
    harness.audit.record("run_finished", graph_id=root.id, status=root.state.status,
                         llm_calls=harness.total_llm_calls)
    return report


async def run_comparison(args) -> dict:
    use_mock = args.mock or not os.environ.get("RGI_LLM_API_KEY")
    baseline_llm = MockLLMClient() if use_mock else LLMClient(model=args.model)
    baseline = await run_baseline(args.path, args.objective, baseline_llm)
    rgi_report = await run_analysis(
        args.path, args.objective, str(Path("data") / "report_compare.json"),
        args.mock, args.provider, args.model, args.max_llm_calls,
        embed=args.embed,
    )
    return {
        "objective": args.objective,
        "caveat": MOCK_CAVEAT if use_mock else "",
        "rgi": rgi_report,
        "baseline": baseline,
        "deltas": {
            "findings_count": len(rgi_report["findings"]) - len(baseline["findings"]),
            "llm_calls": rgi_report["llm_calls"] - baseline["llm_calls"],
            "corrections": rgi_report["corrections_made"],
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="rgi")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="Analyze a codebase with recursive graph intelligence")
    analyze.add_argument("path")
    analyze.add_argument("--objective", required=True)
    analyze.add_argument("--output", default="report.json")
    analyze.add_argument("--mock", action="store_true", help="Force the deterministic mock LLM")
    analyze.add_argument("--provider", default="kimi")
    analyze.add_argument("--model", default=None)
    analyze.add_argument("--max-llm-calls", type=int, default=20)
    analyze.add_argument("--embed", action="store_true",
                         help="Seed activation with embeddings (OpenAI-compatible endpoint)")
    compare = sub.add_parser("compare", help="Run RGI vs single-agent baseline on the same target")
    compare.add_argument("path")
    compare.add_argument("--objective", required=True)
    compare.add_argument("--output", default="compare.json")
    compare.add_argument("--mock", action="store_true")
    compare.add_argument("--provider", default="kimi")
    compare.add_argument("--model", default=None)
    compare.add_argument("--max-llm-calls", type=int, default=20)
    compare.add_argument("--embed", action="store_true",
                         help="Seed activation with embeddings (OpenAI-compatible endpoint)")
    evaluate = sub.add_parser("eval", help="Run the target x condition x repetition experiment matrix")
    evaluate.add_argument("--objective", required=True)
    evaluate.add_argument("--runs", type=int, default=3)
    evaluate.add_argument("--output", default="eval_report.json")
    evaluate.add_argument("--mock", action="store_true")
    evaluate.add_argument("--provider", default="kimi")
    evaluate.add_argument("--model", default=None)
    evaluate.add_argument("--max-llm-calls", type=int, default=20)
    evaluate.add_argument("--target", default=None)
    evaluate.add_argument("--embed", action="store_true",
                          help="Seed activation with embeddings (OpenAI-compatible endpoint)")
    server = sub.add_parser("server", help="Run RGI as a local HTTP service")
    server.add_argument("--host", default="127.0.0.1", help="Bind address")
    server.add_argument("--port", type=int, default=8787, help="Bind port")
    args = parser.parse_args(argv)

    if args.command == "server":
        from rgi.server import main as server_main
        asyncio.run(server_main(host=args.host, port=args.port))
        return 0
    if args.command == "analyze":
        report = asyncio.run(run_analysis(
            args.path, args.objective, args.output,
            args.mock, args.provider, args.model, args.max_llm_calls,
            embed=args.embed,
        ))
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "completed" else 1
    if args.command == "compare":
        comparison = asyncio.run(run_comparison(args))
        print(json.dumps(comparison, indent=2))
        Path(args.output).write_text(json.dumps(comparison, indent=2) + "\n")
        return 0 if comparison["rgi"]["status"] == "completed" else 1
    if args.command == "eval":
        from rgi.eval import run_eval
        result = asyncio.run(run_eval(args.objective, args.runs, args.mock,
                                      args.provider, args.model, args.max_llm_calls,
                                      target_filter=args.target, embed=args.embed))
        print(json.dumps(result, indent=2))
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
