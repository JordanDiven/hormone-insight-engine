"""Create a representative hormone user-journey chart for ovulation-window analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from ovulation_window_model import ASSETS, cycle_hormones, detect_hormone_columns, load_data


def main(presentation: bool = False):
    ASSETS.mkdir(exist_ok=True)
    cycles, hormones = load_data()
    hormone_cols = detect_hormone_columns(hormones)

    cycle_key = "HUB-3F12AD24214003__8"
    hub_id, cycle_index = cycle_key.rsplit("__", 1)
    row = cycles[
        (cycles["hub_id"] == hub_id)
        & (cycles["Cycle Index"].astype(str) == cycle_index)
    ].iloc[0]
    h = cycle_hormones(row, hormones)
    daily = pd.read_csv(ASSETS / "prospective_daily_states.csv", parse_dates=["date"])
    states = daily[
        (daily["cycle_key"] == cycle_key)
        & (daily["method"] == "cycle_plus_hormones")
    ].copy()

    ov_day = int((row["Ovulation Date"].normalize() - row["Period Start Date"].normalize()).days + 1)
    fertile_start = ov_day - 5
    fertile_end = ov_day

    if presentation:
        plt.rcParams.update(
            {
                "font.size": 12,
                "axes.labelsize": 13,
                "xtick.labelsize": 11,
                "ytick.labelsize": 11,
            }
        )

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(13.33, 7.5) if presentation else (11, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [1.1, 1.1, 1.1, 0.65]},
    )
    fig.patch.set_facecolor("white")

    series = [
        ("E3G", hormone_cols["e3g"], "#2f9e7e", axes[0]),
        ("LH", hormone_cols["lh"], "#d9480f", axes[1]),
        ("PdG", hormone_cols["pdg"], "#4263eb", axes[2]),
    ]

    e3g_for_threshold = h.dropna(subset=[hormone_cols["e3g"]]).copy()
    e3g_for_threshold = e3g_for_threshold[
        (e3g_for_threshold["cycle_day"] >= 4) & (e3g_for_threshold["cycle_day"] <= 25)
    ]
    early_e3g = e3g_for_threshold[
        e3g_for_threshold["cycle_day"] <= max(6, e3g_for_threshold["cycle_day"].min() + 2)
    ]
    e3g_baseline = float(early_e3g[hormone_cols["e3g"]].median()) if not early_e3g.empty else float(e3g_for_threshold[hormone_cols["e3g"]].median())
    e3g_rise_threshold = 1.5 * e3g_baseline

    for label, col, color, ax in series:
        plot_df = h.dropna(subset=[col]).copy()
        ax.axvspan(fertile_start, fertile_end, color="#e9f7ef", alpha=0.9, label="Reference fertile window")
        ax.axvline(ov_day, color="#101828", linestyle="--", linewidth=1.5, label="Annotated ovulation")
        ax.plot(plot_df["cycle_day"], plot_df[col], color=color, linewidth=2.8 if presentation else 2)
        ax.scatter(plot_df["cycle_day"], plot_df[col], color=color, s=34 if presentation else 22, zorder=3)
        ax.set_ylabel(label)
        ax.grid(axis="y", color="#e4e7ec", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)

    axes[0].axhline(e3g_rise_threshold, color="#2f9e7e", linestyle=":", linewidth=1.4)
    axes[0].text(
        27.5 if presentation else 34.5,
        e3g_rise_threshold,
        "E3G rise threshold\n1.5x early baseline",
        ha="right",
        va="bottom",
        fontsize=9.5 if presentation else 8,
        color="#2f9e7e",
    )
    axes[1].axhline(16, color="#d9480f", linestyle=":", linewidth=1.4)
    axes[1].text(
        27.5 if presentation else 34.5,
        16,
        "LH absolute threshold 16\nor >=2.5x baseline and >=10",
        ha="right",
        va="bottom",
        fontsize=9.5 if presentation else 8,
        color="#d9480f",
    )
    axes[2].axhline(10, color="#4263eb", linestyle=":", linewidth=1.4)
    axes[2].text(
        27.5 if presentation else 34.5,
        10,
        "PdG confirmation threshold 10",
        ha="right",
        va="bottom",
        fontsize=9.5 if presentation else 8,
        color="#4263eb",
    )

    state_colors = {
        "prior_only": "#d0d5dd",
        "e3g_rising": "#7bc8a4",
        "lh_surge_24_48h": "#f59f00",
        "post_lh_waiting_pdg": "#9b5de5",
        "pdg_confirmation": "#91a7ff",
        "no_confident_call": "#ff8787",
    }
    state_labels = {
        "prior_only": "Prior only",
        "e3g_rising": "E3G rising",
        "lh_surge_24_48h": "LH: ovulation likely 24-48h",
        "post_lh_waiting_pdg": "After LH: awaiting PdG",
        "pdg_confirmation": "PdG confirmation",
        "no_confident_call": "No confident call",
    }
    ax = axes[3]
    for _, s in states.iterrows():
        x = int(s["cycle_day"])
        state = s["state"]
        ax.barh(
            y=0,
            width=0.9,
            left=x - 0.45,
            height=0.5,
            color=state_colors.get(state, "#d0d5dd"),
            edgecolor="white",
        )
    ax.axvspan(fertile_start, fertile_end, color="#e9f7ef", alpha=0.9)
    ax.axvline(ov_day, color="#101828", linestyle="--", linewidth=1.5)
    ax.set_yticks([])
    ax.set_ylabel("App state")
    ax.set_xlabel("" if presentation else "Cycle day")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.set_ylim(-0.6, 0.6)

    handles = [
        plt.Line2D([0], [0], color="#e9f7ef", linewidth=8, label="Reference fertile window"),
        plt.Line2D([0], [0], color="#101828", linestyle="--", label="Annotated ovulation"),
    ]
    for state, color in state_colors.items():
        if state in set(states["state"]):
            handles.append(plt.Rectangle((0, 0), 1, 1, color=color, label=state_labels[state]))

    if not presentation:
        fig.suptitle(
            "Example user journey: hormones and daily app states",
            x=0.02,
            y=0.985,
            ha="left",
            fontsize=16,
            fontweight="bold",
        )
        fig.text(
            0.02,
            0.945,
            f"{cycle_key}: annotated ovulation on cycle day {ov_day}. Dotted lines show prototype rule thresholds.",
            fontsize=10,
            color="#475467",
        )
    axes[0].legend(handles=handles[:2], loc="upper right", frameon=False, fontsize=11 if presentation else 9)
    axes[3].legend(
        handles=handles[2:],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.28 if presentation else -0.5),
        ncol=5 if presentation else 3,
        frameon=False,
        fontsize=10 if presentation else 8,
    )
    axes[3].set_xlim(1, max(28, min(35, int(h["cycle_day"].max()))))

    fig.tight_layout(rect=[0.02, 0.13, 0.98, 0.98] if presentation else [0, 0.08, 1, 0.92])
    out = ASSETS / (
        "hormone_user_journey_presentation.png"
        if presentation
        else "hormone_user_journey.png"
    )
    fig.savefig(out, dpi=200 if presentation else 180, bbox_inches="tight", pad_inches=0.08 if presentation else 0.1)
    print(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentation", action="store_true")
    args = parser.parse_args()
    main(presentation=args.presentation)
