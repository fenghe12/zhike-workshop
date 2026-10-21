from __future__ import annotations

import unittest

from app.experiment_analysis import (
    analyze_learning_rows,
    approximate_two_group_sample_size,
    build_experiment_protocol,
)


class ExperimentAnalysisTests(unittest.TestCase):
    def test_protocol_declares_endpoints_and_draft_status(self):
        protocol = build_experiment_protocol("E2", ["B0", "B4"], 0.5, 0.05, 0.8)
        self.assertEqual(protocol["registrationStatus"], "draft_not_preregistered")
        self.assertIn("aoi_dwell_time", protocol["primaryEndpoints"])
        self.assertGreater(protocol["powerPlanning"]["approximateParticipantsPerTwoGroupComparison"], 0)

    def test_sample_size_rejects_invalid_effect_size(self):
        with self.assertRaises(ValueError):
            approximate_two_group_sample_size(0)

    def test_empty_template_is_not_reported_as_learning_effect(self):
        result = analyze_learning_rows(
            [{"participant_id": "", "lesson_id": "linear-function", "experiment_id": "E1", "condition": "A0", "pretest": "", "posttest": ""}]
        )
        self.assertEqual(result["humanOutcomeStatus"], "not_measured")
        self.assertIsNone(result["groupSummaries"][0]["metrics"]["raw_learning_gain"]["mean"])

    def test_actual_rows_compute_learning_gain_and_effect_size(self):
        rows = []
        for condition, posts in (("A0", [60, 65, 70]), ("A4", [80, 85, 90])):
            for index, post in enumerate(posts):
                rows.append(
                    {
                        "participant_id": f"{condition}_{index}",
                        "lesson_id": "linear-function",
                        "experiment_id": "E1",
                        "condition": condition,
                        "pretest": 50,
                        "posttest": post,
                        "delayed_test": post - 5,
                        "near_transfer": post - 2,
                        "far_transfer": post - 8,
                    }
                )
        result = analyze_learning_rows(rows)
        self.assertEqual(result["humanOutcomeStatus"], "measured")
        measured = [item for item in result["pairwiseEffectSizes"] if item["metric"] == "posttest"]
        self.assertEqual(len(measured), 1)
        self.assertIsNotNone(measured[0]["cohenD"])


if __name__ == "__main__":
    unittest.main()
