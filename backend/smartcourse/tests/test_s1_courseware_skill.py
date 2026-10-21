from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agents.s1_courseware_skill import S1CoursewareSkill
from agents import s1_ppt_generator
from app.course_agent import CourseStructureAgent
from app.s1_quality_system import S1QualitySystem


def rag_context():
    return {
        "query": "什么是过拟合",
        "knowledgeUnits": [
            {
                "knowledgeId": "u-overfit",
                "title": "过拟合",
                "content": "过拟合表现为训练误差较低而验证误差升高。",
                "sourceId": "google-generalization",
                "sourceName": "Google MLCC",
                "sourcePage": None,
                "sourceUrl": "https://developers.google.com/machine-learning/crash-course/overfitting",
            }
        ],
        "allowedTerms": ["过拟合", "训练误差", "验证误差"],
        "allowedFormulas": [],
        "sources": [],
    }


class S1CoursewareSkillTests(unittest.TestCase):
    def setUp(self):
        self.skill = S1CoursewareSkill()
        self.brief = {
            "course_thesis": "模型在已知数据上表现良好，并不保证它能处理新样本。",
            "sections": [
                {
                    "section_id": "S01",
                    "title": "训练结果为什么会失效",
                    "section_question": "模型为什么记住训练样本",
                }
            ],
            "terminology": [
                {
                    "term_id": "T001",
                    "canonical_zh": "过拟合",
                    "canonical_en": "overfitting",
                    "definition": "模型过度适应训练数据",
                    "allowed_aliases": [],
                    "forbidden_variants": ["过度拟合"],
                }
            ],
            "voice_profile": {"teacher_role": "高校教师"},
        }

    def test_course_brief_prompt_requires_thesis_sections_and_terms(self):
        messages = self.skill.brief_messages(
            "机器学习基础",
            12,
            "zh-CN",
            rag_context(),
            target_learners="非计算机专业一年级学生",
            duration_minutes=50,
        )
        self.assertIn("课程主旨", messages[0]["content"])
        self.assertIn("术语表", messages[0]["content"])
        self.assertIn("u-overfit", messages[1]["content"])
        self.assertIn("50", messages[1]["content"])

    def test_page_prompt_includes_teacher_voice_terms_and_rag_units(self):
        spec = {
            "section_id": "S01",
            "page_topic": "训练误差低为什么仍然失败",
            "opening_question": "训练集准确率接近满分就够了吗？",
            "visual_type": "manim",
            "term_ids": ["T001"],
        }
        messages = self.skill.page_messages(
            "机器学习基础",
            self.brief,
            spec,
            "zh-CN",
            rag_context(),
        )
        self.assertIn("高校教师", messages[1]["content"])
        self.assertIn("过拟合", messages[1]["content"])
        self.assertIn("u-overfit", messages[1]["content"])
        self.assertIn("visual_plan", messages[1]["content"])

    def test_audit_rejects_marketing_style_and_unknown_sources(self):
        page = {
            "page_id": 1,
            "title": "一张图看懂过拟合",
            "key_points": ["全面提升模型能力", "训练效果实现深度融合"],
            "slide_body": "这" + "不" + "是普通模型，" + "而" + "是革命性核心引擎。",
            "script_text": "",
            "opening_question": "训练集准确率高就够了吗？",
            "visual_plan": {"objects": ["训练曲线"], "sequence": ["显示曲线"]},
            "terminology_used": ["T001"],
            "source_unit_ids": ["unknown"],
            "rag_context": rag_context(),
        }
        report = self.skill.audit_page(page, self.brief["terminology"])
        self.assertFalse(report["passed"])
        issue_types = {item["type"] for item in report["issues"]}
        self.assertIn("mechanical_contrast", issue_types)
        self.assertIn("marketing_phrase", issue_types)
        self.assertIn("generic_title", issue_types)
        self.assertIn("unknown_source_units", issue_types)

    def test_audit_accepts_specific_teacher_page(self):
        page = {
            "page_id": 1,
            "section_id": "S01",
            "title": "训练误差很低，换一批数据为什么失效？",
            "key_points": ["训练误差只描述已见样本", "验证误差反映模型对新样本的表现"],
            "slide_body": "",
            "script_text": "先看两条误差曲线。训练曲线继续下降时，验证曲线开始上升，这时模型正在记住训练样本。",
            "opening_question": "训练集准确率高就够了吗？",
            "worked_example": "比较训练集与验证集误差曲线",
            "visual_plan": {
                "objects": ["训练曲线", "验证曲线"],
                "sequence": ["先显示训练曲线", "再显示验证曲线", "标出分离位置"],
            },
            "page_spec": {
                "teaching_goal": "识别过拟合",
                "assessment_hook": "指出验证误差开始上升的位置",
            },
            "terminology_used": ["T001"],
            "source_unit_ids": ["u-overfit"],
            "rag_context": rag_context(),
        }
        report = self.skill.audit_page(page, self.brief["terminology"])
        self.assertTrue(report["passed"], report)

    def test_deterministic_repair_removes_mechanical_style_without_new_facts(self):
        page = {
            "title": "一张图看懂课程定位",
            "slide_body": "这" + "不" + "是专业课，" + "而" + "是进入公共基础课序列。",
            "script_text": "人工智能课程将全面提升学生能力。",
            "key_points": [],
            "opening_question": "这门课为什么进入公共基础课？",
            "worked_example": "阅读课程文件原句",
            "visual_plan": {"objects": ["文件原句"], "sequence": ["标出课程定位"]},
            "page_spec": {
                "page_topic": "课程定位",
                "teaching_goal": "说明课程对象",
                "assessment_hook": "指出课程面向哪些学生",
            },
        }
        audit = self.skill.audit_page(page, [])
        repaired = self.skill.repair_page_deterministically(page, audit)
        self.assertEqual(repaired["title"], page["opening_question"])
        self.assertNotIn("全面提升", repaired["script_text"])
        self.assertNotRegex(repaired["slide_body"], self.skill._contrast_pattern)

    def test_course_brief_style_is_checked_and_repaired(self):
        value = {
            **self.brief,
            "course_thesis": "人工智能" + "不" + "是专业课，" + "而" + "是一种通用素养。",
            "teaching_purpose": "提高学生判断能力。",
            "sections": [
                {
                    "section_id": f"S{index:02d}",
                    "title": f"第{index}部分",
                    "section_question": "学生需要回答什么问题？",
                    "teaching_task": "讲解一个具体概念",
                    "visual_strategy": ["Manim"],
                    "retrieval_query": "课程知识",
                    "assessment": "完成一个判断题",
                }
                for index in range(1, 4)
            ],
        }
        audit = self.skill.audit_brief(value)
        self.assertFalse(audit["passed"])
        repaired = self.skill.repair_brief_deterministically(value, audit)
        self.assertNotRegex(repaired["course_thesis"], self.skill._contrast_pattern)
        self.assertTrue(repaired["style_audit"]["passed"])

    def test_deck_audit_checks_course_thesis_and_section_coverage(self):
        report = self.skill.audit_deck(self.brief, [{"page_id": 1, "section_id": "S01"}])
        self.assertTrue(report["courseThesis"])
        self.assertEqual(report["sectionCount"], 1)
        self.assertEqual(report["deckIssues"], [])


class S1CoursewarePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_requires_brief_then_outline_then_grounded_page(self):
        brief = {
            "course_thesis": "模型必须在未见样本上保持有效。",
            "teaching_purpose": "能够识别过拟合并选择验证方法。",
            "sections": [
                {
                    "section_id": "S01",
                    "title": "训练结果为什么会失效",
                    "section_question": "训练集表现很好为什么仍会失败",
                    "teaching_task": "比较训练误差与验证误差",
                    "visual_strategy": ["Manim 曲线"],
                    "retrieval_query": "过拟合 训练误差 验证误差",
                    "assessment": "指出过拟合开始的位置",
                }
            ],
            "terminology": [
                {
                    "term_id": "T001",
                    "canonical_zh": "过拟合",
                    "canonical_en": "overfitting",
                    "definition": "模型过度适应训练数据",
                    "allowed_aliases": [],
                    "forbidden_variants": [],
                }
            ],
            "voice_profile": {"teacher_role": "高校教师"},
        }
        outline = [
            {
                "chapter": "训练结果为什么会失效",
                "section_id": "S01",
                "section_question": "训练集表现很好为什么仍会失败",
                "pages": [
                    {
                        "page_topic": "训练误差很低，换一批数据为什么失效？",
                        "teaching_goal": "识别过拟合",
                        "opening_question": "训练集准确率高就够了吗？",
                        "content_role": "explain",
                        "retrieval_query": "过拟合 训练误差 验证误差",
                        "visual_type": "manim",
                        "visual_brief": "比较训练曲线和验证曲线",
                        "term_ids": ["T001"],
                        "assessment_hook": "判断哪条曲线代表过拟合",
                    }
                ],
            }
        ]
        page = {
            "title": "训练误差很低，换一批数据为什么失效？",
            "key_points": ["训练误差描述已见样本", "验证误差描述新样本表现"],
            "slide_body": "",
            "script_text": "先看两条曲线。验证误差开始上升时，模型正在记住训练样本。",
            "opening_question": "训练集准确率高就够了吗？",
            "worked_example": "比较训练曲线和验证曲线",
            "visual_plan": {
                "type": "manim",
                "objects": ["训练曲线", "验证曲线"],
                "sequence": ["显示训练曲线", "显示验证曲线", "标出分离位置"],
                "focus_cues": ["分离位置"],
                "manim_requirements": ["坐标轴与曲线"],
            },
            "terminology_used": ["T001"],
            "source_unit_ids": ["u-overfit"],
            "needs_teacher_review": False,
        }

        class FakeRAGService:
            def __init__(self):
                self.queries = []

            def query(self, payload):
                self.queries.append(payload)
                return {"context": rag_context()}

        service = FakeRAGService()
        fake_llm = AsyncMock(side_effect=[brief, outline, page])
        with patch.object(s1_ppt_generator, "call_llm_json", fake_llm):
            generated_brief, pages, report = await s1_ppt_generator.generate_all_content(
                "机器学习基础",
                1,
                "zh-CN",
                client=object(),
                rag_service=service,
                skill=S1CoursewareSkill(),
                require_rag=True,
            )
        self.assertEqual(generated_brief["course_thesis"], brief["course_thesis"])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["source_unit_ids"], ["u-overfit"])
        self.assertTrue(pages[0]["quality_audit"]["passed"])
        self.assertTrue(report["passed"])
        self.assertGreaterEqual(len(service.queries), 3)
        self.assertEqual(fake_llm.await_count, 3)


class CourseStructureAgentEnhancedTests(unittest.TestCase):
    def test_topic_mode_saves_brief_terms_rag_context_and_quality_report(self):
        brief = {
            "course_thesis": "模型必须在未见样本上保持有效。",
            "teaching_purpose": "识别过拟合。",
            "sections": [
                {
                    "section_id": "S01",
                    "title": "训练结果为什么会失效",
                    "section_question": "训练集表现很好为什么仍会失败",
                    "teaching_task": "比较训练误差与验证误差",
                    "visual_strategy": ["Manim 曲线"],
                    "retrieval_query": "过拟合 训练误差 验证误差",
                    "assessment": "指出过拟合开始的位置",
                }
            ],
            "terminology": [
                {
                    "term_id": "T001",
                    "canonical_zh": "过拟合",
                    "canonical_en": "overfitting",
                    "definition": "模型过度适应训练数据",
                    "allowed_aliases": [],
                    "forbidden_variants": [],
                }
            ],
            "voice_profile": {"teacher_role": "高校教师"},
        }
        outline = [
            {
                "chapter": "训练结果为什么会失效",
                "section_id": "S01",
                "pages": [
                    {
                        "page_topic": "训练误差很低，换一批数据为什么失效？",
                        "teaching_goal": "识别过拟合",
                        "opening_question": "训练集准确率高就够了吗？",
                        "retrieval_query": "过拟合 训练误差 验证误差",
                        "visual_type": "manim",
                        "visual_brief": "比较训练曲线和验证曲线",
                        "term_ids": ["T001"],
                        "assessment_hook": "指出验证误差开始上升的位置",
                    }
                ],
            }
        ]
        page = {
            "title": "训练误差很低，换一批数据为什么失效？",
            "key_points": ["训练误差描述已见样本", "验证误差描述新样本表现"],
            "slide_body": "",
            "script_text": "先看两条曲线。验证误差开始上升时，模型正在记住训练样本。",
            "opening_question": "训练集准确率高就够了吗？",
            "worked_example": "比较训练曲线和验证曲线",
            "visual_plan": {
                "type": "manim",
                "objects": ["训练曲线", "验证曲线"],
                "sequence": ["显示训练曲线", "显示验证曲线", "标出分离位置"],
                "focus_cues": ["分离位置"],
                "manim_requirements": ["坐标轴与曲线"],
            },
            "terminology_used": ["T001"],
            "source_unit_ids": ["u-overfit"],
            "needs_teacher_review": False,
        }

        class FakeGateway:
            def __init__(self):
                self.responses = iter([brief, outline, page])

            def respond_json(self, _prompt, **_kwargs):
                return next(self.responses)

        class FakeRAGService:
            def query(self, _payload):
                return {"context": rag_context()}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generated.pptx"
            result = CourseStructureAgent(
                FakeGateway(),
                rag_service=FakeRAGService(),
                courseware_skill=S1CoursewareSkill(),
                quality_system=S1QualitySystem(),
                experience_memory_path=output.parent / "shared-memory.json",
                require_rag=True,
            ).from_topic(
                "机器学习基础",
                "task-1",
                output,
                total_pages=1,
                language="Simplified Chinese",
            )
            self.assertTrue(output.is_file())
            self.assertTrue((output.parent / "course_brief.json").is_file())
            self.assertTrue((output.parent / "course_quality_report.json").is_file())
            self.assertTrue((output.parent / "visual_quality_report.json").is_file())
            self.assertTrue((output.parent / "learning_evaluation.json").is_file())
            self.assertTrue((output.parent / "research_coverage.json").is_file())
            self.assertTrue((output.parent / "shared-memory.json").is_file())
            self.assertEqual(result["course_thesis"], brief["course_thesis"])
            self.assertEqual(result["pages"][0]["source_unit_ids"], ["u-overfit"])
            self.assertTrue(result["quality_report"]["passed"])


if __name__ == "__main__":
    unittest.main()
