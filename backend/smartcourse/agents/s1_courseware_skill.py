"""智课工坊 S1 教学课件生成规则。

该模块先形成教师备课方案，再约束大纲、逐页内容、术语和视觉计划。
它不负责调用具体模型，也不负责渲染 PPT。
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoursewareSkillConfig:
    default_target_learners: str = "高校本科生"
    default_duration_minutes: int = 45
    max_sections: int = 6
    page_rewrite_limit: int = 2


class S1CoursewareSkill:
    """为 S1 课程生成智能体提供备课、写作和质量检查规则。"""

    MARKETING_TERMS = (
        "赋能",
        "重塑",
        "全面提升",
        "全链路",
        "一站式",
        "深度融合",
        "全方位",
        "核心引擎",
        "开启新时代",
        "未来已来",
        "革命性",
        "颠覆性",
    )

    GENERIC_TITLES = (
        "一张图看懂",
        "核心问题",
        "关键路径",
        "全景解析",
        "深度解读",
        "重新定义",
        "从入门到精通",
    )

    def __init__(self, config: CoursewareSkillConfig | None = None):
        self.config = config or CoursewareSkillConfig()
        self._contrast_pattern = re.compile("不" + "是.{0,36}而" + "是")

    @staticmethod
    def compact_rag_context(context: dict[str, Any] | None, limit: int = 10) -> dict[str, Any]:
        context = context or {}
        units = []
        for item in list(context.get("knowledgeUnits") or [])[:limit]:
            units.append(
                {
                    "knowledgeId": item.get("knowledgeId"),
                    "title": item.get("title"),
                    "content": item.get("content"),
                    "sourceId": item.get("sourceId"),
                    "sourceName": item.get("sourceName"),
                    "sourcePage": item.get("sourcePage"),
                    "sourceUrl": item.get("sourceUrl"),
                    "terms": item.get("terms", []),
                    "formulas": item.get("formulas", []),
                }
            )
        return {
            "query": context.get("query", ""),
            "knowledgeUnits": units,
            "allowedTerms": list(context.get("allowedTerms") or []),
            "allowedFormulas": list(context.get("allowedFormulas") or []),
            "sources": list(context.get("sources") or []),
        }

    def brief_messages(
        self,
        topic: str,
        total_pages: int,
        language: str,
        rag_context: dict[str, Any] | None,
        *,
        target_learners: str | None = None,
        duration_minutes: int | None = None,
    ) -> list[dict[str, str]]:
        learners = target_learners or self.config.default_target_learners
        duration = duration_minutes or self.config.default_duration_minutes
        payload = {
            "courseTopic": topic,
            "targetLearners": learners,
            "durationMinutes": duration,
            "contentPageCount": total_pages,
            "language": language,
            "ragContext": self.compact_rag_context(rag_context, limit=14),
        }
        schema = {
            "course_thesis": "本节课希望学生最终形成的一个明确认识",
            "teaching_purpose": "完成课程后学生能解释、判断或完成什么任务",
            "target_learners": learners,
            "duration_minutes": duration,
            "prerequisites": ["必要先修知识"],
            "learner_questions": ["学生进入课堂时可能提出的问题"],
            "sections": [
                {
                    "section_id": "S01",
                    "title": "自然、具体的章节标题",
                    "section_question": "本部分回答的真实问题",
                    "teaching_task": "教师在本部分完成的教学任务",
                    "page_budget": 3,
                    "content_sequence": ["案例", "观察", "解释", "应用"],
                    "visual_strategy": ["原始图表或 Manim 场景"],
                    "retrieval_query": "用于课程知识库检索的查询",
                    "assessment": "本部分结束时的判断题、选择题或解释任务",
                }
            ],
            "terminology": [
                {
                    "term_id": "T001",
                    "canonical_zh": "规范中文术语",
                    "canonical_en": "English term",
                    "definition": "适合目标学习者的准确定义",
                    "first_use_section": "S01",
                    "allowed_aliases": [],
                    "forbidden_variants": [],
                    "source_unit_ids": ["知识单元编号"],
                }
            ],
            "voice_profile": {
                "teacher_role": "具备学科背景的高校教师",
                "sentence_style": ["自然提问", "具体案例", "逐步解释", "必要总结"],
                "avoid": ["口号", "产品宣传语", "机械排比", "机械对比句", "无来源数字"],
            },
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是智课工坊的课程主编。先完成教师备课方案，再允许生成页面。\n"
                    "备课方案必须围绕一个明确课程主旨组织。大纲应包含3至6个部分，每部分说明回答什么问题、采用什么案例、使用什么视觉载体以及如何检查学生理解。\n"
                    "建立课程术语表：规范中英文名称、定义、首次出现位置、允许别名、禁用写法和来源知识单元。\n"
                    "课程内容仅使用给定ragContext中的事实、术语、公式和数字；来源不足时标记needs_teacher_review。\n"
                    "语言采用真实高校教师备课语气。避免产品宣传、机械排比、口号、抽象空话和模板化标题。\n"
                    "输出严格JSON，不添加说明。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"input": payload, "outputSchema": schema}, ensure_ascii=False),
            },
        ]

    def outline_messages(
        self,
        brief: dict[str, Any],
        total_pages: int,
        language: str,
        section_contexts: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        schema = [
            {
                "chapter": "章节标题",
                "section_id": "S01",
                "section_question": "该部分回答的问题",
                "pages": [
                    {
                        "page_topic": "页面主题",
                        "teaching_goal": "学生看完本页能完成的具体任务",
                        "opening_question": "教师进入本页时提出的问题",
                        "content_role": "case|observe|explain|derive|apply|check|summary",
                        "retrieval_query": "本页知识检索问题",
                        "visual_type": "source_figure|data_chart|manim|graph|photo|text",
                        "visual_brief": "视觉对象、变化过程和重点位置",
                        "term_ids": ["T001"],
                        "assessment_hook": "用于检查理解的简短任务",
                    }
                ],
            }
        ]
        payload = {
            "brief": brief,
            "sectionContexts": {
                key: self.compact_rag_context(value, limit=8)
                for key, value in (section_contexts or {}).items()
            },
            "contentPageCount": total_pages,
            "language": language,
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是高校课程设计教师。依据已经确认的课程主旨和章节方案展开逐页大纲。\n"
                    "总页面数必须准确。每页只承担一个明确教学任务，页面之间具有自然承接关系。\n"
                    "页面标题写成教师实际会使用的标题，优先使用具体问题、案例对象或学科概念。\n"
                    "视觉载体由知识表达需要决定。算法、公式、空间关系和变化过程优先选择Manim或数据图；实物场景使用授权图片；已有教材图表优先复用。\n"
                    "不得为了版式整齐重复使用相同卡片结构。输出严格JSON。"
                ),
            },
            {"role": "user", "content": json.dumps({"input": payload, "outputSchema": schema}, ensure_ascii=False)},
        ]

    def page_messages(
        self,
        topic: str,
        brief: dict[str, Any],
        page_spec: dict[str, Any],
        language: str,
        rag_context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        term_ids = set(page_spec.get("term_ids") or [])
        terminology = [
            item for item in brief.get("terminology", [])
            if item.get("term_id") in term_ids
        ]
        schema = {
            "title": "具体、自然、无宣传语的页面标题",
            "key_points": ["2至4条可直接展示的简短内容"],
            "slide_body": "仅在确有必要时使用的短段落，不复述要点",
            "script_text": "教师能够直接朗读的自然讲稿",
            "opening_question": page_spec.get("opening_question", ""),
            "worked_example": "具体案例、数据、题目或推导步骤",
            "visual_plan": {
                "type": page_spec.get("visual_type", "text"),
                "objects": ["画面中必须出现的对象"],
                "sequence": ["视觉对象出现和变化的顺序"],
                "focus_cues": ["与讲稿对应的视觉重点"],
                "manim_requirements": ["需要代码生成时的数学对象和动画要求"],
            },
            "terminology_used": ["T001"],
            "source_unit_ids": ["来源知识单元编号"],
            "needs_teacher_review": False,
        }
        payload = {
            "courseTopic": topic,
            "courseThesis": brief.get("course_thesis"),
            "voiceProfile": brief.get("voice_profile"),
            "pageSpec": page_spec,
            "terminology": terminology,
            "ragContext": self.compact_rag_context(rag_context, limit=8),
            "language": language,
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是正在备课的高校教师。生成一页可用于正式授课的课件内容。\n"
                    "先提出具体问题或展示案例，再引导学生观察，随后解释概念；需要推导时逐步展开。\n"
                    "讲稿应像教师面对学生讲话，可以使用短句、停顿、追问和指向画面的表达。避免摘要腔、产品文案、口号和机械排比。\n"
                    "每个专业术语严格采用terminology中的规范写法，第一次出现时给出简短定义。\n"
                    "所有事实、数字、公式和专有名词必须来自ragContext，并返回对应source_unit_ids。\n"
                    "视觉计划必须说明画面对象和变化顺序，不能只写抽象风格词。\n"
                    "输出严格JSON。"
                ),
            },
            {"role": "user", "content": json.dumps({"input": payload, "outputSchema": schema}, ensure_ascii=False)},
        ]

    def rewrite_messages(
        self,
        page: dict[str, Any],
        audit: dict[str, Any],
        brief: dict[str, Any],
        rag_context: dict[str, Any] | None,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "你是课程文字编辑。只修改检查报告指出的问题，保持原有知识、术语、来源编号和视觉计划。\n"
                    "删除宣传语、机械句式和抽象空话，将内容改成教师能够自然讲出的中文。\n"
                    "不得引入新的事实、数字、术语或来源。输出完整JSON。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "page": page,
                        "audit": audit,
                        "courseThesis": brief.get("course_thesis"),
                        "ragContext": self.compact_rag_context(rag_context, limit=8),
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def repair_page_deterministically(
        self,
        page: dict[str, Any],
        audit: dict[str, Any],
    ) -> dict[str, Any]:
        value = deepcopy(page)
        issue_types = {str(item.get("type")) for item in audit.get("issues", [])}
        if "generic_title" in issue_types:
            page_spec = value.get("page_spec") or {}
            replacement = str(
                value.get("opening_question")
                or page_spec.get("page_topic")
                or page_spec.get("teaching_goal")
                or ""
            ).strip()
            if replacement:
                value["title"] = replacement

        def edit_text(text: str) -> str:
            result = str(text or "")
            if "mechanical_contrast" in issue_types:
                pattern = re.compile(
                    "不" + "是(?:只)?(?P<left>[^，,。！？；;]{1,48})[，,]\\s*而" + "是(?P<right>[^。！？；;]+)"
                )

                def replace(match: re.Match[str]) -> str:
                    left = match.group("left").strip()
                    right = match.group("right").strip()
                    if any(right.startswith(token) for token in ("进入", "采用", "要求", "面向", "用于", "需要")):
                        return right
                    if any(right.startswith(token) for token in ("一种", "一项", "一个", "一门", "一类")):
                        return "是" + right
                    return f"这里同时涉及{left}，重点在于{right}"

                result = pattern.sub(replace, result)
            if "marketing_phrase" in issue_types:
                replacements = {
                    "赋能": "支持",
                    "重塑": "改变",
                    "全面提升": "提高",
                    "全链路": "各环节",
                    "一站式": "集中",
                    "深度融合": "结合",
                    "全方位": "多方面",
                    "核心引擎": "主要模块",
                    "开启新时代": "进入新的发展阶段",
                    "未来已来": "相关应用已经出现",
                    "革命性": "显著",
                    "颠覆性": "显著",
                }
                for source, target in replacements.items():
                    result = result.replace(source, target)
            return result

        for key in ("title", "slide_body", "script_text", "worked_example"):
            if isinstance(value.get(key), str):
                value[key] = edit_text(value[key])
        value["key_points"] = [edit_text(str(item)) for item in value.get("key_points", [])]
        value["deterministic_style_repair"] = sorted(
            issue_types & {"mechanical_contrast", "marketing_phrase", "generic_title"}
        )
        return value

    def audit_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        values = [
            str(brief.get("course_thesis", "")),
            str(brief.get("teaching_purpose", "")),
        ]
        for section in brief.get("sections", []) or []:
            values.extend(
                [
                    str(section.get("title", "")),
                    str(section.get("section_question", "")),
                    str(section.get("teaching_task", "")),
                    str(section.get("assessment", "")),
                ]
            )
        for term in brief.get("terminology", []) or []:
            values.extend(
                [
                    str(term.get("canonical_zh", "")),
                    str(term.get("canonical_en", "")),
                    str(term.get("definition", "")),
                ]
            )
        content = "\n".join(value for value in values if value)
        issues = []
        if self._contrast_pattern.search(content):
            issues.append({"type": "mechanical_contrast", "message": "备课方案使用了机械对比句式"})
        for term in self.MARKETING_TERMS:
            if term in content:
                issues.append({"type": "marketing_phrase", "term": term})
        section_count = len(brief.get("sections", []) or [])
        duration_minutes = int(brief.get("duration_minutes", 0) or 0)
        minimum_sections = 3 if duration_minutes >= 30 else 1
        if not minimum_sections <= section_count <= self.config.max_sections:
            issues.append({"type": "section_count", "count": section_count})
        for section in brief.get("sections", []) or []:
            missing = [
                key
                for key in (
                    "section_id",
                    "title",
                    "section_question",
                    "teaching_task",
                    "visual_strategy",
                    "retrieval_query",
                    "assessment",
                )
                if not section.get(key)
            ]
            if missing:
                issues.append(
                    {
                        "type": "incomplete_section_plan",
                        "sectionId": section.get("section_id"),
                        "missing": missing,
                    }
                )
        for term in brief.get("terminology", []) or []:
            if not term.get("term_id") or not term.get("canonical_zh") or not term.get("definition"):
                issues.append(
                    {
                        "type": "incomplete_terminology",
                        "termId": term.get("term_id"),
                    }
                )
        return {
            "passed": not issues,
            "issueCount": len(issues),
            "issues": issues,
        }

    def repair_brief_deterministically(
        self,
        brief: dict[str, Any],
        audit: dict[str, Any],
    ) -> dict[str, Any]:
        value = deepcopy(brief)
        issue_types = {str(item.get("type")) for item in audit.get("issues", [])}

        def edit_text(text: str) -> str:
            page = {
                "title": "",
                "slide_body": str(text or ""),
                "script_text": "",
                "key_points": [],
                "opening_question": "",
                "worked_example": "",
                "visual_plan": {},
                "page_spec": {},
            }
            repaired = self.repair_page_deterministically(
                page,
                {
                    "issues": [
                        {"type": item}
                        for item in issue_types
                        if item in {"mechanical_contrast", "marketing_phrase"}
                    ]
                },
            )
            return str(repaired.get("slide_body", ""))

        for key in ("course_thesis", "teaching_purpose"):
            value[key] = edit_text(str(value.get(key, "")))
        for section in value.get("sections", []) or []:
            for key in ("title", "section_question", "teaching_task", "assessment"):
                if isinstance(section.get(key), str):
                    section[key] = edit_text(section[key])
        for term in value.get("terminology", []) or []:
            if isinstance(term.get("definition"), str):
                term["definition"] = edit_text(term["definition"])
        value["style_audit"] = self.audit_brief(value)
        return value

    @staticmethod
    def _page_text(page: dict[str, Any]) -> str:
        values = [
            str(page.get("title", "")),
            *[str(item) for item in page.get("key_points", [])],
            str(page.get("slide_body", "")),
            str(page.get("script_text", "")),
        ]
        return "\n".join(item for item in values if item).strip()

    def audit_page(self, page: dict[str, Any], terminology: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        text = self._page_text(page)
        issues: list[dict[str, Any]] = []
        if self._contrast_pattern.search(text):
            issues.append({"type": "mechanical_contrast", "message": "使用了机械对比句式"})
        for term in self.MARKETING_TERMS:
            if term in text:
                issues.append({"type": "marketing_phrase", "term": term})
        title = str(page.get("title", "")).strip()
        for value in self.GENERIC_TITLES:
            if value in title:
                issues.append({"type": "generic_title", "term": value})
        if title.count(":") + title.count("：") > 1:
            issues.append({"type": "title_punctuation", "message": "标题包含过多分隔符"})
        if len(page.get("key_points", [])) > 5:
            issues.append({"type": "excessive_bullets", "count": len(page.get("key_points", []))})
        if len(str(page.get("slide_body", ""))) > 180:
            issues.append({"type": "dense_slide_body", "length": len(str(page.get("slide_body", "")))})
        if not page.get("opening_question") and not page.get("worked_example"):
            issues.append({"type": "missing_teaching_entry", "message": "缺少问题或案例入口"})
        visual_plan = page.get("visual_plan") or {}
        if not visual_plan.get("objects") or not visual_plan.get("sequence"):
            issues.append({"type": "abstract_visual_plan", "message": "视觉计划缺少对象或变化顺序"})
        page_spec = page.get("page_spec") or {}
        if not page_spec.get("teaching_goal"):
            issues.append({"type": "missing_teaching_goal", "message": "页面缺少可检查的教学目标"})
        if not page_spec.get("assessment_hook") and not page.get("assessment_hook"):
            issues.append({"type": "missing_assessment_hook", "message": "页面缺少理解检查任务"})
        allowed_source_ids = {str(item.get("knowledgeId")) for item in (page.get("rag_context") or {}).get("knowledgeUnits", [])}
        returned_source_ids = {str(item) for item in page.get("source_unit_ids", [])}
        if allowed_source_ids and not returned_source_ids:
            issues.append({"type": "missing_source_units", "message": "页面未返回来源知识单元"})
        if allowed_source_ids and returned_source_ids - allowed_source_ids:
            issues.append(
                {
                    "type": "unknown_source_units",
                    "values": sorted(returned_source_ids - allowed_source_ids),
                }
            )
        term_map = {str(item.get("term_id")): item for item in (terminology or [])}
        for term_id in page.get("terminology_used", []):
            if str(term_id) not in term_map:
                issues.append({"type": "unknown_term_id", "value": term_id})
        for item in terminology or []:
            for forbidden in item.get("forbidden_variants", []) or []:
                if forbidden and forbidden in text:
                    issues.append(
                        {
                            "type": "forbidden_term_variant",
                            "term_id": item.get("term_id"),
                            "value": forbidden,
                        }
                    )
        severity = sum(2 if item["type"] in {"unknown_source_units", "unknown_term_id"} else 1 for item in issues)
        return {
            "passed": not issues,
            "issueCount": len(issues),
            "severity": severity,
            "issues": issues,
        }

    def audit_deck(self, brief: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
        terminology = list(brief.get("terminology") or [])
        page_reports = [self.audit_page(page, terminology) for page in pages]
        issue_count = sum(item["issueCount"] for item in page_reports)
        thesis = str(brief.get("course_thesis", "")).strip()
        section_ids = {str(item.get("section_id")) for item in brief.get("sections", [])}
        covered_sections = {str(page.get("section_id")) for page in pages if page.get("section_id")}
        deck_issues = []
        if not thesis:
            deck_issues.append({"type": "missing_course_thesis"})
        missing_sections = sorted(section_ids - covered_sections)
        if missing_sections:
            deck_issues.append({"type": "missing_sections", "values": missing_sections})
        return {
            "passed": issue_count == 0 and not deck_issues,
            "courseThesis": thesis,
            "sectionCount": len(section_ids),
            "pageCount": len(pages),
            "pageIssueCount": issue_count,
            "deckIssues": deck_issues,
            "pages": [
                {"pageId": page.get("page_id"), **report}
                for page, report in zip(pages, page_reports)
            ],
        }
