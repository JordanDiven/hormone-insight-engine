"""Render the ovulation-window analysis daily fertile-window flowchart as a PNG."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fertile_window_flow.png"


def box(ax, xy, text, width=3.8, height=0.72, fc="#ffffff", ec="#cbd5e1"):
    x, y = xy
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.03,rounding_size=0.08",
        linewidth=1.5,
        edgecolor=ec,
        facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=9.5, color="#101828", wrap=True)


def arrow(ax, start, end):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops=dict(arrowstyle="->", color="#344054", lw=1.6),
    )


def main():
    OUT.parent.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f7f8fb")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    ax.text(
        5,
        9.55,
        "Daily prospective fertile-window engine",
        ha="center",
        va="center",
        fontsize=17,
        fontweight="bold",
        color="#101828",
    )
    ax.text(
        5,
        9.15,
        "Run daily or whenever a new hormone test is logged. Use only data available at that moment.",
        ha="center",
        va="center",
        fontsize=9.5,
        color="#475467",
    )

    box(ax, (5, 8.4), "New cycle starts\nPeriod start = cycle day 1")
    box(ax, (5, 7.35), "Create initial calendar prior\nLow confidence")
    box(ax, (5, 6.25), "Enough prior cycles?", fc="#fff8e6", ec="#e7b800")
    box(ax, (2.4, 5.1), "No\nKeep generic calendar prior")
    box(ax, (7.6, 5.1), "Yes\nPersonalise expected window")
    box(ax, (5, 3.9), "Hormone tests available today?", fc="#fff8e6", ec="#e7b800")
    box(ax, (2.4, 2.7), "No\nShow low-confidence calendar guidance", fc="#edf7f3", ec="#2f9e7e")
    box(ax, (7.6, 2.7), "Yes\nAssess E3G, LH, and PdG", fc="#ffffff")
    box(ax, (5, 1.55), "Daily app state\nPrior only, E3G rising, LH 24-48h,\nawaiting PdG, confirmation, or no-call", width=5.2, height=0.9, fc="#edf7f3", ec="#2f9e7e")

    box(ax, (1.25, 1.05), "E3G rising\nWindow approaching", width=2.0, height=0.68, fc="#edf7f3", ec="#2f9e7e")
    box(ax, (3.55, 0.65), "LH surge\nOvulation likely 24-48h", width=2.25, height=0.68, fc="#fff4e6", ec="#f59f00")
    box(ax, (6.2, 0.65), "After LH\nAwait PdG", width=2.0, height=0.68, fc="#fff8db", ec="#ffd43b")
    box(ax, (8.7, 1.05), "PdG rise\nConfirm after event", width=2.0, height=0.68, fc="#eef4ff", ec="#4e79d9")

    arrow(ax, (5, 8.03), (5, 7.72))
    arrow(ax, (5, 6.98), (5, 6.62))
    arrow(ax, (4.25, 5.85), (2.9, 5.45))
    arrow(ax, (5.75, 5.85), (7.1, 5.45))
    arrow(ax, (2.4, 4.75), (4.45, 4.2))
    arrow(ax, (7.6, 4.75), (5.55, 4.2))
    arrow(ax, (4.25, 3.55), (2.8, 3.05))
    arrow(ax, (5.75, 3.55), (7.2, 3.05))
    arrow(ax, (7.6, 2.33), (5.55, 1.96))
    arrow(ax, (2.4, 2.33), (4.45, 1.96))

    fig.tight_layout()
    fig.savefig(OUT, dpi=180, bbox_inches="tight")
    print(OUT)


if __name__ == "__main__":
    main()
