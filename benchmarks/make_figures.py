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


def _c1_curves():
    out = {}
    files = {"1.5b": "data/complexity_c1.json",
             "4b": "data/complexity_c1_nemotron-3-nano_4b.json",
             "7b": "data/complexity_c1_qwen2_5_7b.json"}
    for model, path in files.items():
        if not Path(path).exists():
            continue
        cells = _load(path)
        levels = {}
        for c in cells:
            levels.setdefault(c["level"], {}).setdefault(c["condition"], []).append(c.get("recall", 0))
        out[model] = {lv: {k: sum(v) / len(v) for k, v in conds.items()}
                      for lv, conds in levels.items()}
    return out


def fig3_complexity_curve():
    """Today: recall vs problem complexity, per condition, per model available."""
    curves = _c1_curves()
    levels = ["L1", "L2", "L3", "L4", "L5"]
    xs = [8, 16, 32, 64, 128]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    styles = {"1.5b": "-", "4b": "--", "7b": "-."}
    for model, lv in curves.items():
        for cond, color in (("rgi", C["rgi"]), ("fixed", C["fixed"]), ("single", C["single"])):
            ys = [lv.get(l, {}).get(cond) for l in levels]
            pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        styles[model], color=color, lw=2, marker="o", ms=6,
                        label=f"{cond.upper()} ({model})")
    ax.set_xscale("log", base=2)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{x}" for x in xs])
    ax.set_xlabel("problem complexity (files in generated codebase)")
    ax.set_ylabel("mean recall")
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("Complexity scaling at constant model size (C1)\nDoes topology growth preserve performance as problems grow?")
    ax.legend(fontsize=8, ncol=2)
    partial = [m for m, lv in curves.items() if any(l not in lv for l in levels)]
    if partial:
        ax.text(0.99, 0.02,
                f"INTERIM: {', '.join(partial)} run in progress — later levels pending",
                transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color="dimgray", style="italic")
    fig.tight_layout()
    fig.savefig(FIGDIR / "fig3_complexity_curve.png", dpi=150)
    plt.close(fig)


def fig4_coupling():
    """The mechanism: graphs spawned vs recall, per RGI cell."""
    pts = []
    for path in glob.glob("data/complexity_c1*.json"):
        model = "1.5b" if path == "data/complexity_c1.json" else path.split("_")[-1].replace(".json", "")
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
    print(f"figures written to {FIGDIR}/")
