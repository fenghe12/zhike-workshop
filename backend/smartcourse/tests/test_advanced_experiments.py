from __future__ import annotations

import unittest

from app.advanced_experiments import (
    build_personalization_plan,
    check_pedagogical_alignment,
    prescreen_candidate,
    select_proactive_intervention,
    update_structured_memory,
)


class AdvancedExperimentTests(unittest.TestCase):
    def test_learner_state_triggers_proactive_intervention(self):
        result = select_proactive_intervention(
            {"mastery": 0.7, "attention": 0.3, "cognitiveLoad": 0.5},
            "D4",
        )
        self.assertTrue(result["shouldIntervene"])
        self.assertEqual(result["trigger"], "low_attention")
        self.assertEqual(result["action"], "attention_check")

    def test_structured_memory_groups_concept_evidence(self):
        memory = update_structured_memory(
            None,
            {"concept": "斜率", "success": True, "confidence": 0.9},
            "F4",
        )
        memory = update_structured_memory(
            memory,
            {"concept": "斜率", "success": False, "confidence": 0.8},
            "F4",
        )
        self.assertEqual(memory["conceptSummaries"][0]["evidenceCount"], 2)
        self.assertEqual(len(memory["entries"]), 2)

    def test_full_personalization_enables_all_layers(self):
        plan = build_personalization_plan(
            {"mastery": 0.35, "attention": 0.4, "cognitiveLoad": 0.8},
            {"interestDomain": "robotics"},
            "G5",
        )
        self.assertTrue(all(plan["enabledLayers"].values()))
        self.assertEqual(plan["plan"]["difficulty"], "foundational")
        self.assertEqual(plan["plan"]["cueIntensity"], "high")
        self.assertEqual(plan["plan"]["pacing"], "slower")

    def test_adaptive_alignment_requires_reasoning_for_low_mastery(self):
        result = check_pedagogical_alignment(
            {"mastery": 0.4, "attention": 0.8},
            {"requestsDirectAnswer": True, "studentReasoning": ""},
            "H4",
        )
        self.assertEqual(result["policy"], "require_self_explanation")
        self.assertTrue(result["studentReasoningRequired"])

    def test_prescreen_rejects_temporal_misalignment(self):
        result = prescreen_candidate(
            {"constraintSatisfaction": 1.0},
            {"temporalAlignment": 0.5, "semanticAlignment": 1.0},
            "I0",
        )
        self.assertFalse(result["passed"])
        self.assertIn("temporal_alignment", result["failures"])
        self.assertTrue(result["requiresHumanCalibration"])


if __name__ == "__main__":
    unittest.main()
