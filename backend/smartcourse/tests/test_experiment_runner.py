from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from app.experiment_runner import ExperimentRunner


class ExperimentRunnerTests(unittest.TestCase):
    def test_runner_saves_conditions_and_empty_human_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ExperimentRunner(directory).run(
                ["E1", "E2"],
                ["linear-function"],
                seed=7,
            )
            self.assertEqual(result["conditionCount"], 11)
            self.assertEqual(result["humanOutcomeStatus"], "not_measured")
            self.assertTrue(Path(result["manifest"]).is_file())
            self.assertTrue(Path(result["humanRatingTemplate"]).is_file())
            self.assertTrue(Path(result["learningStudyTemplate"]).is_file())
            with Path(result["learningStudyTemplate"]).open(encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 11)
            self.assertTrue(all(row["pretest"] == "" for row in rows))

    def test_full_suite_contains_48_conditions_per_lesson(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ExperimentRunner(directory).run(
                ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"],
                ["ph-indicator"],
            )
            self.assertEqual(result["conditionCount"], 48)
            self.assertEqual(
                {row["experimentId"] for row in result["results"]},
                {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"},
            )


if __name__ == "__main__":
    unittest.main()
