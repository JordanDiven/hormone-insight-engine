"""First-cycle-only cold-start simulation for PCOS-pattern analysis.

This rebuilds the user-level feature table using only each user's first observed
cycle and hormone/diary rows within that first-cycle window. It then reruns the
same transparent leave-one-user-out resemblance scoring used in the primary
analysis.

The goal is to answer: how much performance remains if the score is attempted
after only one observed cycle?
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import pcos_pattern_analysis as base


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"

CORE_FEATURES = [
    "cycle_length_mean",
    "cycle_length_sd",
    "cycle_length_cv",
    "cycle_length_max",
    "prop_cycles_gt35",
    "lh_median",
    "lh_max",
    "lh_peak_to_median",
    "prop_lh_over_16",
    "e3g_median",
    "e3g_max",
    "pdg_median",
    "pdg_max",
    "prop_pdg_over_5",
    "prop_pdg_over_10",
    "fsh_median",
]


def date_value(row: dict[str, str], key: str):
    parsed = base.parse_excel_date(row.get(key, ""))
    return parsed.date() if parsed else None


def first_cycle_rows(cycle_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], Any, Any]:
    dated = []
    for row in cycle_rows:
        start = date_value(row, "Period Start Date")
        if start:
            dated.append((start, row))
    if not dated:
        return [], None, None
    dated.sort(key=lambda item: item[0])
    first_start, first = dated[0]
    first_end = date_value(first, "Period End Date")
    next_start = dated[1][0] if len(dated) > 1 else None
    window_end = next_start or first_end
    return [first], first_start, window_end


def within_window(row: dict[str, str], date_key: str, start, end) -> bool:
    if start is None:
        return False
    dt = date_value(row, date_key)
    if dt is None:
        return False
    if dt < start:
        return False
    if end is not None and dt >= end:
        return False
    return True


def truncate_sheets_to_first_cycle(path: Path, reader) -> dict[str, list[dict[str, str]]]:
    sheets = reader(path)
    cycles_by_hub = base.group_by_hub(sheets["CycleData_Sheet"])
    first_cycles = []
    windows = {}
    for hub, rows in cycles_by_hub.items():
        first, start, end = first_cycle_rows(rows)
        first_cycles.extend(first)
        windows[hub] = (start, end)

    truncated = dict(sheets)
    truncated["CycleData_Sheet"] = first_cycles

    def filter_rows(sheet_name: str, date_key: str) -> list[dict[str, str]]:
        out = []
        for row in sheets[sheet_name]:
            hub = row.get("hub_id", "")
            start, end = windows.get(hub, (None, None))
            if within_window(row, date_key, start, end):
                out.append(row)
        return out

    truncated["Hormone_Sheet"] = filter_rows("Hormone_Sheet", "Test Time")
    truncated["Diary_Mood_Sheet"] = filter_rows("Diary_Mood_Sheet", "Log Date")
    truncated["Diary_Symptoms_Sheet"] = filter_rows("Diary_Symptoms_Sheet", "Log Date")
    truncated["Diary_Pregnant_Sheet"] = filter_rows("Diary_Pregnant_Sheet", "Log Date")
    return truncated


def build_first_cycle_features(path: Path, label: int) -> list[dict[str, Any]]:
    original_read_xlsx = base.read_xlsx
    try:
        base.read_xlsx = lambda _: truncate_sheets_to_first_cycle(path, original_read_xlsx)
        return base.build_user_features(path, label)
    finally:
        base.read_xlsx = original_read_xlsx


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_first_cycle_features(base.PCOS_FILE, 1) + build_first_cycle_features(base.NO_PCOS_FILE, 0)
    rows = sorted(rows, key=lambda row: (row["pcos_label"], row["hub_id"]))
    write_csv(ASSET_DIR / "cold_start_user_features.csv", rows)

    selected = [feature for feature in CORE_FEATURES if feature in rows[0]]
    # Features with no variation after one-cycle truncation cannot help and can
    # make scaling brittle.
    usable = []
    for feature in selected:
        values = [base.to_float(row.get(feature)) for row in rows]
        values = [v for v in values if v is not None and not math.isnan(v)]
        if len(set(round(v, 8) for v in values)) > 1:
            usable.append(feature)

    result = base.leave_one_user_out(rows, usable)
    scored = []
    for row, score in zip(result.rows, result.scores):
        out = dict(row)
        out["loou_score"] = score
        scored.append(out)
    write_csv(ASSET_DIR / "cold_start_user_scores.csv", scored)

    metrics = {
        "analysis": "first_cycle_only",
        "users": len(rows),
        "features_used": len(usable),
        "loou_roc_auc": base.rank_auc(result.labels, result.scores),
        "loou_average_precision": base.average_precision(result.labels, result.scores),
        "median_cycle_rows_per_user": 1.0,
        "mean_hormone_rows_per_user": sum(row["n_hormone_rows"] for row in rows) / len(rows),
        "features": ";".join(usable),
    }
    write_csv(ASSET_DIR / "cold_start_metrics.csv", [metrics])
    print(metrics)


if __name__ == "__main__":
    main()
