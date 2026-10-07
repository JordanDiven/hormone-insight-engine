"""Prospective daily fertile-window simulation for ovulation-window analysis.

This script evaluates the product-style question: on each cycle day, using only
data available up to that day, what state would the app have shown?
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ovulation_window_model import (
    DATA,
    ASSETS,
    cycle_hormones,
    detect_hormone_columns,
    load_data,
    period_history_prediction,
)


def daily_state(row, cycles, h_to_date, hormone_cols, current_date):
    prior = period_history_prediction(row, cycles)
    cycle_day = (current_date - row["Period Start Date"].normalize()).days + 1

    if h_to_date.empty:
        return {
            "state": "prior_only",
            "confidence": "low",
            "message_class": "calendar_guidance",
            "evidence": "No hormone tests available up to this day.",
            "window_start": prior.interval_start,
            "window_end": prior.interval_end,
            "ovulation_window_start": prior.interval_start,
            "ovulation_window_end": prior.interval_end,
            "fertile_window_start": prior.interval_start - pd.Timedelta(days=5),
            "fertile_window_end": prior.interval_end,
        }

    lh_col = hormone_cols["lh"]
    e3g_col = hormone_cols["e3g"]
    pdg_col = hormone_cols["pdg"]

    lh = h_to_date.dropna(subset=[lh_col]).copy()
    e3g = h_to_date.dropna(subset=[e3g_col]).copy()
    pdg = h_to_date.dropna(subset=[pdg_col]).copy()

    # PdG is confirmation only, and should not create a forward-looking fertile
    # window call. It has priority once visible because it changes the product
    # state to "likely occurred".
    if not pdg.empty and (pdg[pdg_col].astype(float) >= 10).any():
        first = pdg[pdg[pdg_col].astype(float) >= 10].iloc[0]
        return {
            "state": "pdg_confirmation",
            "confidence": "moderate",
            "message_class": "ovulation_likely_occurred",
            "evidence": f"PdG >= 10 observed by cycle day {int(first['cycle_day'])}.",
            "window_start": first["test_date"] - pd.Timedelta(days=6),
            "window_end": first["test_date"] - pd.Timedelta(days=2),
            "ovulation_window_start": first["test_date"] - pd.Timedelta(days=6),
            "ovulation_window_end": first["test_date"] - pd.Timedelta(days=2),
            "fertile_window_start": first["test_date"] - pd.Timedelta(days=11),
            "fertile_window_end": first["test_date"] - pd.Timedelta(days=2),
        }

    # LH is the actionable near-term signal. Use only values observed up to the
    # current day and keep the message active for the surge day and next day.
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
            if not candidates.empty:
                surge = candidates.iloc[0]
                if current_date <= surge["test_date"] + pd.Timedelta(days=1):
                    return {
                        "state": "lh_surge_24_48h",
                        "confidence": "high",
                        "message_class": "ovulation_likely_24_48h",
                        "evidence": f"LH surge detected by cycle day {int(surge['cycle_day'])}.",
                        "window_start": surge["test_date"],
                        "window_end": surge["test_date"] + pd.Timedelta(days=2),
                        "ovulation_window_start": surge["test_date"],
                        "ovulation_window_end": surge["test_date"] + pd.Timedelta(days=2),
                        "fertile_window_start": surge["test_date"] - pd.Timedelta(days=5),
                        "fertile_window_end": surge["test_date"] + pd.Timedelta(days=2),
                    }
                return {
                    "state": "post_lh_waiting_pdg",
                    "confidence": "moderate",
                    "message_class": "awaiting_ovulation_confirmation",
                    "evidence": f"LH surge detected by cycle day {int(surge['cycle_day'])}; awaiting PdG confirmation.",
                    "window_start": surge["test_date"],
                    "window_end": surge["test_date"] + pd.Timedelta(days=2),
                    "ovulation_window_start": surge["test_date"],
                    "ovulation_window_end": surge["test_date"] + pd.Timedelta(days=2),
                    "fertile_window_start": surge["test_date"] - pd.Timedelta(days=5),
                    "fertile_window_end": surge["test_date"] + pd.Timedelta(days=2),
                }

    # E3G is earlier and less precise. It can indicate the fertile window is
    # approaching before the LH surge is visible.
    if len(e3g) >= 3:
        e3g = e3g.sort_values("Test Time")
        e3g = e3g[(e3g["cycle_day"] >= 4) & (e3g["cycle_day"] <= 25)].copy()
    if len(e3g) >= 3:
        early = e3g[e3g["cycle_day"] <= max(6, e3g["cycle_day"].min() + 2)]
        baseline = float(early[e3g_col].median()) if not early.empty else float(e3g[e3g_col].median())
        e3g["ratio_to_baseline"] = e3g[e3g_col].astype(float) / max(baseline, 1.0)
        rise = e3g[e3g["ratio_to_baseline"] >= 1.5]
        if not rise.empty:
            first = rise.iloc[0]
            if current_date <= first["test_date"] + pd.Timedelta(days=5):
                return {
                    "state": "e3g_rising",
                    "confidence": "moderate",
                    "message_class": "fertile_window_approaching",
                    "evidence": f"E3G rise detected by cycle day {int(first['cycle_day'])}.",
                    "window_start": first["test_date"] + pd.Timedelta(days=1),
                    "window_end": first["test_date"] + pd.Timedelta(days=5),
                    "ovulation_window_start": first["test_date"] + pd.Timedelta(days=1),
                    "ovulation_window_end": first["test_date"] + pd.Timedelta(days=5),
                    "fertile_window_start": first["test_date"],
                    "fertile_window_end": first["test_date"] + pd.Timedelta(days=5),
                }

    if cycle_day > 25:
        return {
            "state": "no_confident_call",
            "confidence": "low",
            "message_class": "no_call",
            "evidence": "No clear ovulatory hormone signal by late cycle.",
            "window_start": pd.NaT,
            "window_end": pd.NaT,
            "ovulation_window_start": pd.NaT,
            "ovulation_window_end": pd.NaT,
            "fertile_window_start": pd.NaT,
            "fertile_window_end": pd.NaT,
        }

    return {
        "state": "prior_only",
        "confidence": "low",
        "message_class": "calendar_guidance",
        "evidence": "No actionable hormone signal yet.",
        "window_start": prior.interval_start,
        "window_end": prior.interval_end,
        "ovulation_window_start": prior.interval_start,
        "ovulation_window_end": prior.interval_end,
        "fertile_window_start": prior.interval_start - pd.Timedelta(days=5),
        "fertile_window_end": prior.interval_end,
    }


def calendar_daily_state(row, current_date):
    cycle_day = (current_date - row["Period Start Date"].normalize()).days + 1
    fertile_window_start = row["Period Start Date"].normalize() + pd.Timedelta(days=8)
    fertile_window_end = row["Period Start Date"].normalize() + pd.Timedelta(days=13)
    ovulation_window_start = row["Period Start Date"].normalize() + pd.Timedelta(days=12)
    ovulation_window_end = row["Period Start Date"].normalize() + pd.Timedelta(days=14)
    if 9 <= cycle_day <= 14:
        return {
            "state": "calendar_window_open",
            "confidence": "low",
            "message_class": "fertile_window_approaching",
            "evidence": "Current day falls inside a generic cycle-day-9-to-14 fertile-window estimate.",
            "window_start": ovulation_window_start,
            "window_end": ovulation_window_end,
            "ovulation_window_start": ovulation_window_start,
            "ovulation_window_end": ovulation_window_end,
            "fertile_window_start": fertile_window_start,
            "fertile_window_end": fertile_window_end,
        }
    return {
        "state": "calendar_prior_only",
        "confidence": "low",
        "message_class": "calendar_guidance",
        "evidence": "Current day falls outside a generic cycle-day-9-to-14 fertile-window estimate.",
        "window_start": ovulation_window_start,
        "window_end": ovulation_window_end,
        "ovulation_window_start": ovulation_window_start,
        "ovulation_window_end": ovulation_window_end,
        "fertile_window_start": fertile_window_start,
        "fertile_window_end": fertile_window_end,
    }


def cycle_only_daily_state(row, cycles, current_date):
    prior = period_history_prediction(row, cycles)
    fertile_window_start = prior.interval_start - pd.Timedelta(days=5)
    fertile_window_end = prior.interval_end
    in_fertile_window = fertile_window_start <= current_date <= fertile_window_end
    if in_fertile_window:
        return {
            "state": "cycle_window_open",
            "confidence": prior.confidence,
            "message_class": "fertile_window_approaching",
            "evidence": "Current day falls inside the cycle-history fertile-window estimate.",
            "window_start": prior.interval_start,
            "window_end": prior.interval_end,
            "ovulation_window_start": prior.interval_start,
            "ovulation_window_end": prior.interval_end,
            "fertile_window_start": fertile_window_start,
            "fertile_window_end": fertile_window_end,
        }
    return {
        "state": "cycle_prior_only",
        "confidence": "low",
        "message_class": "calendar_guidance",
        "evidence": "Current day falls outside the cycle-history fertile-window estimate.",
        "window_start": prior.interval_start,
        "window_end": prior.interval_end,
        "ovulation_window_start": prior.interval_start,
        "ovulation_window_end": prior.interval_end,
        "fertile_window_start": fertile_window_start,
        "fertile_window_end": fertile_window_end,
    }


def safe_rate(mask):
    return float(mask.mean()) if len(mask) else np.nan


def summarise_method(daily, method):
    subset = daily[daily["method"] == method].copy()
    lh_alerts = subset[subset["lh_alert"]]
    first_actionable = (
        subset[subset["actionable_positive"]]
        .sort_values(["cycle_key", "date"])
        .groupby("cycle_key")
        .first()
        .reset_index()
    )
    return [
        {
            "method": method,
            "metric": "daily_rows",
            "value": len(subset),
            "interpretation": "Number of cycle-days evaluated with data frozen to that date.",
        },
        {
            "method": method,
            "metric": "cycles_evaluated",
            "value": subset["cycle_key"].nunique(),
            "interpretation": "Real cycles with ovulation annotation.",
        },
        {
            "method": method,
            "metric": "pre_ovulatory_fertile_day_sensitivity",
            "value": safe_rate(
                subset.loc[subset["pre_ovulatory_fertile_day_reference"], "actionable_positive"]
            ),
            "interpretation": "Share of actionable pre-ovulatory fertile days with an actionable app state.",
        },
        {
            "method": method,
            "metric": "non_fertile_day_specificity",
            "value": safe_rate(
                ~subset.loc[~subset["fertile_day_reference"], "actionable_positive"]
            ),
            "interpretation": "Share of non-fertile days not receiving an actionable fertile-window call.",
        },
        {
            "method": method,
            "metric": "actionable_call_ppv_pre_ov_fertile_day",
            "value": safe_rate(
                subset.loc[subset["actionable_positive"], "pre_ovulatory_fertile_day_reference"]
            ),
            "interpretation": "Share of actionable calls that occurred on annotated ovulation day or the five days before it.",
        },
        {
            "method": method,
            "metric": "lh_alert_count",
            "value": len(lh_alerts),
            "interpretation": "Daily states saying ovulation is likely in the next 24-48 hours.",
        },
        {
            "method": method,
            "metric": "lh_alert_ppv_0_to_2_days",
            "value": safe_rate(lh_alerts["days_to_ovulation"].between(0, 2)),
            "interpretation": "Share of LH alerts that occurred on ovulation day or 1-2 days before.",
        },
        {
            "method": method,
            "metric": "lh_alert_ppv_same_day",
            "value": safe_rate(lh_alerts["days_to_ovulation"].between(0, 0)),
            "interpretation": "Share of LH alerts where annotated ovulation was the same day.",
        },
        {
            "method": method,
            "metric": "lh_alert_ppv_0_to_1_days",
            "value": safe_rate(lh_alerts["days_to_ovulation"].between(0, 1)),
            "interpretation": "Share of LH alerts where annotated ovulation was 0-1 days away.",
        },
        {
            "method": method,
            "metric": "lh_alert_ppv_0_to_3_days",
            "value": safe_rate(lh_alerts["days_to_ovulation"].between(0, 3)),
            "interpretation": "Share of LH alerts where annotated ovulation was 0-3 days away.",
        },
        {
            "method": method,
            "metric": "lh_alert_ppv_minus_1_to_2_days",
            "value": safe_rate(lh_alerts["days_to_ovulation"].between(-1, 2)),
            "interpretation": "Share of LH alerts where annotated ovulation was -1 to +2 days away.",
        },
        {
            "method": method,
            "metric": "false_reassurance_rate_next_48h",
            "value": safe_rate(subset["false_reassurance_risk"]),
            "interpretation": "Share of all evaluated days with low/no call despite ovulation being 0-2 days away.",
        },
        {
            "method": method,
            "metric": "cycles_with_actionable_pre_ovulatory_guidance",
            "value": safe_rate(first_actionable["days_to_ovulation"] >= 0),
            "interpretation": "Among cycles with an actionable call, share where the first call occurred before or on ovulation day.",
        },
        {
            "method": method,
            "metric": "median_days_notice_first_actionable_call",
            "value": float(first_actionable["days_to_ovulation"].median()) if len(first_actionable) else np.nan,
            "interpretation": "Median lead time from first actionable call to annotated ovulation.",
        },
    ]


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

    rows = []
    for _, row in eval_cycles.iterrows():
        h = cycle_hormones(row, hormones)
        cycle_end = min(
            row["cycle_end_exclusive"].normalize() - pd.Timedelta(days=1),
            row["Ovulation Date"].normalize() + pd.Timedelta(days=5),
        )
        days = pd.date_range(row["Period Start Date"].normalize(), cycle_end, freq="D")
        for current_date in days:
            h_to_date = h[h["test_date"] <= current_date].copy()
            days_to_ovulation = (row["Ovulation Date"].normalize() - current_date).days
            fertile_day = -1 <= days_to_ovulation <= 5
            pre_ov_fertile_day = 0 <= days_to_ovulation <= 5
            base = {
                    "cycle_key": f"{row['hub_id']}__{row['Cycle Index']}",
                    "hub_id": row["hub_id"],
                    "cycle_index": row["Cycle Index"],
                    "date": current_date,
                    "cycle_day": (current_date - row["Period Start Date"].normalize()).days + 1,
                    "reference_ovulation_date": row["Ovulation Date"].normalize(),
                    "days_to_ovulation": days_to_ovulation,
                    "fertile_day_reference": fertile_day,
                    "pre_ovulatory_fertile_day_reference": pre_ov_fertile_day,
            }
            for method, state in [
                ("calendar_only", calendar_daily_state(row, current_date)),
                ("cycle_only", cycle_only_daily_state(row, cycles, current_date)),
                ("cycle_plus_hormones", daily_state(row, cycles, h_to_date, hormone_cols, current_date)),
            ]:
                rows.append({**base, "method": method, **state})

    daily = pd.DataFrame(rows)
    daily["actionable_positive"] = daily["message_class"].isin(
        ["fertile_window_approaching", "ovulation_likely_24_48h"]
    )
    daily["lh_alert"] = daily["message_class"] == "ovulation_likely_24_48h"
    daily["false_reassurance_risk"] = (
        (daily["message_class"].isin(["calendar_guidance", "no_call"]))
        & (daily["days_to_ovulation"].between(0, 2))
    )

    summary_rows = []
    for method in ["calendar_only", "cycle_only", "cycle_plus_hormones"]:
        summary_rows.extend(summarise_method(daily, method))

    summary = pd.DataFrame(summary_rows)
    state_counts = (
        daily.groupby(["method", "state"])
        .agg(
            daily_rows=("cycle_key", "count"),
            cycles=("cycle_key", "nunique"),
            pre_ov_fertile_day_rate=("pre_ovulatory_fertile_day_reference", "mean"),
            median_days_to_ovulation=("days_to_ovulation", "median"),
        )
        .reset_index()
    )

    daily.to_csv(ASSETS / "prospective_daily_states.csv", index=False)
    summary.to_csv(ASSETS / "prospective_daily_metrics.csv", index=False)
    state_counts.to_csv(ASSETS / "prospective_state_counts.csv", index=False)

    print(summary.to_string(index=False))
    print()
    print(state_counts.to_string(index=False))


if __name__ == "__main__":
    main()
