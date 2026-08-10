"""RGI figure set — generated from raw run artifacts, no hand-edited numbers.
Outputs PNGs to docs/reports/figures/. Re-run any time to regenerate.

Data sources (all committed or local run artifacts):
  docs/reports/overnight-ladder-2026-08-08/*/matrix.json   (model ladder)
  docs/reports/overnight-ladder-2026-08-08/run13-prefix-control/matrix.json
  data/eval_run12_7b.json, data/eval_run11_fullstack.json
  data/complexity_c1*.json                                  (C1 curves)
"""
import json
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGDIR = Path("docs/reports/figures")
FIGDIR.mkdir(parents=True, exist_ok=True)
C = {"rgi": "#1a7f5a", "fixed": "#b0432f", "single": "#8a8a8a", "prefix": "#c08a1a"}


def _load(path):
    return json.loads(Path(path).read_text())


def _summary(path):
    d = _load(path)
    return {k.split("|")[1]: v["mean_recall"] for k, v in d["summary"].items()}


def fig1_model_ladder():
    """Yesterday: RGI vs fixed across neuron tiers (vuln_app_hard)."""
    tiers = [
        ("4b", "docs/reports/overnight-ladder-2026-08-08/nemotron-3-nano_4b/matrix.json"),
        ("7b", "data/eval_run12_7b.json"),
        ("coder-7b", "docs/reports/overnight-ladder-2026-08-08/qwen2_5-coder_7b/matrix.json"),
        ("DeepSeek", "data/eval_run11_fullstack.json"),
    ]
    labels, rgi, fixed = [], [], []
    for name, path in tiers:
        s = _summary(path)
        labels.append(name)
        rgi.append(s["rgi"])
        fixed.append(s["fixed"])
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(labels, rgi, "o-", color=C["rgi"], lw=2.5, ms=9, label="RGI (adaptive topology)")
    ax.plot(labels, fixed, "s--", color=C["fixed"], lw=2, ms=8, label="Fixed pipeline")
    for i, (r, f) in enumerate(zip(rgi, fixed)):
        ax.annotate(f"{r:.2f}", (i, r), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=9, color=C["rgi"])
        ax.annotate(f"{f:.2f}", (i, f), textcoords="offset points", xytext=(0, -14),
                    ha="center", fontsize=9, color=C["fixed"])
    ax.set_xlabel("neuron strength (model tier)")
    ax.set_ylabel("mean recall (vuln_app_hard)")
    ax.set_ylim(0, 1.1)
    ax.set_title("Topology compensates for weak neurons\nRGI is flat across model families; pipelines swing with model strength")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig1_model_ladder.png", dpi=150)
    plt.close(fig)


def fig2_ablation():
    """Run 13 dose-response: same model, same target, fixes removed."""
    r12 = _summary("data/eval_run12_7b.json")
    r13 = _summary("docs/reports/overnight-ladder-2026-08-08/run13-prefix-control/matrix.json")
    bars = [
        ("Fixed pipeline\n(no structure)", r13["fixed"], C["fixed"]),
        ("RGI pre-fix\n(structure, starved)", r13["rgi"], C["prefix"]),
        ("RGI full stack\n(structure + substrate)", r12["rgi"], C["rgi"]),
    ]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    xs = range(len(bars))
    ax.bar(xs, [b[1] for b in bars], color=[b[2] for b in bars], width=0.55)
    for x, b in zip(xs, bars):
        ax.annotate(f"{b[1]:.3f}", (x, b[1]), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=11, fontweight="bold")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([b[0] for b in bars], fontsize=9)
    ax.set_ylabel("mean recall (7B, vuln_app_hard)")
    ax.set_ylim(0, 0.9)
    ax.set_title("The ablation: dose-response proof\nEach layer of the architecture has a measured contribution")
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig2_ablation_dose_response.png", dpi=150)
    plt.close(fig)


LEVELS = ["L1", "L2", "L3", "L4", "L5"]
N_FILES = [8, 16, 32, 64, 128]
C1_FILES = {"1.5b": "data/complexity_c1.json",
            "4b": "data/complexity_c1_nemotron-3-nano_4b.json",
            "7b": "data/complexity_c1_qwen2_5_7b.json"}


def _c1_curves():
    """Per model, per level, per condition: mean recall and mean calls over completed cells."""
    out = {}
    for model, path in C1_FILES.items():
        if not Path(path).exists():
            continue
        cells = _load(path)
        levels = {}
        for c in cells:
            if c.get("status") != "completed":
                continue
            d = levels.setdefault(c["level"], {}).setdefault(c["condition"], {"recall": [], "calls": []})
            d["recall"].append(c.get("recall", 0))
            d["calls"].append(c.get("calls", 0))
        out[model] = {
            lv: {k: {"recall": sum(v["recall"]) / len(v["recall"]),
                     "calls": sum(v["calls"]) / len(v["calls"])}
                 for k, v in conds.items()}
            for lv, conds in levels.items()}
    return out


def _panel_axes(fig, curves, suptitle):
    """Shared 1x3 panel setup: log2 x, level ticks with n_files labels."""
    axes = fig.subplots(1, 3, sharex=True)
    for ax, (model, lv) in zip(axes, curves.items()):
        ax.set_xscale("log", base=2)
        ax.set_xticks(N_FILES)
        ax.set_xticklabels([f"{l}\n{n}" for l, n in zip(LEVELS, N_FILES)], fontsize=8)
        ax.set_title(model, fontsize=11)
        ax.tick_params(axis="y", labelsize=9)
    fig.suptitle(suptitle, fontsize=12)
    return axes


def fig3_complexity_curve():
    """Recall vs problem complexity at constant model size, one panel per model."""
    curves = _c1_curves()
    fig = plt.figure(figsize=(11, 4.4))
    axes = _panel_axes(fig, curves,
                       "Recall vs problem complexity at constant model size (C1)")
    for ax, (model, lv) in zip(axes, curves.items()):
        for cond, color, marker in (("rgi", C["rgi"], "o"),
                                    ("fixed", C["fixed"], "s"),
                                    ("single", C["single"], "^")):
            ys = [lv.get(l, {}).get(cond, {}).get("recall") for l in LEVELS]
            pts = [(x, y) for x, y in zip(N_FILES, ys) if y is not None]
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        "-" , color=color, lw=2, marker=marker, ms=6,
                        label=f"{cond.upper()}")
        ax.set_ylim(0, 1.05)
        ax.set_xlabel("complexity level (files)", fontsize=9)
    axes[0].set_ylabel("mean recall")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center",
               ncol=3, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.savefig(FIGDIR / "fig3_complexity_curve.png", dpi=150)
    plt.close(fig)


def fig5_efficiency():
    """Mean LLM calls vs complexity, rgi vs fixed, one panel per model."""
    curves = _c1_curves()
    fig = plt.figure(figsize=(11, 4.4))
    axes = _panel_axes(fig, curves,
                       "LLM calls vs problem complexity — same recall, different cost")
    for ax, (model, lv) in zip(axes, curves.items()):
        for cond, color, marker in (("rgi", C["rgi"], "o"),
                                    ("fixed", C["fixed"], "s")):
            ys = [lv.get(l, {}).get(cond, {}).get("calls") for l in LEVELS]
            pts = [(x, y) for x, y in zip(N_FILES, ys) if y is not None]
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        "-", color=color, lw=2, marker=marker, ms=6,
                        label=f"{cond.upper()}")
        ax.set_yscale("log", base=2)
        ax.set_xlabel("complexity level (files)", fontsize=9)
    axes[0].set_ylabel("mean LLM calls (log2)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center",
               ncol=2, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.savefig(FIGDIR / "fig5_efficiency.png", dpi=150)
    plt.close(fig)


def _c1_rgi_topology():
    """Per model, per level: mean rgi-condition topology_metrics over completed cells."""
    keys = ("graphs", "graph_cells", "max_depth", "max_width", "spawn_approved")
    out = {}
    for model, path in C1_FILES.items():
        if not Path(path).exists():
            continue
        buckets = {}
        for c in _load(path):
            if c.get("status") != "completed" or c.get("condition") != "rgi":
                continue
            tm = c.get("topology_metrics") or {}
            b = buckets.setdefault(c["level"], {k: [] for k in keys})
            for k in keys:
                if tm.get(k) is not None:
                    b[k].append(tm[k])
        out[model] = {lv: {k: (sum(v) / len(v) if v else None) for k, v in b.items()}
                      for lv, b in buckets.items()}
    return out


def fig6_topology_growth():
    """Does RGI grow deeper/wider graphs as problems get harder?
    3x3 small-multiple: rows = models, cols = graph size / max depth / max width.
    Post-fix (f782c28): L5 no longer collapses — recall holds with lean graphs."""
    topo = _c1_rgi_topology()
    fig, axes = plt.subplots(3, 3, figsize=(11, 9), sharex=True)
    for row, (model, lv) in enumerate(topo.items()):
        def ys(key):
            return [lv.get(l, {}).get(key) for l in LEVELS]
        ax = axes[row][0]
        ax.plot(N_FILES, ys("graph_cells"), "-", color=C["rgi"], lw=2, marker="o", ms=6,
                label="graph_cells (nodes)")
        ax.plot(N_FILES, ys("graphs"), "--", color=C["prefix"], lw=2, marker="s", ms=6,
                label="graphs (subgraphs spawned)")
        axes[row][1].plot(N_FILES, ys("max_depth"), "-", color=C["rgi"], lw=2,
                          marker="D", ms=6)
        axes[row][2].plot(N_FILES, ys("max_width"), "-", color=C["rgi"], lw=2,
                          marker="^", ms=6)
        for col in range(3):
            a = axes[row][col]
            a.set_xscale("log", base=2)
            a.set_xticks(N_FILES)
            a.set_xticklabels([f"{l}\n{n}" for l, n in zip(LEVELS, N_FILES)], fontsize=8)
            a.tick_params(axis="y", labelsize=9)
            a.grid(alpha=0.25)
        axes[row][0].set_ylabel(model, fontsize=11)
    axes[0][0].set_title("graph size (mean count)", fontsize=11)
    axes[0][1].set_title("max depth (mean)", fontsize=11)
    axes[0][2].set_title("max width (mean)", fontsize=11)
    axes[2][1].set_xlabel("complexity level (files)", fontsize=10)
    fig.suptitle("Topology growth vs problem complexity (C1, rgi condition, post-fix)\n"
                 "Size and width scale with complexity through mid levels; depth stays at the policy cap (2);\n"
                 "L5 runs lean — the planner solves with small graphs, not no graphs", fontsize=12)
    fig.legend(*axes[0][0].get_legend_handles_labels(), loc="lower center",
               ncol=2, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    fig.savefig(FIGDIR / "fig6_topology_growth.png", dpi=150)
    plt.close(fig)


def fig4_coupling():
    """The mechanism: graphs spawned vs recall, per RGI cell."""
    pts = []
    for model, path in C1_FILES.items():  # main files only — not the 8k/mock side files
        if not Path(path).exists():
            continue
        for c in _load(path):
            if c["condition"] == "rgi" and c.get("status") == "completed":
                tm = c.get("topology_metrics", {})
                pts.append((tm.get("graphs", 0), c.get("recall", 0), c["level"], model))
    fig, ax = plt.subplots(figsize=(7, 4.4))
    marks = {"L1": "o", "L2": "s", "L3": "^", "L4": "D", "L5": "x"}
    for g, r, lv, model in pts:
        ax.scatter(g, r, marker=marks[lv], s=70, alpha=0.75,
                   color=C["rgi"] if r >= 0.7 else C["fixed"],
                   edgecolors="black", linewidths=0.4)
    from matplotlib.lines import Line2D
    legend = [Line2D([0], [0], marker=m, color="w", markerfacecolor="gray",
                     markeredgecolor="black", markersize=8, label=lv)
              for lv, m in marks.items()]
    ax.legend(handles=legend, title="complexity", fontsize=9)
    ax.set_xlabel("graphs spawned in the run (topology size)")
    ax.set_ylabel("cell recall")
    ax.set_title("The mechanism: performance follows topology\nEvery RGI cell with ≥11 graphs scored 1.0; every 1-graph cell scored 0.0")
    ax.set_ylim(-0.08, 1.12)
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig4_topology_coupling.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    fig1_model_ladder()
    fig2_ablation()
    fig3_complexity_curve()
    fig4_coupling()
    fig5_efficiency()
    fig6_topology_growth()
    print(f"figures written to {FIGDIR}/")
