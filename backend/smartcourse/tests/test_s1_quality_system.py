from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.course_agent import CourseStructureAgent
from app.s1_quality_system import AGENT_ROLES, RESEARCH_DIRECTIONS, S1QualitySystem


def brief():
    return {
        "course_thesis": "模型需要在未见样本上保持有效。",
        "target_learners": "高校本科生",
        "prerequisites": ["函数与坐标系"],
        "sections": [{"section_id": "S01", "title": "泛化"}],
        "terminology": [
            {
                "term_id": "T001",
                "canonical_zh": "过拟合",
                "canonical_en": "overfitting",
                "definition": "模型过度适应训练数据",
                "forbidden_variants": [],
            }
        ],
    }


def page():
    return {
        "page_id": 1,
        "section_id": "S01",
        "title": "训练误差很低，换一批数据为什么失效？",
        "key_points": ["训练误差描述已见样本", "验证误差描述新样本表现"],
        "script_text": "先看训练曲线。再看验证曲线。两条曲线分离时，模型正在记住训练样本。",
        "opening_question": "训练集准确率高就够了吗？",
        "worked_example": "比较训练曲线和验证曲线",
        "terminology_used": ["T001"],
        "source_unit_ids": ["u-overfit"],
        "visual_plan": {
            "type": "manim",
            "objects": ["训练曲线", "验证曲线", "分离位置"],
            "sequence": ["显示训练曲线", "显示验证曲线", "标出分离位置"],
            "focus_cues": ["训练曲线", "验证曲线", "分离位置"],
        },
        "page_spec": {
            "teaching_goal": "识别过拟合",
            "content_role": "explain",
            "retrieval_query": "过拟合 训练误差 验证误差",
            "visual_type": "manim",
            "assessment_hook": "指出验证误差开始上升的位置",
        },
        "quality_audit": {"passed": True, "issueCount": 0},
        "rewrite_rounds": 0,
    }


class S1QualitySystemTests(unittest.TestCase):
    def setUp(self):
        self.system = S1QualitySystem()

    def test_all_research_directions_and_agent_roles_are_registered(self):
        self.assertEqual(len(RESEARCH_DIRECTIONS), 9)
        self.assertEqual(len(AGENT_ROLES), 9)
        self.assertEqual(len({item["id"] for item in RESEARCH_DIRECTIONS}), 9)
        self.assertTrue(all(item["url"].startswith("https://") for item in RESEARCH_DIRECTIONS))

    def test_page_is_enriched_with_manim_timeline_assets_and_slide_spec(self):
        learner = self.system.build_learner_model(brief())
        value = self.system.enrich_page(page(), brief(), learner)
        scene = value["manim_scene_spec"]
        self.assertEqual(scene["renderer"], "manim")
        self.assertEqual(len(scene["symbol_ledger"]), 1)
        self.assertEqual(len(scene["animation_events"]), 3)
        self.assertEqual(scene["safe_regions"]["avatarPlacement"], "dynamic_by_content_regions")
        self.assertEqual(value["slide_spec"]["sourceUnitIds"], ["u-overfit"])
        self.assertEqual(value["multimodal_asset_request"]["status"], "request_ready")

    def test_learning_evaluation_uses_page_assessment_and_sources(self):
        value = self.system.build_learning_evaluation(brief(), [page()])
        self.assertEqual(len(value["quizItems"]), 1)
        self.assertEqual(value["quizItems"][0]["sourceUnitIds"], ["u-overfit"])
        self.assertEqual(value["teachQuiz"]["status"], "spec_ready")
        self.assertTrue(value["humanEvaluation"]["required"])

    def test_render_review_memory_and_research_coverage_are_saved(self):
        learner = self.system.build_learner_model(brief())
        enriched = self.system.enrich_page(page(), brief(), learner)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pptx = root / "course.pptx"
            CourseStructureAgent._write_pptx([enriched], pptx)
            report = self.system.inspect_pptx(pptx, [enriched], brief(), root)
            self.assertEqual(report["pageCount"], 1)
            self.assertTrue((root / "rendered_slides" / "slide_001.png").is_file())
            memory = self.system.update_experience_memory(
                root / "memory.json", [enriched], report
            )
            self.assertEqual(len(memory["positive"]) + len(memory["negative"]), 1)
            coverage = self.system.research_coverage([enriched], report)
            self.assertEqual(len(coverage["directions"]), 9)
            self.assertEqual(
                coverage["directions"][5]["status"],
                "scene_specs_ready_renderer_required",
            )


if __name__ == "__main__":
    unittest.main()
