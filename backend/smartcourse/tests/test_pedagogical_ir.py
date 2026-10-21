from __future__ import annotations

import unittest

from app.code_lessons import get_lesson_spec
from app.pedagogical_ir import (
    PedagogicalIRCompiler,
    build_e2_variants,
    compile_lesson_ir,
    compile_course_structure_ir,
    evaluate_pedagogical_ir,
)


class PedagogicalIRTests(unittest.TestCase):
    def setUp(self):
        self.spec = get_lesson_spec("linear-function")

    def test_a4_contains_explicit_multimodal_teaching_fields(self):
        ir = PedagogicalIRCompiler().compile(self.spec, "A4")
        self.assertEqual(ir["experiment"]["condition"], "A4")
        self.assertEqual(ir["timeline"]["eventCount"], 18)
        event = ir["timeline"]["events"][0]
        self.assertTrue(event["concept"])
        self.assertTrue(event["teachingIntent"])
        self.assertTrue(event["visual"]["target"])
        self.assertTrue(event["cue"]["enabled"])
        self.assertTrue(event["instructorBehavior"]["enabled"])
        self.assertEqual(event["instructorBehavior"]["gazeTarget"], event["visual"]["target"])

    def test_e1_conditions_enable_theory_incrementally(self):
        a1 = PedagogicalIRCompiler().compile(self.spec, "A1")
        a3 = PedagogicalIRCompiler().compile(self.spec, "A3")
        a4 = PedagogicalIRCompiler().compile(self.spec, "A4")
        self.assertFalse(any(a1["theoryProfile"]["enabled"].values()))
        self.assertTrue(a3["theoryProfile"]["enabled"]["ctml"])
        self.assertFalse(a3["theoryProfile"]["enabled"]["socialAgency"])
        self.assertTrue(a4["theoryProfile"]["enabled"]["socialAgency"])

    def test_a4_constraint_report_passes(self):
        ir, report = compile_lesson_ir(self.spec, "A4")
        self.assertTrue(report["valid"])
        self.assertEqual(report["constraintSatisfaction"], 1.0)
        self.assertEqual(report["temporalAlignment"], 1.0)
        self.assertEqual(report["semanticAlignment"], 1.0)
        self.assertEqual(evaluate_pedagogical_ir(ir), report)

    def test_e2_variants_have_expected_channels(self):
        ir, _ = compile_lesson_ir(self.spec, "A4")
        variants = build_e2_variants(ir)["variants"]
        first = lambda condition: variants[condition]["ir"]["timeline"]["events"][0]
        self.assertFalse(first("B0")["cue"]["enabled"])
        self.assertFalse(first("B0")["instructorBehavior"]["enabled"])
        self.assertTrue(first("B1")["cue"]["enabled"])
        self.assertFalse(first("B1")["instructorBehavior"]["enabled"])
        self.assertFalse(first("B2")["cue"]["enabled"])
        self.assertTrue(first("B2")["instructorBehavior"]["enabled"])
        self.assertTrue(first("B4")["cue"]["enabled"])
        self.assertTrue(first("B4")["instructorBehavior"]["enabled"])

    def test_misaligned_condition_scores_lower_than_aligned_condition(self):
        ir, _ = compile_lesson_ir(self.spec, "A4")
        variants = build_e2_variants(ir)["variants"]
        self.assertLess(
            variants["B3"]["evaluation"]["temporalAlignment"],
            variants["B4"]["evaluation"]["temporalAlignment"],
        )
        self.assertEqual(variants["B4"]["evaluation"]["temporalAlignment"], 1.0)

    def test_adaptive_condition_contains_learner_state_trigger(self):
        ir, _ = compile_lesson_ir(self.spec, "A4")
        variants = build_e2_variants(ir)["variants"]
        event = variants["B5"]["ir"]["timeline"]["events"][0]
        self.assertTrue(event["learnerStateTrigger"]["enabled"])
        self.assertEqual(len(event["learnerStateTrigger"]["conditions"]), 2)

    def test_s1_course_structure_uses_same_ir_for_upload_and_topic_modes(self):
        structure = {
            "task_id": "task_upload",
            "input_mode": "existing_pptx",
            "course_topic": "人工智能概述",
            "pages": [
                {
                    "page_id": 1,
                    "title": "人工智能的定义",
                    "key_points": ["感知", "推理", "行动"],
                    "script_text": "人工智能系统通过感知、推理和行动完成任务。",
                    "layout": {
                        "regions": [
                            {"name": "title"},
                            {"name": "reasoning"},
                            {"name": "action"},
                        ]
                    },
                }
            ],
        }
        ir, report = compile_course_structure_ir(structure, "A4")
        self.assertEqual(ir["source"]["stage"], "S1")
        self.assertEqual(ir["source"]["inputMode"], "existing_pptx")
        self.assertEqual(ir["timeline"]["eventCount"], 3)
        self.assertEqual(ir["timeline"]["events"][0]["visual"]["target"], "title")
        self.assertTrue(report["valid"])


if __name__ == "__main__":
    unittest.main()
