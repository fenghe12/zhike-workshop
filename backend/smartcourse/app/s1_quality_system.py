"""S1 课件生成研究规范、页面检查和课程级产物。

该模块把课件生成研究方向转换成智课工坊可保存、可检查的结构。
外部模型未配置时会明确记录为 pending，不会写成已完成。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from agents.ppt_renderer import occupied_regions, render_pptx_to_images


SCHEMA_VERSION = "2026.2"


RESEARCH_DIRECTIONS = [
    {
        "id": "narrative_planning",
        "title": "教学叙事规划",
        "reference": "Auto-Slides",
        "url": "https://arxiv.org/abs/2509.11062",
        "systemUse": "课程主旨、学习者、章节问题和页面教学角色",
    },
    {
        "id": "programmatic_slides",
        "title": "程序化页面生成",
        "reference": "AutoPresent",
        "url": "https://openaccess.thecvf.com/content/CVPR2025/papers/Ge_AutoPresent_Designing_Structured_Visuals_from_Scratch_CVPR_2025_paper.pdf",
        "systemUse": "可编辑文字、图片、图表、公式和版面对象",
    },
    {
        "id": "visual_feedback",
        "title": "渲染后视觉检查",
        "reference": "Seeing is Improving",
        "url": "https://openaccess.thecvf.com/content/CVPR2026/html/Guo_Seeing_is_Improving_Visual_Feedback_for_Iterative_Text_Layout_Refinement_CVPR_2026_paper.html",
        "systemUse": "页面渲染、边界、密度、对比度和 OCR 接口",
    },
    {
        "id": "visual_reward",
        "title": "多维视觉评分",
        "reference": "PosterReward",
        "url": "https://openaccess.thecvf.com/content/CVPR2026/html/Lai_PosterReward_Unlocking_Accurate_Evaluation_for_High-Quality_Graphic_Design_Generation_CVPR_2026_paper.html",
        "systemUse": "文字、布局、颜色、图文语义和生成痕迹分项评分",
    },
    {
        "id": "deck_structure",
        "title": "跨页结构检查",
        "reference": "PPTArena",
        "url": "https://arxiv.org/abs/2512.03042",
        "systemUse": "母版、字体、标题、术语和章节节奏一致性",
    },
    {
        "id": "code_visualization",
        "title": "代码驱动教学可视化",
        "reference": "Code2Video",
        "url": "https://arxiv.org/abs/2510.01174",
        "systemUse": "Planner、Coder、Critic 和 Manim 场景说明",
    },
    {
        "id": "narration_alignment",
        "title": "旁白与视觉事件对齐",
        "reference": "LLM2Manim",
        "url": "https://arxiv.org/abs/2604.05266",
        "systemUse": "符号表、旁白提示、动画事件和时间范围",
    },
    {
        "id": "multimodal_retrieval",
        "title": "多模态素材检索",
        "reference": "PresentAgent-2",
        "url": "https://arxiv.org/abs/2605.11363",
        "systemUse": "正文、原始图表、授权图片、GIF 和视频请求清单",
    },
    {
        "id": "experience_memory",
        "title": "跨任务经验记忆",
        "reference": "ManimAgent",
        "url": "https://arxiv.org/abs/2606.30296",
        "systemUse": "成功场景、失败模式、修改次数和人工结果",
    },
]


AGENT_ROLES = [
    "learner_modeling",
    "rag_research",
    "teaching_narrative",
    "visual_semantic_planning",
    "teacher_language",
    "manim_scene",
    "page_visual_review",
    "deck_review",
    "learning_evaluation",
]


def _sentences(value: str) -> list[str]:
    return [
        item.strip()
        for item in re.findall(r"[^。！？.!?]+[。！？.!?]?", value or "")
        if item.strip()
    ]


class S1QualitySystem:
    def build_learner_model(
        self,
        brief: dict[str, Any],
        learner_state: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = learner_state or {}
        pref = preferences or {}
        mastery = min(1.0, max(0.0, float(state.get("mastery", 0.5))))
        cognitive_load = min(
            1.0,
            max(0.0, float(state.get("cognitiveLoad", state.get("cognitive_load", 0.5)))),
        )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "targetLearners": brief.get("target_learners", "高校本科生"),
            "prerequisites": list(brief.get("prerequisites") or []),
            "mastery": mastery,
            "cognitiveLoad": cognitive_load,
            "misconceptions": list(state.get("misconceptions") or []),
            "interestDomain": pref.get("interestDomain", "general"),
            "explanationDepth": "foundational" if mastery < 0.45 else "advanced" if mastery > 0.8 else "standard",
            "exampleDensity": "high" if mastery < 0.6 else "standard",
            "pacing": "slower" if cognitive_load > 0.7 else "normal",
        }

    @staticmethod
    def build_multimodal_asset_request(page: dict[str, Any]) -> dict[str, Any]:
        spec = page.get("page_spec") or {}
        visual = page.get("visual_plan") or {}
        visual_type = str(visual.get("type") or spec.get("visual_type") or "text")
        objects = [str(item) for item in visual.get("objects", [])]
        return {
            "pageId": page.get("page_id"),
            "visualType": visual_type,
            "queries": {
                "sourceFigure": str(spec.get("retrieval_query", "")),
                "authorizedImage": " ".join([str(page.get("title", "")), *objects]).strip(),
                "gifOrVideo": " ".join([str(page.get("title", "")), "过程 动画"]).strip(),
            },
            "selectionOrder": [
                "teacher_source_figure",
                "official_or_authorized_media",
                "programmatic_visual",
                "decorative_generated_image",
            ],
            "licenseRequired": visual_type in {"photo", "source_figure", "video", "gif"},
            "dynamicMediaPreferred": bool(visual.get("sequence")) and visual_type in {"manim", "video", "gif"},
            "status": "request_ready",
        }

    @staticmethod
    def build_manim_scene_spec(
        page: dict[str, Any],
        brief: dict[str, Any],
        learner_model: dict[str, Any],
    ) -> dict[str, Any]:
        visual = page.get("visual_plan") or {}
        spec = page.get("page_spec") or {}
        terminology = {
            str(item.get("term_id")): item
            for item in brief.get("terminology", [])
        }
        symbol_ledger = []
        for term_id in page.get("terminology_used", []):
            term = terminology.get(str(term_id))
            if not term:
                continue
            symbol_ledger.append(
                {
                    "termId": term_id,
                    "canonicalZh": term.get("canonical_zh"),
                    "canonicalEn": term.get("canonical_en"),
                    "definition": term.get("definition"),
                    "semanticColor": None,
                }
            )
        script_sentences = _sentences(str(page.get("script_text", "")))
        sequence = [str(item) for item in visual.get("sequence", [])]
        event_count = max(1, len(sequence), len(script_sentences))
        duration = max(12.0, min(90.0, len(str(page.get("script_text", ""))) / 4.2))
        interval = duration / event_count
        events = []
        for index in range(event_count):
            events.append(
                {
                    "eventId": f"p{int(page.get('page_id', 0)):03d}_e{index + 1:02d}",
                    "start": round(index * interval, 3),
                    "end": round((index + 1) * interval, 3),
                    "visualAction": sequence[index] if index < len(sequence) else "hold_or_emphasize_current_object",
                    "narrationCue": script_sentences[index] if index < len(script_sentences) else None,
                    "focusTarget": (visual.get("focus_cues") or [None] * event_count)[index]
                    if index < len(visual.get("focus_cues") or [])
                    else None,
                }
            )
        return {
            "renderer": "manim" if str(visual.get("type") or spec.get("visual_type")) == "manim" else "ppt",
            "symbol_ledger": symbol_ledger,
            "scene_objects": [str(item) for item in visual.get("objects", [])],
            "animation_events": events,
            "visual_focus": [str(item) for item in visual.get("focus_cues", [])],
            "narration_cues": script_sentences,
            "duration": round(duration, 3),
            "safe_regions": {
                "header": {"top": 0.0, "bottom": 0.16},
                "content": {"left": 0.04, "top": 0.18, "right": 0.96, "bottom": 0.84},
                "subtitle": {"left": 0.05, "top": 0.86, "right": 0.95, "bottom": 0.98},
                "avatarCandidateRegions": ["left", "right", "left_bottom", "right_bottom"],
                "avatarPlacement": "dynamic_by_content_regions",
            },
            "learnerAdaptation": {
                "depth": learner_model.get("explanationDepth"),
                "pacing": learner_model.get("pacing"),
            },
            "status": "scene_spec_ready",
        }

    def enrich_page(
        self,
        page: dict[str, Any],
        brief: dict[str, Any],
        learner_model: dict[str, Any],
    ) -> dict[str, Any]:
        value = dict(page)
        value["learner_model"] = learner_model
        value["multimodal_asset_request"] = self.build_multimodal_asset_request(value)
        value["manim_scene_spec"] = self.build_manim_scene_spec(value, brief, learner_model)
        value["slide_spec"] = {
            "schemaVersion": SCHEMA_VERSION,
            "pageId": value.get("page_id"),
            "courseThesis": brief.get("course_thesis"),
            "sectionId": value.get("section_id"),
            "teachingGoal": (value.get("page_spec") or {}).get("teaching_goal"),
            "narrativeRole": (value.get("page_spec") or {}).get("content_role"),
            "openingQuestion": value.get("opening_question"),
            "workedExample": value.get("worked_example"),
            "termIds": list(value.get("terminology_used") or []),
            "sourceUnitIds": list(value.get("source_unit_ids") or []),
            "retrievalQuery": value.get("retrieval_query"),
            "visualPlan": value.get("visual_plan") or {},
            "manimScene": value["manim_scene_spec"],
            "assetRequest": value["multimodal_asset_request"],
            "assessmentHook": (value.get("page_spec") or {}).get("assessment_hook"),
        }
        return value

    @staticmethod
    def _region_report(
        regions: list[tuple[int, int, int, int]], width: int, height: int
    ) -> dict[str, Any]:
        boundary_issues = []
        for index, (left, top, right, bottom) in enumerate(regions):
            if left < 0 or top < 0 or right > width or bottom > height:
                boundary_issues.append(index)
        occupied_area = sum(
            max(0, right - left) * max(0, bottom - top)
            for left, top, right, bottom in regions
        )
        return {
            "regionCount": len(regions),
            "boundaryIssues": boundary_issues,
            "occupiedAreaRatio": round(min(1.0, occupied_area / max(1, width * height)), 4),
        }

    @staticmethod
    def _image_report(path: Path) -> dict[str, Any]:
        image = Image.open(path).convert("RGB")
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        contrast = float(stat.stddev[0])
        sample = image.resize((120, 68))
        pixels = (
            sample.get_flattened_data()
            if hasattr(sample, "get_flattened_data")
            else sample.getdata()
        )
        common = Counter(pixels).most_common(1)[0][1]
        dominant_ratio = common / (120 * 68)
        return {
            "path": str(path),
            "width": image.width,
            "height": image.height,
            "contrastStd": round(contrast, 3),
            "dominantColorRatio": round(dominant_ratio, 4),
            "lowContrast": contrast < 10.0,
            "visuallySparseCandidate": dominant_ratio > 0.92,
        }

    def inspect_pptx(
        self,
        pptx_path: Path,
        pages: list[dict[str, Any]],
        brief: dict[str, Any],
        output_dir: Path,
    ) -> dict[str, Any]:
        render_dir = output_dir / "rendered_slides"
        rendered = [Path(item) for item in render_pptx_to_images(pptx_path, render_dir, width=1600)]
        region_sets = occupied_regions(pptx_path, image_width=1600)
        page_reports = []
        for index, image_path in enumerate(rendered):
            image_report = self._image_report(image_path)
            region_report = self._region_report(
                region_sets[index], image_report["width"], image_report["height"]
            )
            image_report["visuallySparse"] = bool(
                image_report["dominantColorRatio"] > 0.965
                and region_report["occupiedAreaRatio"] < 0.25
            )
            deterministic_failures = []
            if image_report["lowContrast"]:
                deterministic_failures.append("low_contrast")
            if image_report["visuallySparse"]:
                deterministic_failures.append("visually_sparse")
            if region_report["boundaryIssues"]:
                deterministic_failures.append("content_outside_slide")
            page_reports.append(
                {
                    "pageId": pages[index].get("page_id") if index < len(pages) else index + 1,
                    "image": image_report,
                    "layout": region_report,
                    "rewardDimensions": {
                        "textAccuracy": {"status": "pending_ocr_or_vlm"},
                        "layout": {"status": "executed", "passed": not region_report["boundaryIssues"]},
                        "color": {"status": "executed", "passed": not image_report["lowContrast"]},
                        "imageTextAlignment": {"status": "pending_vlm"},
                        "instructionFollowing": {"status": "pending_vlm"},
                        "aiArtifactRisk": {"status": "pending_vlm_and_teacher_review"},
                    },
                    "deterministicFailures": deterministic_failures,
                    "passedDeterministicChecks": not deterministic_failures,
                }
            )

        terms = list(brief.get("terminology") or [])
        all_values = []
        for page in pages:
            all_values.extend(
                [
                    str(page.get("title", "")),
                    str(page.get("script_text", "")),
                    *[str(item) for item in page.get("key_points", [])],
                ]
            )
        all_text = "\n".join(all_values)
        terminology_issues = []
        for term in terms:
            for forbidden in term.get("forbidden_variants", []) or []:
                if forbidden and forbidden in all_text:
                    terminology_issues.append(
                        {"termId": term.get("term_id"), "forbiddenVariant": forbidden}
                    )
        title_values = [str(page.get("title", "")).strip() for page in pages]
        duplicate_titles = sorted(
            title for title, count in Counter(title_values).items() if title and count > 1
        )
        deterministic_passed = all(
            item["passedDeterministicChecks"] for item in page_reports
        ) and not terminology_issues and not duplicate_titles
        return {
            "schemaVersion": SCHEMA_VERSION,
            "pptx": str(pptx_path),
            "pageCount": len(rendered),
            "pageReports": page_reports,
            "deckReview": {
                "courseThesisPresent": bool(brief.get("course_thesis")),
                "duplicateTitles": duplicate_titles,
                "terminologyIssues": terminology_issues,
                "sectionIds": [str(item.get("section_id")) for item in brief.get("sections", [])],
            },
            "deterministicPassed": deterministic_passed,
            "requiresExternalReview": [
                "ocr_text_accuracy",
                "vlm_image_text_alignment",
                "vlm_instruction_following",
                "teacher_ai_artifact_review",
            ],
        }

    @staticmethod
    def build_learning_evaluation(
        brief: dict[str, Any], pages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        quiz_items = []
        for page in pages:
            hook = (page.get("page_spec") or {}).get("assessment_hook")
            if not hook:
                continue
            quiz_items.append(
                {
                    "pageId": page.get("page_id"),
                    "prompt": hook,
                    "termIds": list(page.get("terminology_used") or []),
                    "sourceUnitIds": list(page.get("source_unit_ids") or []),
                }
            )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "courseThesis": brief.get("course_thesis"),
            "quizItems": quiz_items,
            "teachQuiz": {
                "status": "spec_ready",
                "input": "final_course_video_and_transcript",
                "metrics": [
                    "knowledge_recovery",
                    "concept_transfer",
                    "misconception_rate",
                    "answer_source_alignment",
                ],
            },
            "humanEvaluation": {
                "required": True,
                "roles": ["teacher", "student_pre_post_test"],
            },
        }

    @staticmethod
    def update_experience_memory(
        path: Path,
        pages: list[dict[str, Any]],
        visual_report: dict[str, Any],
    ) -> dict[str, Any]:
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            value = {
                "schemaVersion": SCHEMA_VERSION,
                "positive": [],
                "negative": [],
            }
        visual_by_page = {
            int(item.get("pageId") or 0): item
            for item in visual_report.get("pageReports", [])
        }
        for page in pages:
            page_id = int(page.get("page_id", 0))
            quality = page.get("quality_audit") or {}
            visual = visual_by_page.get(page_id, {})
            entry = {
                "pageId": page_id,
                "title": page.get("title"),
                "visualType": (page.get("visual_plan") or {}).get("type"),
                "textIssueCount": int(quality.get("issueCount", 0)),
                "visualFailures": list(visual.get("deterministicFailures", [])),
                "rewriteRounds": int(page.get("rewrite_rounds", 0)),
                "teacherAccepted": None,
            }
            target = "positive" if entry["textIssueCount"] == 0 and not entry["visualFailures"] else "negative"
            value[target].append(entry)
        value["positive"] = value["positive"][-500:]
        value["negative"] = value["negative"][-500:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return value

    @staticmethod
    def research_coverage(
        pages: list[dict[str, Any]], visual_report: dict[str, Any]
    ) -> dict[str, Any]:
        has_manim_specs = any(
            page.get("manim_scene_spec", {}).get("status") == "scene_spec_ready"
            for page in pages
        )
        has_asset_requests = all(page.get("multimodal_asset_request") for page in pages)
        status = {
            "narrative_planning": "executed",
            "programmatic_slides": "executed",
            "visual_feedback": "deterministic_executed_external_review_pending",
            "visual_reward": "partial_external_reward_model_pending",
            "deck_structure": "deterministic_executed",
            "code_visualization": "scene_specs_ready_renderer_required" if has_manim_specs else "not_required",
            "narration_alignment": "event_timeline_ready",
            "multimodal_retrieval": "requests_ready" if has_asset_requests else "incomplete",
            "experience_memory": "executed",
        }
        return {
            "schemaVersion": SCHEMA_VERSION,
            "directions": [
                {**item, "status": status[item["id"]]}
                for item in RESEARCH_DIRECTIONS
            ],
            "agentRoles": AGENT_ROLES,
            "deterministicVisualPassed": visual_report.get("deterministicPassed", False),
        }
