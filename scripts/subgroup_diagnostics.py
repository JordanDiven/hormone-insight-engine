"""Subgroup and data-maturity diagnostics for PCOS-pattern analysis."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"


def safe_auc(y: pd.Series, score: pd.Series) -> float:
    if y.nunique() < 2:
        return float("nan")
    return float(roc_auc_score(y, score))


def safe_ap(y: pd.Series, score: pd.Series) -> float:
    if y.nunique() < 2:
        return float("nan")
    return float(average_precision_score(y, score))


def summarize_group(df: pd.DataFrame, group_name: str, group_value: str) -> dict[str, float | str]:
    y = df["pcos_label"].astype(int)
    score = df["loou_score"].astype(float)
    threshold = 0.5
    pred = (score >= threshold).astype(int)
    positives = int(y.sum())
    negatives = int((1 - y).sum())
    return {
        "subgroup": group_name,
        "level": group_value,
        "users": len(df),
        "pcos_users": positives,
        "no_pcos_users": negatives,
        "mean_score": float(score.mean()),
        "roc_auc": safe_auc(y, score),
        "average_precision": safe_ap(y, score),
        "accuracy_at_0_5": float((pred == y).mean()),
        "sensitivity_at_0_5": float(((pred == 1) & (y == 1)).sum() / positives) if positives else float("nan"),
        "specificity_at_0_5": float(((pred == 0) & (y == 0)).sum() / negatives) if negatives else float("nan"),
    }


def main() -> None:
    df = pd.read_csv(ASSET_DIR / "pcos_user_scores.csv")

    # Data maturity: how much longitudinal cycle history does each user have?
    df["cycle_history_group"] = pd.cut(
        df["n_cycles"],
        bins=[-np.inf, 2, 3, np.inf],
        labels=["1-2 cycles", "3 cycles", "4+ cycles"],
    )

    # Hormone engagement/data sufficiency: tertiles avoid overfitting thresholds.
    df["hormone_testing_density_group"] = pd.qcut(
        df["hormone_test_days_per_cycle"],
        q=3,
        labels=["lower testing density", "middle testing density", "higher testing density"],
        duplicates="drop",
    )

    df["diary_engagement_group"] = pd.cut(
        df["n_mood_rows"].fillna(0) + df["n_symptom_rows"].fillna(0),
        bins=[-np.inf, 0, 10, np.inf],
        labels=["no diary logs", "1-10 diary logs", "11+ diary logs"],
    )

    rows = []
    for col in ["cycle_history_group", "hormone_testing_density_group", "diary_engagement_group"]:
        for level, sub in df.groupby(col, observed=True):
            rows.append(summarize_group(sub, col, str(level)))

    out_path = ASSET_DIR / "subgroup_diagnostics.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
