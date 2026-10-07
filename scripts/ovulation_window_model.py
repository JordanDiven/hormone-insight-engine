"""ovulation-window analysis ovulation and fertile-window prototype.

Uses NO_PCOS_DATA only. Compares three increasingly informed estimators:

1. Generic cycle prior: ovulation on cycle day 14.
2. Period-history model: manual period inputs only, no hormones.
3. Hormone-updated model: period-history prior updated by LH, E3G, and PdG.

Workbook ovulation annotations are used as retrospective reference labels, not
clinical ground truth.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "reference_pattern_cohort.xlsx"
ASSETS = ROOT / "assets"


@dataclass
class Prediction:
    method: str
    pred_date: pd.Timestamp
    interval_start: pd.Timestamp
    interval_end: pd.Timestamp
    confidence: str
    evidence: str


def parse_list(value):
    if pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = ast.literal_eval(str(value))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def detect_hormone_columns(hormones: pd.DataFrame) -> dict[str, str]:
    """Avoid depending on exact Unicode punctuation in workbook column names."""
    return {
        "e3g": next(c for c in hormones.columns if c.startswith("E3G")),
        "lh": next(c for c in hormones.columns if c.startswith("LH")),
        "pdg": next(c for c in hormones.columns if c.startswith("PDG")),
    }


def load_data():
    cycles = pd.read_excel(DATA, sheet_name="CycleData_Sheet")
    hormones = pd.read_excel(DATA, sheet_name="Hormone_Sheet")

    for col in ["Period Start Date", "Period End Date", "Ovulation Date", "LH Surge Time"]:
        cycles[col] = pd.to_datetime(cycles[col], errors="coerce")

    hormones["Test Time"] = pd.to_datetime(hormones["Test Time"], errors="coerce")
    hormones["test_date"] = hormones["Test Time"].dt.normalize()

    cycles = cycles.sort_values(["hub_id", "Period Start Date"]).reset_index(drop=True)
    cycles["next_period_start"] = cycles.groupby("hub_id")["Period Start Date"].shift(-1)
    cycles["cycle_end_exclusive"] = cycles["next_period_start"]
    missing_end = cycles["cycle_end_exclusive"].isna()
    cycles.loc[missing_end, "cycle_end_exclusive"] = (
        cycles.loc[missing_end, "Period Start Date"]
        + pd.to_timedelta(cycles.loc[missing_end, "Cycle Length (days)"], unit="D")
    )
    cycles["annotated_ovulation_day"] = (
        cycles["Ovulation Date"] - cycles["Period Start Date"]
    ).dt.days + 1
    cycles["pdg_rise_dates"] = cycles["date_PDG_rise"].apply(parse_list)

    return cycles, hormones


def cycle_hormones(row, hormones):
    mask = (
        (hormones["hub_id"] == row["hub_id"])
        & (hormones["Test Time"] >= row["Period Start Date"])
        & (hormones["Test Time"] < row["cycle_end_exclusive"])
    )
    out = hormones.loc[mask].copy()
    out["cycle_day"] = (out["test_date"] - row["Period Start Date"].normalize()).dt.days + 1
    return out.sort_values("Test Time")


def previous_cycle_lengths(cycles, row):
    same_user = cycles[
        (cycles["hub_id"] == row["hub_id"])
        & (cycles["Period Start Date"] < row["Period Start Date"])
    ].copy()
    return same_user["Cycle Length (days)"].dropna().astype(float).tolist()


def date_from_cycle_day(row, cycle_day):
    bounded = int(round(max(1, cycle_day)))
    return row["Period Start Date"].normalize() + pd.Timedelta(days=bounded - 1)


def interval(pred_date, half_width_days):
    half_width_days = int(round(half_width_days))
    return pred_date - pd.Timedelta(days=half_width_days), pred_date + pd.Timedelta(days=half_width_days)


def generic_cycle_prediction(row):
    pred = date_from_cycle_day(row, 14)
    lo, hi = interval(pred, 2)
    return Prediction(
        method="generic_cycle_day_14",
        pred_date=pred,
        interval_start=lo,
        interval_end=hi,
        confidence="low",
        evidence="Generic cycle-day-14 prior using current period start only.",
    )


def period_history_prediction(row, cycles):
    prior_lengths = previous_cycle_lengths(cycles, row)
    if len(prior_lengths) == 0:
        expected_len = 28.0
        half_width = 4
        evidence = "No prior cycles for this user; used generic 28-day cycle prior."
    else:
        expected_len = float(np.median(prior_lengths))
        variability = float(np.std(prior_lengths, ddof=1)) if len(prior_lengths) > 1 else 3.0
        half_width = int(max(2, min(6, round(variability))))
        evidence = f"Used prior period history: median prior cycle length {expected_len:.1f} days."

    predicted_ov_day = max(8, min(25, expected_len - 14))
    pred = date_from_cycle_day(row, predicted_ov_day)
    lo, hi = interval(pred, half_width)
    confidence = "moderate" if len(prior_lengths) >= 2 and half_width <= 3 else "low"
    return Prediction(
        method="period_history_only",
        pred_date=pred,
        interval_start=lo,
        interval_end=hi,
        confidence=confidence,
        evidence=evidence,
    )


def hormone_prediction(row, cycles, h, hormone_cols):
    prior = period_history_prediction(row, cycles)
    if h.empty:
        return Prediction(
            method="hormone_updated",
            pred_date=prior.pred_date,
            interval_start=prior.interval_start,
            interval_end=prior.interval_end,
            confidence="low",
            evidence="No hormone tests in cycle; fell back to period-history estimate.",
        )

    lh_col = hormone_cols["lh"]
    e3g_col = hormone_cols["e3g"]
    pdg_col = hormone_cols["pdg"]
    lh = h.dropna(subset=[lh_col]).copy()
    e3g = h.dropna(subset=[e3g_col]).copy()
    pdg = h.dropna(subset=[pdg_col]).copy()

    # LH is the strongest near-term signal for ovulation timing. For a product
    # predictor, do not select the largest LH value anywhere in a long or stale
    # cycle record. Restrict to the biologically plausible peri-ovulatory search
    # window and use the first plausible surge.
    if not lh.empty:
        lh_search = lh[(lh["cycle_day"] >= 6) & (lh["cycle_day"] <= 25)].copy()
        if not lh_search.empty:
            baseline = float(np.nanpercentile(lh_search[lh_col].astype(float), 25))
            lh_search["is_surge"] = (
                (lh_search[lh_col].astype(float) >= 16)
                | (
                    (baseline > 0)
                    & (lh_search[lh_col].astype(float) >= 2.5 * baseline)
                    & (lh_search[lh_col].astype(float) >= 10)
                )
            )
            candidates = lh_search[lh_search["is_surge"]].sort_values("Test Time")
        else:
            candidates = pd.DataFrame()
        if not candidates.empty:
            surge_row = candidates.iloc[0]
            surge_value = float(surge_row[lh_col])
            pred = surge_row["test_date"] + pd.Timedelta(days=1)
            lo = surge_row["test_date"]
            hi = surge_row["test_date"] + pd.Timedelta(days=2)
            post_pdg = pdg[pdg["test_date"] > surge_row["test_date"]]
            pdg_support = bool((post_pdg[pdg_col].astype(float) >= 5).any()) if not post_pdg.empty else False
            confidence = "high" if pdg_support else "moderate"
            evidence = (
                f"LH surge detected: LH {surge_value:.1f} on cycle day {int(surge_row['cycle_day'])}; "
                + ("later PdG elevation supports ovulation confirmation." if pdg_support else "PdG confirmation not yet observed.")
            )
            return Prediction("hormone_updated", pred, lo, hi, confidence, evidence)

    # E3G rise is useful earlier in the fertile window but less precise than LH.
    if len(e3g) >= 3:
        e3g = e3g.sort_values("Test Time")
        e3g = e3g[(e3g["cycle_day"] >= 4) & (e3g["cycle_day"] <= 25)].copy()
    if len(e3g) >= 3:
        early = e3g[e3g["cycle_day"] <= max(6, e3g["cycle_day"].min() + 2)]
        baseline = float(early[e3g_col].median()) if not early.empty else float(e3g[e3g_col].median())
        e3g["ratio_to_baseline"] = e3g[e3g_col].astype(float) / max(baseline, 1.0)
        rise = e3g[e3g["ratio_to_baseline"] >= 1.5]
        if not rise.empty:
            first_rise = rise.iloc[0]
            pred = first_rise["test_date"] + pd.Timedelta(days=3)
            lo = first_rise["test_date"] + pd.Timedelta(days=1)
            hi = first_rise["test_date"] + pd.Timedelta(days=5)
            return Prediction(
                "hormone_updated",
                pred,
                lo,
                hi,
                "moderate",
                f"E3G rise detected on cycle day {int(first_rise['cycle_day'])}; LH surge not detected, so interval remains wider.",
            )

    # PdG alone is retrospective: it helps confirm that ovulation probably occurred.
    if not pdg.empty and (pdg[pdg_col].astype(float) >= 10).any():
        first = pdg[pdg[pdg_col].astype(float) >= 10].iloc[0]
        pred = first["test_date"] - pd.Timedelta(days=4)
        lo = first["test_date"] - pd.Timedelta(days=6)
        hi = first["test_date"] - pd.Timedelta(days=2)
        return Prediction(
            "hormone_updated",
            pred,
            lo,
            hi,
            "low",
            f"PdG elevation observed on cycle day {int(first['cycle_day'])}; used retrospective estimate.",
        )

    return Prediction(
        method="hormone_updated",
        pred_date=prior.pred_date,
        interval_start=prior.interval_start,
        interval_end=prior.interval_end,
        confidence="low",
        evidence="No clear LH surge, E3G rise, or PdG confirmation; fell back to period-history estimate.",
    )


def evaluate(pred_rows):
    df = pd.DataFrame(pred_rows)
    df["abs_error_days"] = (df["pred_date"] - df["reference_ovulation_date"]).abs().dt.days
    df["signed_error_days"] = (df["pred_date"] - df["reference_ovulation_date"]).dt.days
    df["interval_width_days"] = (df["interval_end"] - df["interval_start"]).dt.days + 1
    df["covered_by_interval"] = (
        (df["reference_ovulation_date"] >= df["interval_start"])
        & (df["reference_ovulation_date"] <= df["interval_end"])
    )
    df["within_1_day"] = df["abs_error_days"] <= 1
    df["within_2_days"] = df["abs_error_days"] <= 2

    summary = (
        df.groupby("method")
        .agg(
            cycles=("cycle_key", "count"),
            median_abs_error_days=("abs_error_days", "median"),
            mean_abs_error_days=("abs_error_days", "mean"),
            within_1_day=("within_1_day", "mean"),
            within_2_days=("within_2_days", "mean"),
            interval_coverage=("covered_by_interval", "mean"),
            mean_interval_width_days=("interval_width_days", "mean"),
            high_confidence_share=("confidence", lambda s: (s == "high").mean()),
            moderate_or_high_confidence_share=("confidence", lambda s: s.isin(["moderate", "high"]).mean()),
        )
        .reset_index()
    )
    return df, summary


def add_relative_lift(summary):
    base = summary.set_index("method").loc["generic_cycle_day_14"]
    out = summary.copy()
    out["mean_abs_error_reduction_vs_generic_days"] = base["mean_abs_error_days"] - out["mean_abs_error_days"]
    out["within_1_day_lift_vs_generic"] = out["within_1_day"] - base["within_1_day"]
    out["within_2_day_lift_vs_generic"] = out["within_2_days"] - base["within_2_days"]
    return out


def main():
    ASSETS.mkdir(exist_ok=True)
    cycles, hormones = load_data()
    hormone_cols = detect_hormone_columns(hormones)
    status_col = next(c for c in cycles.columns if c.startswith("Cycle Status"))
    eval_cycles = cycles[
        cycles["Period Start Date"].notna()
        & cycles["Ovulation Date"].notna()
        & (cycles[status_col] == 1)
    ].copy()

    pred_rows = []
    cycle_examples = []
    for _, row in eval_cycles.iterrows():
        h = cycle_hormones(row, hormones)
        preds = [
            generic_cycle_prediction(row),
            period_history_prediction(row, cycles),
            hormone_prediction(row, cycles, h, hormone_cols),
        ]
        cycle_key = f"{row['hub_id']}__{row['Cycle Index']}"
        for pred in preds:
            pred_rows.append(
                {
                    "cycle_key": cycle_key,
                    "hub_id": row["hub_id"],
                    "cycle_index": row["Cycle Index"],
                    "method": pred.method,
                    "reference_ovulation_date": row["Ovulation Date"].normalize(),
                    "reference_ovulation_day": row["annotated_ovulation_day"],
                    "pred_date": pred.pred_date,
                    "interval_start": pred.interval_start,
                    "interval_end": pred.interval_end,
                    "confidence": pred.confidence,
                    "evidence": pred.evidence,
                    "hormone_tests_in_cycle": len(h),
                    "lh_tests_in_cycle": h[hormone_cols["lh"]].notna().sum() if not h.empty else 0,
                    "e3g_tests_in_cycle": h[hormone_cols["e3g"]].notna().sum() if not h.empty else 0,
                    "pdg_tests_in_cycle": h[hormone_cols["pdg"]].notna().sum() if not h.empty else 0,
                }
            )
        if len(h) >= 20:
            hp = preds[-1]
            cycle_examples.append(
                {
                    "cycle_key": cycle_key,
                    "hub_id": row["hub_id"],
                    "cycle_index": row["Cycle Index"],
                    "period_start": row["Period Start Date"].date(),
                    "reference_ovulation": row["Ovulation Date"].date(),
                    "hormone_prediction": hp.pred_date.date(),
                    "prediction_interval": f"{hp.interval_start.date()} to {hp.interval_end.date()}",
                    "confidence": hp.confidence,
                    "evidence": hp.evidence,
                    "hormone_tests": len(h),
                }
            )

    predictions, summary = evaluate(pred_rows)
    summary = add_relative_lift(summary)
    predictions.to_csv(ASSETS / "ovulation_predictions.csv", index=False)
    summary.to_csv(ASSETS / "ovulation_method_metrics.csv", index=False)
    pd.DataFrame(cycle_examples).head(10).to_csv(ASSETS / "ovulation_cycle_examples.csv", index=False)

    hormone = predictions[predictions["method"] == "hormone_updated"].copy()
    conf = (
        hormone.groupby("confidence")
        .agg(
            cycles=("cycle_key", "count"),
            median_abs_error_days=("abs_error_days", "median"),
            mean_abs_error_days=("abs_error_days", "mean"),
            within_1_day=("within_1_day", "mean"),
            within_2_days=("within_2_days", "mean"),
            interval_coverage=("covered_by_interval", "mean"),
            mean_interval_width_days=("interval_width_days", "mean"),
        )
        .reset_index()
    )
    conf.to_csv(ASSETS / "hormone_confidence_metrics.csv", index=False)

    print("Evaluation cycles:", len(eval_cycles))
    print(summary.to_string(index=False))
    print("\nHormone confidence strata:")
    print(conf.to_string(index=False))


if __name__ == "__main__":
    main()
