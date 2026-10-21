from __future__ import annotations

import unittest

from app.adaptive_teaching import (
    apply_adaptive_policy,
    build_adaptive_experiment,
    select_teaching_policy,
    update_learner_state,
)
from app.code_lessons import get_lesson_spec
from app.pedagogical_ir import compile_lesson_ir


class AdaptiveTeachingTests(unittest.TestCase):
    def setUp(self):
        self.ir, _ = compile_lesson_ir(get_lesson_spec("linear-function"), "A4")

    def test_observation_updates_state_and_error_diagnosis(self):
        result = update_learner_state(
            {"mastery": 0.7, "attention": 0.8},
            {
                "concept": "斜率",
                "correct": False,
                "misconception": "conceptual_gap",
                "responseTimeSeconds": 55,
                "expectedTimeSeconds": 30,
            },
        )
        self.assertEqual(result["diagnosis"]["label"], "conceptual_gap")
        self.assertLess(result["learnerState"]["mastery"], 0.7)
        self.assertEqual(len(result["learnerState"]["evidence"]), 1)

    def test_low_attention_selects_visual_and_embodied_cues(self):
        policy = select_teaching_policy(
            {"mastery": 0.65, "attention": 0.3, "cognitiveLoad": 0.4},
            "E4",
        )
        self.assertEqual(policy["primaryAction"], "visual_replay")
        self.assertIn("embodied_cue", policy["actions"])
        self.assertEqual(policy["renderControls"]["cueSalience"], "high")

    def test_high_load_reduces_information_density(self):
        policy = select_teaching_policy(
            {"mastery": 0.4, "attention": 0.8, "cognitiveLoad": 0.9},
            "E4",
        )
        self.assertEqual(policy["primaryAction"], "reduce_information_density")
        self.assertEqual(policy["renderControls"]["pacing"], "slower")

    def test_conceptual_gap_selects_counterfactual_strategy(self):
        policy = select_teaching_policy(
            {
                "mastery": 0.45,
                "attention": 0.8,
                "cognitiveLoad": 0.5,
                "misconception": "conceptual_gap",
            },
            "E4",
        )
        self.assertEqual(policy["primaryAction"], "counterfactual_question")

    def test_policy_is_applied_to_ir_events(self):
        value = apply_adaptive_policy(
            self.ir,
            {"mastery": 0.4, "attention": 0.3, "cognitiveLoad": 0.5},
            "E4",
        )
        event = value["adaptiveIr"]["timeline"]["events"][0]
        self.assertTrue(event["learnerStateTrigger"]["enabled"])
        self.assertTrue(event["learnerStateTrigger"]["matched"])
        self.assertEqual(event["dialogue"]["act"], "visual_replay")

    def test_adaptive_experiment_contains_all_e3_and_e5_conditions(self):
        result = build_adaptive_experiment(
            self.ir,
            {"mastery": 0.5, "attention": 0.7, "cognitiveLoad": 0.5},
        )
        self.assertEqual(set(result["e3Variants"]), {"C0", "C1", "C2", "C3", "C4"})
        self.assertEqual(
            set(result["e5Variants"]),
            {"E0", "E1", "E2", "E3", "E4", "E5"},
        )


if __name__ == "__main__":
    unittest.main()
