"""
Dependency-light PCOS-pattern analysis analysis.

This script intentionally avoids pandas/sklearn so the first analytical pass can
run in a bare Python environment. It creates a user-level feature table and an
exploratory PCOS-pattern resemblance model with leave-one-user-out validation.

The model is a prototype for scientific/product reasoning, not a diagnostic
model.
"""

from __future__ import annotations

import ast
import csv
import json
import math
import os
import re
import statistics as stats
import zipfile
from collections import Counter, defaultdict
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
REPORT_DIR = ROOT / "reports"
MPL_CACHE_DIR = ROOT / ".matplotlib"
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

PCOS_FILE = DATA_DIR / "pcos_pattern_cohort.xlsx"
NO_PCOS_FILE = DATA_DIR / "reference_pattern_cohort.xlsx"

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def col_number(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref).group(1)
    value = 0
    for ch in letters:
        value = value * 26 + ord(ch) - 64
    return value


def parse_excel_date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def safe_literal(value: str) -> Any:
    if value in ("", None):
        return None
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return None


def read_xlsx(path: Path) -> dict[str, list[dict[str, str]]]:
    """Read simple worksheet tables from an XLSX file using stdlib XML parsing."""
    with zipfile.ZipFile(path) as zf:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", NS):
                shared_strings.append(
                    "".join(t.text or "" for t in item.findall(".//a:t", NS))
                )

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        sheets: dict[str, list[dict[str, str]]] = {}
        for sheet in workbook.findall("a:sheets/a:sheet", NS):
            name = sheet.attrib["name"]
            rid = sheet.attrib[
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            ]
            target = relmap[rid].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target

            root = ET.fromstring(zf.read(target))
            rows: list[list[str]] = []
            for row in root.findall("a:sheetData/a:row", NS):
                values: dict[int, str] = {}
                for cell in row.findall("a:c", NS):
                    ref = cell.attrib.get("r", "")
                    value_node = cell.find("a:v", NS)
                    value = "" if value_node is None else value_node.text or ""
                    if cell.attrib.get("t") == "s" and value != "":
                        value = shared_strings[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        inline = cell.find("a:is", NS)
                        value = (
                            "".join(t.text or "" for t in inline.findall(".//a:t", NS))
                            if inline is not None
                            else ""
                        )
                    values[col_number(ref)] = value
                if values:
                    rows.append([values.get(i, "") for i in range(1, max(values) + 1)])

            if not rows:
                sheets[name] = []
                continue
            headers = rows[0]
            out = []
            for row in rows[1:]:
                padded = row + [""] * (len(headers) - len(row))
                out.append(dict(zip(headers, padded)))
            sheets[name] = out
    return sheets


def numeric_summary(values: list[float], prefix: str) -> dict[str, float]:
    values = [v for v in values if v is not None and not math.isnan(v)]
    if not values:
        return {
            f"{prefix}_n": 0.0,
            f"{prefix}_mean": math.nan,
            f"{prefix}_median": math.nan,
            f"{prefix}_sd": math.nan,
            f"{prefix}_min": math.nan,
            f"{prefix}_max": math.nan,
            f"{prefix}_p90": math.nan,
        }
    ordered = sorted(values)
    p90_idx = max(0, min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1))
    return {
        f"{prefix}_n": float(len(values)),
        f"{prefix}_mean": stats.mean(values),
        f"{prefix}_median": stats.median(values),
        f"{prefix}_sd": stats.stdev(values) if len(values) > 1 else 0.0,
        f"{prefix}_min": min(values),
        f"{prefix}_max": max(values),
        f"{prefix}_p90": ordered[p90_idx],
    }


def mean_or_nan(values: list[float]) -> float:
    clean = [v for v in values if v is not None and not math.isnan(v)]
    return stats.mean(clean) if clean else math.nan


def sd_or_nan(values: list[float]) -> float:
    clean = [v for v in values if v is not None and not math.isnan(v)]
    return stats.stdev(clean) if len(clean) > 1 else (0.0 if clean else math.nan)


def as_ratio(num: float, den: float) -> float:
    if den in (0, None) or math.isnan(den):
        return math.nan
    return num / den


def group_by_hub(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        hub = row.get("hub_id", "")
        if hub:
            grouped[hub].append(row)
    return grouped


def count_json_symptoms(rows: list[dict[str, str]]) -> tuple[int, float, float]:
    count = 0
    levels: list[float] = []
    logs_with_symptoms = 0
    for row in rows:
        parsed = safe_literal(row.get("symptoms", ""))
        if not isinstance(parsed, list):
            continue
        if parsed:
            logs_with_symptoms += 1
        for item in parsed:
            if isinstance(item, dict):
                count += 1
                level = to_float(item.get("level"))
                if level is not None and level < 90:
                    levels.append(level)
    return count, mean_or_nan(levels), float(logs_with_symptoms)


def count_codes(value: str) -> int:
    if not value:
        return 0
    return len([part for part in str(value).split(",") if part.strip()])


def build_user_features(path: Path, label: int) -> list[dict[str, Any]]:
    sheets = read_xlsx(path)
    users = sheets["User_Info_Sheet"]
    cycles = group_by_hub(sheets["CycleData_Sheet"])
    hormones = group_by_hub(sheets["Hormone_Sheet"])
    mood = group_by_hub(sheets["Diary_Mood_Sheet"])
    symptoms = group_by_hub(sheets["Diary_Symptoms_Sheet"])
    pregnant = group_by_hub(sheets["Diary_Pregnant_Sheet"])

    feature_rows: list[dict[str, Any]] = []
    for user in users:
        hub = user["hub_id"]
        c_rows = cycles.get(hub, [])
        h_rows = hormones.get(hub, [])
        m_rows = mood.get(hub, [])
        s_rows = symptoms.get(hub, [])
        p_rows = pregnant.get(hub, [])

        cycle_lengths = [
            to_float(r.get("Cycle Length (days)"))
            for r in c_rows
            if to_float(r.get("Cycle Length (days)")) is not None
        ]
        period_lengths = []
        ovulation_cycle_days = []
        lh_peak_values = []
        pdg_rise_counts = 0
        detected_confirmed = 0
        real_cycles = 0
        for row in c_rows:
            status = to_float(row.get("Cycle Status (Forecast/Real/Pregnancy etc.)"))
            if status == 1:
                real_cycles += 1
            start = parse_excel_date(row.get("Period Start Date"))
            end = parse_excel_date(row.get("Period End Date"))
            ov_date = parse_excel_date(row.get("Ovulation Date"))
            if start and end:
                period_lengths.append((end.date() - start.date()).days + 1)
            if start and ov_date:
                ovulation_cycle_days.append((ov_date.date() - start.date()).days + 1)
            lh_peak = to_float(row.get("LH Peak Value"))
            if lh_peak is not None:
                lh_peak_values.append(lh_peak)
            pdg_dates = safe_literal(row.get("date_PDG_rise", ""))
            if isinstance(pdg_dates, list) and len(pdg_dates) > 0:
                pdg_rise_counts += 1
            if str(row.get("Ovulation Type (Predicted/Detected/Confirmed/Custom)", "")) == "23":
                detected_confirmed += 1

        features: dict[str, Any] = {
            "hub_id": hub,
            "pcos_label": label,
            "source_file": path.name,
            "age": to_float(user.get("Age")),
            "goal": to_float(user.get("Goal")),
            "n_cycles": float(len(c_rows)),
            "n_real_cycles": float(real_cycles),
            "n_hormone_rows": float(len(h_rows)),
            "n_mood_rows": float(len(m_rows)),
            "n_symptom_rows": float(len(s_rows)),
            "n_pregnancy_rows": float(len(p_rows)),
            "prop_cycles_gt35": mean_or_nan([1.0 if x > 35 else 0.0 for x in cycle_lengths]),
            "prop_cycles_lt21": mean_or_nan([1.0 if x < 21 else 0.0 for x in cycle_lengths]),
            "cycle_length_cv": as_ratio(sd_or_nan(cycle_lengths), mean_or_nan(cycle_lengths)),
            "pdg_rise_cycle_prop": as_ratio(float(pdg_rise_counts), float(len(c_rows))),
            "detected_confirmed_ovulation_prop": as_ratio(
                float(detected_confirmed), float(len(c_rows))
            ),
        }
        features.update(numeric_summary(cycle_lengths, "cycle_length"))
        features.update(numeric_summary(period_lengths, "period_length"))
        features.update(numeric_summary(ovulation_cycle_days, "ovulation_cycle_day"))
        features.update(numeric_summary(lh_peak_values, "annotated_lh_peak"))

        hormone_values: dict[str, list[float]] = {
            "lh": [],
            "e3g": [],
            "pdg": [],
            "fsh": [],
            "hcg": [],
        }
        hormone_dates: set[str] = set()
        date_level: dict[str, dict[str, float]] = defaultdict(dict)
        for row in h_rows:
            test_time = parse_excel_date(row.get("Test Time"))
            if test_time:
                date_key = test_time.date().isoformat()
                hormone_dates.add(date_key)
            else:
                date_key = ""
            mapping = {
                "lh": "LH (Luteinizing Hormone)",
                "e3g": "E3G (Estrone‑3‑glucuronide)",
                "pdg": "PDG (Pregnanediol Glucuronide)",
                "fsh": "FSH (Follicle‑Stimulating Hormone)",
                "hcg": "hcg",
            }
            for short, col in mapping.items():
                value = to_float(row.get(col))
                if value is not None:
                    hormone_values[short].append(value)
                    if date_key:
                        date_level[date_key][short] = max(
                            value, date_level[date_key].get(short, -math.inf)
                        )

        for short, values in hormone_values.items():
            features.update(numeric_summary(values, short))

        lh_median = features["lh_median"]
        pdg_median = features["pdg_median"]
        features["unique_hormone_test_days"] = float(len(hormone_dates))
        features["hormone_test_days_per_cycle"] = as_ratio(
            float(len(hormone_dates)), float(len(c_rows))
        )
        features["lh_peak_to_median"] = as_ratio(features["lh_max"], lh_median)
        features["pdg_peak_to_median"] = as_ratio(features["pdg_max"], pdg_median)
        features["prop_lh_over_16"] = mean_or_nan(
            [1.0 if value >= 16 else 0.0 for value in hormone_values["lh"]]
        )
        features["prop_pdg_over_5"] = mean_or_nan(
            [1.0 if value >= 5 else 0.0 for value in hormone_values["pdg"]]
        )
        features["prop_pdg_over_10"] = mean_or_nan(
            [1.0 if value >= 10 else 0.0 for value in hormone_values["pdg"]]
        )
        same_day_ratios = []
        for vals in date_level.values():
            if "lh" in vals and "fsh" in vals and vals["fsh"] > 0:
                same_day_ratios.append(vals["lh"] / vals["fsh"])
        features.update(numeric_summary(same_day_ratios, "same_day_lh_fsh_ratio"))

        mood_code_counts = []
        feeling_code_counts = []
        sluggish_logs = 0
        skin_logs = 0
        for row in m_rows:
            mood_code_counts.append(count_codes(row.get("mood", "")))
            feeling_code_counts.append(count_codes(row.get("feeling", "")))
            if row.get("exercise", "") == "sluggish":
                sluggish_logs += 1
            if row.get("skin", "") not in ("", None):
                skin_logs += 1
        features["mood_codes_per_log"] = mean_or_nan(mood_code_counts)
        features["feeling_codes_per_log"] = mean_or_nan(feeling_code_counts)
        features["prop_exercise_sluggish_logs"] = as_ratio(float(sluggish_logs), float(len(m_rows)))
        features["prop_skin_logs"] = as_ratio(float(skin_logs), float(len(m_rows)))

        symptom_count, symptom_level_mean, logs_with_symptoms = count_json_symptoms(s_rows)
        features["symptom_item_count"] = float(symptom_count)
        features["mean_symptom_level"] = symptom_level_mean
        features["symptom_items_per_log"] = as_ratio(float(symptom_count), float(len(s_rows)))
        features["logs_with_symptoms"] = logs_with_symptoms

        feature_rows.append(features)
    return feature_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def median_impute_and_scale(
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    features: list[str],
) -> tuple[list[list[float]], list[list[float]], dict[str, float], dict[str, float]]:
    medians: dict[str, float] = {}
    means: dict[str, float] = {}
    sds: dict[str, float] = {}
    for feature in features:
        values = [to_float(row.get(feature)) for row in train_rows]
        values = [v for v in values if v is not None]
        median = stats.median(values) if values else 0.0
        filled = [median if to_float(row.get(feature)) is None else to_float(row.get(feature)) for row in train_rows]
        mean = stats.mean(filled) if filled else 0.0
        sd = stats.stdev(filled) if len(filled) > 1 else 1.0
        if sd == 0:
            sd = 1.0
        medians[feature] = median
        means[feature] = mean
        sds[feature] = sd

    def transform(rows: list[dict[str, Any]]) -> list[list[float]]:
        matrix = []
        for row in rows:
            output = []
            for feature in features:
                value = to_float(row.get(feature))
                if value is None:
                    value = medians[feature]
                output.append((value - means[feature]) / sds[feature])
            matrix.append(output)
        return matrix

    return transform(train_rows), transform(test_rows), means, sds


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)


def fit_logistic(
    x: list[list[float]],
    y: list[int],
    l2: float = 0.25,
    lr: float = 0.08,
    epochs: int = 500,
) -> list[float]:
    n_features = len(x[0])
    weights = [0.0] * (n_features + 1)
    n = len(y)
    pos = sum(y)
    neg = n - pos
    pos_weight = n / (2 * pos) if pos else 1.0
    neg_weight = n / (2 * neg) if neg else 1.0

    for _ in range(epochs):
        grads = [0.0] * (n_features + 1)
        for row, target in zip(x, y):
            pred = sigmoid(weights[0] + sum(w * v for w, v in zip(weights[1:], row)))
            sample_weight = pos_weight if target == 1 else neg_weight
            error = (pred - target) * sample_weight
            grads[0] += error
            for j, value in enumerate(row):
                grads[j + 1] += error * value
        for j in range(1, len(weights)):
            grads[j] += l2 * weights[j]
        for j in range(len(weights)):
            weights[j] -= lr * grads[j] / n
    return weights


def predict_logistic(weights: list[float], x: list[list[float]]) -> list[float]:
    return [sigmoid(weights[0] + sum(w * v for w, v in zip(weights[1:], row))) for row in x]


def rank_auc(y: list[int], scores: list[float]) -> float:
    pairs = sorted(zip(scores, y), key=lambda item: item[0])
    ranks = []
    i = 0
    while i < len(pairs):
        j = i + 1
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + 1 + j) / 2
        ranks.extend([avg_rank] * (j - i))
        i = j
    pos_ranks = [rank for rank, (_, target) in zip(ranks, pairs) if target == 1]
    n_pos = sum(y)
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return math.nan
    return (sum(pos_ranks) - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def average_precision(y: list[int], scores: list[float]) -> float:
    ordered = sorted(zip(scores, y), key=lambda item: item[0], reverse=True)
    total_pos = sum(y)
    if total_pos == 0:
        return math.nan
    hits = 0
    precision_sum = 0.0
    for idx, (_, target) in enumerate(ordered, start=1):
        if target == 1:
            hits += 1
            precision_sum += hits / idx
    return precision_sum / total_pos


def roc_curve_points(y: list[int], scores: list[float]) -> tuple[list[float], list[float]]:
    thresholds = [math.inf] + sorted(set(scores), reverse=True) + [-math.inf]
    fprs = []
    tprs = []
    positives = sum(y)
    negatives = len(y) - positives
    for threshold in thresholds:
        tp = fp = 0
        for target, score in zip(y, scores):
            if score >= threshold:
                if target == 1:
                    tp += 1
                else:
                    fp += 1
        tprs.append(tp / positives if positives else math.nan)
        fprs.append(fp / negatives if negatives else math.nan)
    return fprs, tprs


def confusion_at_threshold(y: list[int], scores: list[float], threshold: float) -> dict[str, float]:
    tp = fp = tn = fn = 0
    for target, score in zip(y, scores):
        pred = 1 if score >= threshold else 0
        if target == 1 and pred == 1:
            tp += 1
        elif target == 0 and pred == 1:
            fp += 1
        elif target == 0 and pred == 0:
            tn += 1
        else:
            fn += 1
    sensitivity = tp / (tp + fn) if tp + fn else math.nan
    specificity = tn / (tn + fp) if tn + fp else math.nan
    ppv = tp / (tp + fp) if tp + fp else math.nan
    npv = tn / (tn + fn) if tn + fn else math.nan
    return {
        "threshold": threshold,
        "tp": float(tp),
        "fp": float(fp),
        "tn": float(tn),
        "fn": float(fn),
        "sensitivity": sensitivity,
        "specificity": specificity,
        "ppv": ppv,
        "npv": npv,
        "flag_rate": (tp + fp) / len(y),
    }


def metric_row(name: str, result: "ModelResult") -> dict[str, Any]:
    threshold = stats.median(result.scores)
    confusion = confusion_at_threshold(result.labels, result.scores, threshold)
    return {
        "model": name,
        "n_features": float(len(result.selected_features)),
        "loou_roc_auc": rank_auc(result.labels, result.scores),
        "loou_average_precision": average_precision(result.labels, result.scores),
        "median_threshold_sensitivity": confusion["sensitivity"],
        "median_threshold_specificity": confusion["specificity"],
        "median_threshold_ppv": confusion["ppv"],
        "median_threshold_flag_rate": confusion["flag_rate"],
    }


@dataclass
class ModelResult:
    scores: list[float]
    labels: list[int]
    rows: list[dict[str, Any]]
    selected_features: list[str]
    full_weights: list[float]
    full_means: dict[str, float]
    full_sds: dict[str, float]


def feature_missing_rate(rows: list[dict[str, Any]], feature: str) -> float:
    missing = sum(1 for row in rows if to_float(row.get(feature)) is None)
    return missing / len(rows)


def select_features(rows: list[dict[str, Any]]) -> list[str]:
    excluded = {"hub_id", "pcos_label", "source_file"}
    candidates = [
        key
        for key in rows[0]
        if key not in excluded
        and all(isinstance(row.get(key), (int, float)) or to_float(row.get(key)) is not None or row.get(key) in ("", None) for row in rows)
    ]
    selected = []
    for feature in candidates:
        if feature_missing_rate(rows, feature) <= 0.45:
            values = [to_float(row.get(feature)) for row in rows if to_float(row.get(feature)) is not None]
            if len(set(round(v, 8) for v in values)) > 1:
                selected.append(feature)

    # Keep the first-pass model intentionally lean and interpretable. With only
    # 40 users, a wide feature set is unstable and slow in pure Python.
    priority = [
        "cycle_length_mean",
        "cycle_length_sd",
        "cycle_length_cv",
        "cycle_length_max",
        "prop_cycles_gt35",
        "ovulation_cycle_day_mean",
        "ovulation_cycle_day_sd",
        "pdg_rise_cycle_prop",
        "detected_confirmed_ovulation_prop",
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
        "hormone_test_days_per_cycle",
        "n_mood_rows",
        "n_symptom_rows",
        "symptom_items_per_log",
        "mean_symptom_level",
        "age",
    ]
    prioritized = [feature for feature in priority if feature in selected]
    extras = [feature for feature in selected if feature not in prioritized]
    return (prioritized + extras)[:30]


def leave_one_user_out(rows: list[dict[str, Any]], features: list[str]) -> ModelResult:
    labels = [int(row["pcos_label"]) for row in rows]
    scores = []
    for i in range(len(rows)):
        train = rows[:i] + rows[i + 1 :]
        test = [rows[i]]
        x_train, x_test, _, _ = median_impute_and_scale(train, test, features)
        y_train = [int(row["pcos_label"]) for row in train]
        weights = fit_difference_score(x_train, y_train)
        scores.append(predict_difference_score(weights, x_test)[0])

    x_all, _, means, sds = median_impute_and_scale(rows, [], features)
    weights = fit_difference_score(x_all, labels)
    return ModelResult(scores, labels, rows, features, weights, means, sds)


def fit_difference_score(x: list[list[float]], y: list[int]) -> list[float]:
    """Fit a transparent standardized mean-difference resemblance score.

    Coefficients point toward the self-identified PCOS group. This is less
    flexible than logistic regression but more stable for 40 users and very fast
    to cross-validate.
    """
    n_features = len(x[0])
    pos_rows = [row for row, target in zip(x, y) if target == 1]
    neg_rows = [row for row, target in zip(x, y) if target == 0]
    weights = []
    for j in range(n_features):
        pos_mean = stats.mean(row[j] for row in pos_rows)
        neg_mean = stats.mean(row[j] for row in neg_rows)
        weights.append(pos_mean - neg_mean)
    norm = math.sqrt(sum(w * w for w in weights)) or 1.0
    weights = [w / norm for w in weights]
    intercept = -0.5 * (
        stats.mean(sum(w * v for w, v in zip(weights, row)) for row in pos_rows)
        + stats.mean(sum(w * v for w, v in zip(weights, row)) for row in neg_rows)
    )
    return [intercept] + weights


def predict_difference_score(weights: list[float], x: list[list[float]]) -> list[float]:
    return [sigmoid(weights[0] + sum(w * v for w, v in zip(weights[1:], row))) for row in x]


def summarize_by_group(rows: list[dict[str, Any]], features: list[str]) -> list[dict[str, Any]]:
    out = []
    for feature in features:
        pcos_values = [to_float(row.get(feature)) for row in rows if row["pcos_label"] == 1]
        no_values = [to_float(row.get(feature)) for row in rows if row["pcos_label"] == 0]
        pcos_values = [v for v in pcos_values if v is not None]
        no_values = [v for v in no_values if v is not None]
        if not pcos_values or not no_values:
            continue
        diff = stats.mean(pcos_values) - stats.mean(no_values)
        pooled = math.sqrt((sd_or_nan(pcos_values) ** 2 + sd_or_nan(no_values) ** 2) / 2)
        standardized = diff / pooled if pooled else math.nan
        out.append(
            {
                "feature": feature,
                "pcos_mean": stats.mean(pcos_values),
                "no_pcos_mean": stats.mean(no_values),
                "difference": diff,
                "standardized_difference": standardized,
                "pcos_median": stats.median(pcos_values),
                "no_pcos_median": stats.median(no_values),
            }
        )
    return sorted(out, key=lambda row: abs(row["standardized_difference"]), reverse=True)


def coefficient_table(result: ModelResult) -> list[dict[str, Any]]:
    rows = []
    for feature, coef in zip(result.selected_features, result.full_weights[1:]):
        rows.append({"feature": feature, "coefficient": coef, "abs_coefficient": abs(coef)})
    return sorted(rows, key=lambda row: row["abs_coefficient"], reverse=True)


def band_table(labels: list[int], scores: list[float]) -> list[dict[str, Any]]:
    ordered_scores = sorted(scores)
    low_cut = ordered_scores[math.ceil(0.33 * len(scores)) - 1]
    high_cut = ordered_scores[math.ceil(0.67 * len(scores)) - 1]
    bands = []
    for label, score in zip(labels, scores):
        if score <= low_cut:
            band = "lower resemblance"
        elif score <= high_cut:
            band = "indeterminate"
        else:
            band = "higher resemblance"
        bands.append((band, label, score))
    out = []
    for band in ["lower resemblance", "indeterminate", "higher resemblance"]:
        subset = [(label, score) for b, label, score in bands if b == band]
        out.append(
            {
                "band": band,
                "users": float(len(subset)),
                "pcos_users": float(sum(label for label, _ in subset)),
                "pcos_rate": sum(label for label, _ in subset) / len(subset) if subset else math.nan,
                "mean_score": stats.mean(score for _, score in subset) if subset else math.nan,
            }
        )
    return out


def save_visualizations(
    result: ModelResult,
    group_summary: list[dict[str, Any]],
    bands: list[dict[str, Any]],
    variant_metrics: list[dict[str, Any]],
) -> dict[str, str]:
    import matplotlib.pyplot as plt

    MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update(
        {
            "figure.dpi": 160,
            "savefig.dpi": 220,
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    colors = {
        "pcos": "#b23a48",
        "no_pcos": "#277da1",
        "neutral": "#5c677d",
        "grid": "#e5e7eb",
    }
    paths: dict[str, str] = {}

    # ROC curve.
    fprs, tprs = roc_curve_points(result.labels, result.scores)
    auc = rank_auc(result.labels, result.scores)
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    ax.plot(fprs, tprs, color=colors["pcos"], linewidth=2.5, label=f"LOO ROC AUC = {auc:.3f}")
    ax.plot([0, 1], [0, 1], color="#9ca3af", linestyle="--", linewidth=1.2, label="No-signal reference")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("User-level ROC curve")
    ax.grid(True, color=colors["grid"], linewidth=0.8)
    ax.legend(loc="lower right", frameon=False)
    path = ASSET_DIR / "pcos_roc_curve.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    paths["roc_curve"] = str(path)

    # Score distribution.
    pcos_scores = [s for y, s in zip(result.labels, result.scores) if y == 1]
    no_scores = [s for y, s in zip(result.labels, result.scores) if y == 0]
    fig, ax = plt.subplots(figsize=(6.2, 4.3))
    bins = [i / 10 for i in range(0, 11)]
    ax.hist(no_scores, bins=bins, alpha=0.72, color=colors["no_pcos"], label="No-PCOS file")
    ax.hist(pcos_scores, bins=bins, alpha=0.72, color=colors["pcos"], label="Self-identified PCOS")
    ax.set_xlabel("Cross-validated resemblance score")
    ax.set_ylabel("Users")
    ax.set_title("Held-out user score distribution")
    ax.grid(True, axis="y", color=colors["grid"], linewidth=0.8)
    ax.legend(frameon=False)
    path = ASSET_DIR / "pcos_score_distribution.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    paths["score_distribution"] = str(path)

    # Band rates.
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    labels = [row["band"] for row in bands]
    rates = [row["pcos_rate"] for row in bands]
    users = [row["users"] for row in bands]
    bar_colors = ["#8ecae6", "#adb5bd", "#e56b6f"]
    ax.bar(labels, rates, color=bar_colors)
    for i, (rate, n_users) in enumerate(zip(rates, users)):
        ax.text(i, rate + 0.03, f"{rate:.0%}\n(n={int(n_users)})", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Self-identified PCOS share")
    ax.set_title("Resemblance bands enrich the labelled cohort")
    ax.grid(True, axis="y", color=colors["grid"], linewidth=0.8)
    path = ASSET_DIR / "pcos_resemblance_bands.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    paths["resemblance_bands"] = str(path)

    # Top standardized differences.
    top_features = group_summary[:10]
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    names = [row["feature"] for row in top_features][::-1]
    values = [row["standardized_difference"] for row in top_features][::-1]
    colors_for_values = [colors["pcos"] if value >= 0 else colors["no_pcos"] for value in values]
    ax.barh(names, values, color=colors_for_values)
    ax.axvline(0, color="#6b7280", linewidth=1)
    ax.set_xlabel("Standardized difference (PCOS file minus no-PCOS file)")
    ax.set_title("Largest cohort differences")
    ax.grid(True, axis="x", color=colors["grid"], linewidth=0.8)
    path = ASSET_DIR / "pcos_feature_differences.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    paths["top_feature_differences"] = str(path)

    # Model variant comparison.
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    names = [row["model"] for row in variant_metrics]
    aucs = [row["loou_roc_auc"] for row in variant_metrics]
    ax.bar(names, aucs, color=["#90be6d", "#43aa8b", "#277da1", "#f3722c"])
    for i, auc_value in enumerate(aucs):
        ax.text(i, auc_value + 0.015, f"{auc_value:.3f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0.5, 1.02)
    ax.set_ylabel("Leave-one-user-out ROC AUC")
    ax.set_title("Signal remains under conservative feature sets")
    ax.tick_params(axis="x", rotation=18)
    ax.grid(True, axis="y", color=colors["grid"], linewidth=0.8)
    path = ASSET_DIR / "pcos_model_comparison.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    paths["model_variant_auc"] = str(path)

    return paths


def markdown_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> str:
    rows = rows[:max_rows] if max_rows else rows
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                value = f"{value:.3f}" if not math.isnan(value) else ""
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_markdown_report(
    result: ModelResult,
    group_summary: list[dict[str, Any]],
    coefficients: list[dict[str, Any]],
    bands: list[dict[str, Any]],
    variant_metrics: list[dict[str, Any]],
    figure_paths: dict[str, str],
) -> None:
    y = result.labels
    scores = result.scores
    auc = rank_auc(y, scores)
    ap = average_precision(y, scores)
    median_threshold = stats.median(scores)
    confusion = confusion_at_threshold(y, scores, median_threshold)

    data_inventory = [
        {
            "group": "Self-identified PCOS",
            "users": sum(1 for row in result.rows if row["pcos_label"] == 1),
            "cycle_rows": sum(row["n_cycles"] for row in result.rows if row["pcos_label"] == 1),
            "hormone_rows": sum(row["n_hormone_rows"] for row in result.rows if row["pcos_label"] == 1),
        },
        {
            "group": "No PCOS file",
            "users": sum(1 for row in result.rows if row["pcos_label"] == 0),
            "cycle_rows": sum(row["n_cycles"] for row in result.rows if row["pcos_label"] == 0),
            "hormone_rows": sum(row["n_hormone_rows"] for row in result.rows if row["pcos_label"] == 0),
        },
    ]

    report = f"""# Model Run Summary - PCOS-Pattern Resemblance Prototype

## Framing

This is an exploratory model estimating whether a user's longitudinal pattern resembles the self-identified PCOS group in the anonymized demonstration files. It is not a diagnostic PCOS model.

## Data inventory

{markdown_table(data_inventory, ["group", "users", "cycle_rows", "hormone_rows"])}

## Prevalence and label caveats

The demonstration modelling dataset is deliberately balanced: 20 users from the PCOS file and 20 users from the no-PCOS file, so the sample prevalence is 50%. Real-world PCOS prevalence in an app population is likely much lower and will vary by acquisition channel, age, goal, symptoms, and prior diagnosis history.

This matters because model precision, alert burden, and positive predictive value are prevalence-dependent. A score that looks useful in a 50:50 case-control style dataset may generate many false positives in a lower-prevalence production population.

The labels are also self-reported. Some users in the PCOS file may not meet clinician-confirmed diagnostic criteria, and some users in the no-PCOS file may have undiagnosed PCOS or related endocrine conditions. This label noise should be expected to reduce measured performance and can also bias feature interpretation.

**Validation implication:** a true validation dataset should be representative of the app user population and should include clinician-confirmed PCOS status, or at minimum a carefully adjudicated clinical reference standard.

## Validation approach

The unit of analysis is the user. Each user is represented by aggregated cycle, hormone, diary, and data-sufficiency features. Because there are only 40 users, performance is estimated with leave-one-user-out validation rather than a small fixed train/test split.

## Exploratory validation results

Primary model reported below: **cycle + hormone core**, excluding direct condition text and app-use volume features.

| Metric | Value |
|---|---:|
| Users | {len(y)} |
| Positive/self-identified PCOS users | {sum(y)} |
| Leave-one-user-out ROC AUC | {auc:.3f} |
| Leave-one-user-out average precision | {ap:.3f} |
| Median-threshold sensitivity | {confusion["sensitivity"]:.3f} |
| Median-threshold specificity | {confusion["specificity"]:.3f} |
| Median-threshold PPV | {confusion["ppv"]:.3f} |
| Median-threshold flag rate | {confusion["flag_rate"]:.3f} |

These results should be interpreted as a small-sample signal check, not evidence of deployment readiness.

![User-level ROC curve](../assets/pcos_roc_curve.png)

![Held-out score distribution](../assets/pcos_score_distribution.png)

## Sensitivity across feature sets

{markdown_table(variant_metrics, ["model", "n_features", "loou_roc_auc", "loou_average_precision", "median_threshold_sensitivity", "median_threshold_specificity"])}

The broader model performs strongly, but the safer interpretation comes from whether cycle/hormone features retain signal without relying on logging behavior or direct condition text.

![Model variant AUC comparison](../assets/pcos_model_comparison.png)

## Resemblance bands from cross-validated scores

{markdown_table(bands, ["band", "users", "pcos_users", "pcos_rate", "mean_score"])}

![Resemblance bands](../assets/pcos_resemblance_bands.png)

## Strongest group differences

{markdown_table(group_summary, ["feature", "pcos_mean", "no_pcos_mean", "difference", "standardized_difference"], max_rows=15)}

![Top feature differences](../assets/pcos_feature_differences.png)

## Largest model coefficients

{markdown_table(coefficients, ["feature", "coefficient"], max_rows=15)}

## Product interpretation

The model can be useful as a prototype for identifying longitudinal patterns that differ between the two demonstration cohorts. It should not be surfaced as a PCOS prediction, PCOS probability, or diagnostic risk score.

The safer product translation is a non-diagnostic insight about observed cycle or hormone variability, gated by data sufficiency and supported by clinician-reviewed language.

## Recommended claim boundary

- Safe for internal research/prototyping: yes.
- Safe for silent-mode prospective validation: potentially, with a stronger protocol.
- Safe for direct user-facing PCOS prediction: no.
- Safe for cautious cycle-variability education: possibly after validation and human-factors review.

## Prospective validation requirement

The next validation stage should use a prospectively collected, app-representative cohort with clinician-confirmed PCOS labels. It should evaluate performance under the true production prevalence, include users with overlapping conditions such as thyroid disease and endometriosis, and quantify false-positive burden before any user-facing insight is released.
"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "pcos_model_run_summary.generated.md").write_text(report, encoding="utf-8")


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    rows = build_user_features(PCOS_FILE, 1) + build_user_features(NO_PCOS_FILE, 0)
    rows = sorted(rows, key=lambda row: (row["pcos_label"], row["hub_id"]))
    write_csv(ASSET_DIR / "pcos_user_features.csv", rows)

    selected_features = select_features(rows)

    def present(names: list[str]) -> list[str]:
        return [name for name in names if name in selected_features]

    variant_features = OrderedDict(
        [
            (
                "cycle_only",
                present(
                    [
                        "cycle_length_mean",
                        "cycle_length_sd",
                        "cycle_length_cv",
                        "cycle_length_min",
                        "cycle_length_max",
                        "prop_cycles_gt35",
                        "prop_cycles_lt21",
                        "period_length_mean",
                        "period_length_sd",
                    ]
                ),
            ),
            (
                "cycle_plus_ovulation_annotations",
                present(
                    [
                        "cycle_length_mean",
                        "cycle_length_sd",
                        "cycle_length_cv",
                        "cycle_length_max",
                        "prop_cycles_gt35",
                        "ovulation_cycle_day_mean",
                        "ovulation_cycle_day_sd",
                        "pdg_rise_cycle_prop",
                        "detected_confirmed_ovulation_prop",
                    ]
                ),
            ),
            (
                "cycle_hormone_core",
                present(
                    [
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
                ),
            ),
            (
                "full_exploratory",
                selected_features,
            ),
        ]
    )

    variant_results = {
        name: leave_one_user_out(rows, features)
        for name, features in variant_features.items()
        if features
    }
    variant_metrics = [metric_row(name, result) for name, result in variant_results.items()]

    result = variant_results["cycle_hormone_core"]
    scored_rows = []
    for row, score in zip(result.rows, result.scores):
        out = dict(row)
        out["loou_score"] = score
        scored_rows.append(out)
    write_csv(ASSET_DIR / "pcos_user_scores.csv", scored_rows)
    write_csv(ASSET_DIR / "pcos_model_variant_metrics.csv", variant_metrics)

    group_summary = summarize_by_group(rows, selected_features)
    coefficients = coefficient_table(result)
    bands = band_table(result.labels, result.scores)
    figure_paths = save_visualizations(result, group_summary, bands, variant_metrics)

    write_csv(ASSET_DIR / "pcos_group_feature_summary.csv", group_summary)
    write_csv(ASSET_DIR / "pcos_model_coefficients.csv", coefficients)
    write_csv(ASSET_DIR / "pcos_score_bands.csv", bands)

    write_markdown_report(result, group_summary, coefficients, bands, variant_metrics, figure_paths)

    print(
        json.dumps(
            {
                "users": len(rows),
                "features_selected": len(result.selected_features),
                "primary_model": "cycle_hormone_core",
                "loou_roc_auc": rank_auc(result.labels, result.scores),
                "loou_average_precision": average_precision(result.labels, result.scores),
                "outputs": [
                    str(ASSET_DIR / "pcos_user_features.csv"),
                    str(ASSET_DIR / "pcos_user_scores.csv"),
                    str(ASSET_DIR / "pcos_roc_curve.png"),
                    str(REPORT_DIR / "pcos_model_run_summary.generated.md"),
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
