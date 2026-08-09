# Recursive Graph Intelligence (RGI) Vision

## Introduction

Recursive Graph Intelligence (RGI) explores a future architecture for autonomous systems where graphs are treated as fundamental computational structures.

Instead of relying on a single agent following a fixed workflow, RGI proposes networks of specialized graphs that can reason, execute, verify, learn, and adapt through continuous interaction.

## Core Idea

A graph can contain another graph.

Complex objectives can be decomposed into specialized recursive structures:

- Planning graphs
- Knowledge graphs
- Execution graphs
- Verification graphs
- Governance graphs
- Learning graphs

Each graph maintains its own state, policies, and objectives while communicating with other graphs.

## Why Graphs?

Graphs naturally represent:

- Relationships
- Dependencies
- Context
- Memory
- Decision pathways
- Feedback loops

Many complex systems in nature and computing are graph-based. RGI explores whether graph-native architectures can provide a stronger foundation for autonomous intelligence.

## Recursive Architecture

A high-level RGI system may contain:

```
Global Intelligence Graph
├── Planning Graph
├── Knowledge Graph
├── Execution Graph
├── Governance Graph
└── Learning Graph
```

Each component may contain additional specialized subgraphs.

## Research Direction

RGI investigates:

- Adaptive graph creation
- Multi-agent coordination
- Self-organizing computation
- Long-term memory structures
- Governance-aware autonomy
- Safe autonomous evolution

## The Substrate Thesis (added 2026-08-08, after Run 12)

The transformer stops being the product and starts being the substrate.

The industry currently treats the LLM as the whole machine: bigger model =
better system. RGI's evidence points at a division of labor instead —
transformer as *neuron*, topology as *brain*. If the crossover curve holds
at scale, this does not replace transformers; it demotes them to components.
Twenty cheap models wired correctly can do the work of one frontier model.
That is an economic revolution more than an architectural one — distributed
systems did not replace CPUs, they changed which CPUs you buy and how you
wire them.

The graph-inside-the-model idea already won once: **Mixture-of-Experts**.
Router = harness, experts = specialized subgraphs, sparse activation = the
activation engine. The transformer was not replaced; it was topologized
from the inside. RGI is the same principle one level up, at the system
level, where the "experts" are full cognitive graphs instead of
feed-forward blocks.

The credible path, in order of plausibility:

1. **Neurons trained for node-life** — models fine-tuned to be good nodes
   (explore, report confidence honestly, write REPL code) rather than good
   chatbots. RLM (MIT, 2025) showed a small model fine-tuned on 1,000
   trajectories approaches frontier performance. Near-term, buildable.
2. **Learned topology** — v0.3's spawn policy: a GNN trained on the
   pathway logs RGI already collects, deciding when to spawn, verify, and
   prune. Routing moves from rules to learned weights — MoE's router at
   system scale.
3. **End-to-end graph-native models** — replacing the transformer
   wholesale with a recurrent subgraph-REPL structure. No evidence this
   works yet; attention is extraordinarily good at what it does. Not our
   fight — and better neurons only make the graph smarter, so RGI wins
   either way.

The architecture that routes, spawns, verifies, and governs becomes the
product. The model is the ingredient. RGI aims to be the operating system
for that layer — with the safety kernel (hard limits, full audit trail)
that no foundation-model lab will bother to build and every serious
deployment will need.

## Current Status

RGI is an early-stage research initiative focused on developing concepts, specifications, and prototypes for recursive graph-based autonomous systems.

As of 2026-08-08 the prototype has a running reference implementation with
controlled benchmark evidence: adaptive topology doubles a fixed pipeline
at the 7B local-model tier on a 15-vulnerability target (Run 12:
0.711 vs 0.355), and ties it at the frontier-API tier. See
`docs/reports/2026-08-04-rgi-status-report.md` for the full scorecard and
`docs/strategy.md` for the open-research strategy and claim ladder.
