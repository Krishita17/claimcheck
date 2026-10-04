"""Generate all README figures from the benchmark outputs.

Every chart embedded in the README is produced here (none are hand-drawn), so a
`make figures` run after `make bench` fully refreshes them. Reads
``results/metrics.json`` and the CSVs written by ``benchmark.py``.

Usage::

    python experiments/make_figures.py --results results --out figures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# A small, colorblind-friendly palette mapped to verdicts.
VERDICT_COLORS = {
    "CLAIMABLE": "#d1495b",        # red  — exploitable exposure
    "TAKEN-NOT-YOURS": "#edae49",  # amber — investigate
    "PROTECTED": "#00798c",        # teal — mitigated
    "SAFE": "#66a182",             # green — fine
}
VERDICT_ORDER = ["CLAIMABLE", "TAKEN-NOT-YOURS", "PROTECTED", "SAFE"]


def _style(ax, title, ylabel=None):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)


def fig_verdict_distribution(metrics, out: Path):
    dist = metrics["verdict_distribution"]
    labels = [v for v in VERDICT_ORDER if v in dist]
    values = [dist[v] for v in labels]
    colors = [VERDICT_COLORS[v] for v in labels]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, values, color=colors)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.3, str(v),
                ha="center", va="bottom", fontweight="bold")
    _style(ax, "Verdict distribution across scanned names", "names")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=10)
    fig.tight_layout()
    fig.savefig(out / "verdict_distribution.png", dpi=150)
    plt.close(fig)


def fig_classifier_accuracy(metrics, out: Path):
    prf = metrics["classification_prf"]
    classes = list(prf.keys())
    metr = ["precision", "recall", "f1"]
    x = range(len(classes))
    width = 0.25
    fig, ax = plt.subplots(figsize=(7, 4.2))
    palette = ["#2e4057", "#00798c", "#66a182"]
    for i, mname in enumerate(metr):
        vals = [prf[c][mname] for c in classes]
        ax.bar([xi + (i - 1) * width for xi in x], vals, width,
               label=mname, color=palette[i])
    ax.set_xticks(list(x))
    ax.set_xticklabels([c.capitalize() for c in classes])
    ax.set_ylim(0, 1.05)
    _style(ax, "Internal/external classifier accuracy", "score")
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.28))
    fig.tight_layout()
    fig.savefig(out / "classifier_accuracy.png", dpi=150)
    plt.close(fig)


def _stacked(ax, categories, series_by_verdict):
    bottoms = [0] * len(categories)
    for v in VERDICT_ORDER:
        vals = [series_by_verdict.get(c, {}).get(v, 0) for c in categories]
        ax.bar(categories, vals, bottom=bottoms, label=v, color=VERDICT_COLORS[v])
        bottoms = [b + x for b, x in zip(bottoms, vals)]


def fig_by_ecosystem(metrics, out: Path):
    data = metrics["by_ecosystem"]
    cats = list(data.keys())
    fig, ax = plt.subplots(figsize=(6, 4.2))
    _stacked(ax, cats, data)
    _style(ax, "Exposure by ecosystem", "names")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "exposure_by_ecosystem.png", dpi=150)
    plt.close(fig)


def fig_by_source(metrics, out: Path):
    data = metrics["by_source"]
    cats = sorted(data.keys())
    fig, ax = plt.subplots(figsize=(9, 4.5))
    _stacked(ax, cats, data)
    _style(ax, "Where exposures hide: findings by source type", "names")
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, rotation=25, ha="right")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "exposure_by_source.png", dpi=150)
    plt.close(fig)


def fig_false_positives(metrics, out: Path):
    fp_rate = metrics["public_false_positive_rate"]
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
    correct = 1 - fp_rate
    ax.bar(["Public packages"], [correct], color=VERDICT_COLORS["SAFE"],
           label="correctly SAFE")
    ax.bar(["Public packages"], [fp_rate], bottom=[correct],
           color=VERDICT_COLORS["CLAIMABLE"], label="false positive")
    ax.set_ylim(0, 1.05)
    ax.text(0, correct / 2, f"{correct:.0%}", ha="center", va="center",
            color="white", fontweight="bold")
    if fp_rate > 0:
        ax.text(0, correct + fp_rate / 2, f"{fp_rate:.0%}", ha="center",
                va="center", color="white", fontweight="bold")
    _style(ax, "False-positive analysis on public packages", "fraction")
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.3), ncol=2)
    fig.tight_layout()
    fig.savefig(out / "false_positive_analysis.png", dpi=150)
    plt.close(fig)


def fig_fallback_impact(metrics, out: Path):
    fi = metrics["fallback_impact"]
    labels = ["Claimable &\nexploitable", "Protected\n(config blocks fallback)"]
    vals = [fi["claimable_exploitable"], fi["protected"]]
    colors = [VERDICT_COLORS["CLAIMABLE"], VERDICT_COLORS["PROTECTED"]]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    bars = ax.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.2, str(v),
                ha="center", va="bottom", fontweight="bold")
    _style(ax, "Fallback impact: exposure vs. risk", "internal unclaimed names")
    fig.tight_layout()
    fig.savefig(out / "fallback_impact.png", dpi=150)
    plt.close(fig)


def fig_architecture(out: Path):
    """Render the architecture as a block diagram (code-generated, not hand-drawn)."""
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.axis("off")
    boxes = [
        ("Source\ncollectors", 0.02, "#2e4057"),
        ("Name extractor\n+ normalizer", 0.20, "#2e4057"),
        ("Internal/external\nclassifier", 0.38, "#00798c"),
        ("Read-only\nregistry probe", 0.56, "#00798c"),
        ("Fallback / config\nanalyzer", 0.74, "#00798c"),
    ]
    y = 0.60
    w, h = 0.15, 0.22
    for label, x, color in boxes:
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=color,
                                   edgecolor="black", alpha=0.9))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                color="white", fontsize=9, fontweight="bold")
    # arrows between the top row
    for i in range(len(boxes) - 1):
        x0 = boxes[i][1] + w
        x1 = boxes[i + 1][1]
        ax.annotate("", xy=(x1, y + h / 2), xytext=(x0, y + h / 2),
                    arrowprops=dict(arrowstyle="->", lw=1.5))
    # core box (wide enough to receive all three feed arrows)
    core_x, core_y, core_w, core_h = 0.24, 0.18, 0.66, 0.18
    ax.add_patch(plt.Rectangle((core_x, core_y), core_w, core_h,
                               facecolor="#d1495b", edgecolor="black"))
    ax.text(core_x + core_w / 2, core_y + core_h / 2,
            "Exposure scorer + verdict engine  (CORE)\n"
            "CLAIMABLE / TAKEN-NOT-YOURS / PROTECTED / SAFE",
            ha="center", va="center", color="white", fontsize=9, fontweight="bold")
    # feed arrows into core
    for _, x, _ in boxes[2:]:
        ax.annotate("", xy=(x + w / 2, core_y + core_h),
                    xytext=(x + w / 2, y), arrowprops=dict(arrowstyle="->", lw=1.2,
                                                           color="#555"))
    # report box (centered under the core)
    rep_cx = core_x + core_w / 2
    rep_x = rep_cx - 0.10
    ax.add_patch(plt.Rectangle((rep_x, 0.00), 0.20, 0.10,
                               facecolor="#66a182", edgecolor="black"))
    ax.text(rep_cx, 0.05, "Exposure report\n(text / JSON / SARIF)",
            ha="center", va="center", color="white", fontsize=8, fontweight="bold")
    ax.annotate("", xy=(rep_cx, 0.10), xytext=(rep_cx, core_y),
                arrowprops=dict(arrowstyle="->", lw=1.5))
    ax.set_xlim(0, 0.9)
    ax.set_ylim(-0.02, 0.9)
    ax.set_title("ClaimCheck architecture", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "architecture.png", dpi=150)
    plt.close(fig)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate ClaimCheck figures.")
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="figures")
    args = ap.parse_args(argv)

    results = Path(args.results)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    metrics = json.loads((results / "metrics.json").read_text())

    fig_verdict_distribution(metrics, out)
    fig_classifier_accuracy(metrics, out)
    fig_by_ecosystem(metrics, out)
    fig_by_source(metrics, out)
    fig_false_positives(metrics, out)
    fig_fallback_impact(metrics, out)
    fig_architecture(out)
    print(f"figures written -> {out}/ (7 PNGs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
