"""User-level bootstrap confidence intervals for PCOS-pattern analysis held-out scores."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"


def metrics(y: np.ndarray, scores: np.ndarray) -> dict[str, float]:
    threshold = float(np.median(scores))
    pred = (scores >= threshold).astype(int)
    positives = y == 1
    negatives = y == 0
    out = {
        "roc_auc": roc_auc_score(y, scores) if len(np.unique(y)) == 2 else np.nan,
        "average_precision": average_precision_score(y, scores) if len(np.unique(y)) == 2 else np.nan,
        "sensitivity": ((pred == 1) & positives).sum() / positives.sum() if positives.sum() else np.nan,
        "specificity": ((pred == 0) & negatives).sum() / negatives.sum() if negatives.sum() else np.nan,
        "accuracy": (pred == y).mean(),
    }
    return {key: float(value) for key, value in out.items()}


def bootstrap_ci(df: pd.DataFrame, score_col: str, seed: int = 17, n_boot: int = 1000) -> list[dict[str, float | str]]:
    rng = np.random.default_rng(seed)
    y = df["pcos_label"].astype(int).to_numpy()
    scores = df[score_col].astype(float).to_numpy()
    point = metrics(y, scores)

    samples: dict[str, list[float]] = {key: [] for key in point}
    n = len(df)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        sample_y = y[idx]
        sample_scores = scores[idx]
        if len(np.unique(sample_y)) < 2:
            continue
        sample_metrics = metrics(sample_y, sample_scores)
        for key, value in sample_metrics.items():
            if not np.isnan(value):
                samples[key].append(value)

    rows = []
    for key, value in point.items():
        values = np.array(samples[key], dtype=float)
        rows.append(
            {
                "metric": key,
                "point_estimate": value,
                "ci_lower_95": float(np.quantile(values, 0.025)),
                "ci_upper_95": float(np.quantile(values, 0.975)),
                "bootstrap_replicates": len(values),
            }
        )
    return rows


def main() -> None:
    analyses = [
        ("full_history_primary", ASSET_DIR / "pcos_user_scores.csv", "loou_score"),
        ("first_cycle_only", ASSET_DIR / "cold_start_user_scores.csv", "loou_score"),
    ]
    all_rows = []
    for name, path, score_col in analyses:
        df = pd.read_csv(path)
        for row in bootstrap_ci(df, score_col):
            row["analysis"] = name
            all_rows.append(row)

    fieldnames = ["analysis", "metric", "point_estimate", "ci_lower_95", "ci_upper_95", "bootstrap_replicates"]
    out_path = ASSET_DIR / "bootstrap_uncertainty.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(pd.DataFrame(all_rows).to_string(index=False))


if __name__ == "__main__":
    main()
