import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pcos_pattern_analysis as pattern
from ovulation_window_model import cycle_hormones, detect_hormone_columns, load_data
from prospective_daily_evaluation import daily_state


PCOS = ROOT / "data" / "pcos_pattern_cohort.xlsx"
REFERENCE = ROOT / "data" / "reference_pattern_cohort.xlsx"


class AnalysisInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pcos_rows = pattern.build_user_features(PCOS, 1)
        cls.reference_rows = pattern.build_user_features(REFERENCE, 0)

    def test_one_feature_row_per_user_and_disjoint_cohorts(self):
        self.assertEqual(len(self.pcos_rows), 20)
        self.assertEqual(len(self.reference_rows), 20)
        pcos_ids = {row["hub_id"] for row in self.pcos_rows}
        reference_ids = {row["hub_id"] for row in self.reference_rows}
        self.assertEqual(len(pcos_ids), 20)
        self.assertEqual(len(reference_ids), 20)
        self.assertTrue(pcos_ids.isdisjoint(reference_ids))

    def test_direct_label_text_cannot_enter_predictors(self):
        rows = self.pcos_rows + self.reference_rows
        selected = {name.lower() for name in pattern.select_features(rows)}
        forbidden = {"conditions", "pcos_label", "hub_id"}
        self.assertTrue(selected.isdisjoint(forbidden))

    def test_leave_one_user_out_returns_one_bounded_score_per_user(self):
        rows = self.pcos_rows + self.reference_rows
        result = pattern.leave_one_user_out(rows, pattern.select_features(rows))
        self.assertEqual(len(result.scores), len(rows))
        self.assertTrue(all(0.0 <= score <= 1.0 for score in result.scores))

    def test_prospective_state_uses_only_supplied_history(self):
        cycles, hormones = load_data()
        hormone_cols = detect_hormone_columns(hormones)
        row = cycles[cycles["Ovulation Date"].notna()].iloc[0]
        history = cycle_hormones(row, hormones).sort_values("test_date")
        cutoff = history["test_date"].iloc[len(history) // 2]
        observed = history[history["test_date"] <= cutoff].copy()
        state = daily_state(row, cycles, observed, hormone_cols, cutoff)
        self.assertLessEqual(observed["test_date"].max(), cutoff)
        self.assertIn("state", state)
        self.assertIn("confidence", state)

    def test_selected_report_figures_exist(self):
        expected = {
            "pcos_roc_curve.png",
            "pcos_score_distribution.png",
            "pcos_feature_differences.png",
            "fertile_window_flow.png",
            "hormone_user_journey.png",
            "insight_engine_architecture.png",
        }
        existing = {path.name for path in (ROOT / "assets").glob("*.png")}
        self.assertTrue(expected.issubset(existing))


if __name__ == "__main__":
    unittest.main()
