"""Render the longitudinal biomarker insight-system architecture."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "insight_engine_architecture.png"
MPL_CACHE_DIR = ROOT / ".matplotlib"
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def box(ax, x, y, w, h, text, fc="#f7f9fb", ec="#41515c", fontsize=9.5):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.018,rounding_size=0.025",
        linewidth=1.1,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color="#172026",
        wrap=True,
    )


def arrow(ax, x1, y1, x2, y2, color="#52636f"):
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(arrowstyle="->", lw=1.35, color=color, shrinkA=8, shrinkB=8),
    )


def main() -> None:
    fig, ax = plt.subplots(figsize=(13.2, 7.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(
        0.5,
        0.965,
        "Hormone Insight Engine: structured algorithms generate the insight; the LLM phrases it safely",
        ha="center",
        va="top",
        fontsize=15,
        fontweight="bold",
        color="#172026",
    )

    # Main flow.
    box(
        ax,
        0.04,
        0.70,
        0.18,
        0.14,
        "User data inputs\nperiods, LH, E3G, PdG,\nsymptoms, goals, context",
        fc="#eef6ff",
    )
    box(
        ax,
        0.28,
        0.70,
        0.18,
        0.14,
        "Data quality layer\nidentity, timestamps,\ncycle assignment,\nmissingness checks",
        fc="#f7f9fb",
    )
    box(
        ax,
        0.52,
        0.70,
        0.18,
        0.14,
        "Longitudinal feature layer\ncycle baseline, hormone trends,\nstate history, uncertainty",
        fc="#f7f9fb",
    )
    box(
        ax,
        0.76,
        0.70,
        0.18,
        0.14,
        "Insight decision layer\nrules/models decide\nwhat can be said",
        fc="#edfdf7",
    )

    # Middle flow.
    box(
        ax,
        0.18,
        0.42,
        0.20,
        0.15,
        "Confidence gate\nsufficient tests?\nright cycle phase?\nlabel/edge-case safe?",
        fc="#fff8e8",
    )
    box(
        ax,
        0.44,
        0.42,
        0.20,
        0.15,
        "Structured insight object\nintent, evidence, confidence,\nallowed claims, no-call reason",
        fc="#edfdf7",
    )
    box(
        ax,
        0.70,
        0.42,
        0.20,
        0.15,
        "LLM wording layer\ncontrolled prompt,\nstructured input only,\nlimited response schema",
        fc="#f3f0ff",
    )

    # Output and control plane.
    box(
        ax,
        0.44,
        0.17,
        0.20,
        0.15,
        "Safety validator\nclaim checks, tone checks,\nmedical boundary checks,\nfallback templates",
        fc="#fff1f2",
    )
    box(
        ax,
        0.70,
        0.17,
        0.20,
        0.15,
        "App insight shown\nor no-call message\nwith next best action",
        fc="#eef6ff",
    )
    box(
        ax,
        0.04,
        0.17,
        0.26,
        0.15,
        "Monitoring and governance\nversioning, audit logs,\nA/B tests, drift, subgroup safety,\nhuman review queues",
        fc="#f7f9fb",
    )

    # Arrows.
    arrow(ax, 0.22, 0.86, 0.28, 0.86)
    arrow(ax, 0.46, 0.86, 0.52, 0.86)
    arrow(ax, 0.70, 0.86, 0.76, 0.86)
    arrow(ax, 0.85, 0.70, 0.32, 0.57)
    arrow(ax, 0.38, 0.495, 0.44, 0.495)
    arrow(ax, 0.64, 0.495, 0.70, 0.495)
    arrow(ax, 0.80, 0.42, 0.62, 0.32)
    arrow(ax, 0.64, 0.245, 0.70, 0.245)
    arrow(ax, 0.30, 0.245, 0.44, 0.245)
    arrow(ax, 0.54, 0.42, 0.54, 0.32)

    ax.text(
        0.18,
        0.05,
        "Core design principle: the LLM does not infer hormone meaning directly. It turns approved structured insights into safe app language.",
        ha="left",
        va="bottom",
        fontsize=10.5,
        color="#33444f",
    )

    OUT.parent.mkdir(exist_ok=True)
    fig.tight_layout(pad=0.6)
    fig.savefig(OUT, dpi=180)
    plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
