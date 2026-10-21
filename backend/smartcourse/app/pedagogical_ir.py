from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "2026.1"

E1_CONDITIONS = {
    "A0": "end_to_end",
    "A1": "code_ir",
    "A2": "pedagogical_ir",
    "A3": "pedagogical_ir_ctml_clt",
    "A4": "pedagogical_ir_full_theory",
}

E2_CONDITIONS = {
    "B0": "no_behavior_no_cue",
    "B1": "visual_cue_only",
    "B2": "avatar_behavior_only",
    "B3": "behavior_and_cue_temporally_misaligned",
    "B4": "behavior_and_cue_semantically_temporally_aligned",
    "B5": "learner_state_adaptive_alignment",
}

EXPERIMENT_CATALOG = [
    {
        "experimentId": "E1",
        "title": "理论驱动 Pedagogical IR",
        "priority": "P0",
        "conditions": list(E1_CONDITIONS),
        "outputs": ["pedagogical_ir.json", "constraint_report.json"],
    },
    {
        "experimentId": "E2",
        "title": "数字教师行为与动态视觉线索语义同步",
        "priority": "P0",
        "conditions": list(E2_CONDITIONS),
        "outputs": ["e2_variants.json", "sync_evaluation.json"],
    },
]


@dataclass
class LearnerState:
    mastery: float = 0.5
    attention: float = 1.0
    engagement: float = 0.8
    cognitive_load: float = 0.5
    misconception: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def normalized(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("mastery", "attention", "engagement", "cognitive_load"):
            value[key] = round(min(1.0, max(0.0, float(value[key]))), 3)
        return value


def _theory_profile(condition: str) -> dict[str, Any]:
    if condition not in E1_CONDITIONS:
        raise ValueError(f"不支持的 E1 条件：{condition}")
    enabled = {
        "ctml": condition in {"A3", "A4"},
        "cognitiveLoad": condition in {"A3", "A4"},
        "signaling": condition in {"A3", "A4"},
        "socialAgency": condition == "A4",
        "icap": condition == "A4",
    }
    constraints: list[dict[str, Any]] = []
    if enabled["ctml"]:
        constraints.extend(
            [
                {"id": "temporal_contiguity", "rule": "narration_visual_same_span"},
                {"id": "spatial_contiguity", "rule": "cue_targets_named_visual_anchor"},
                {"id": "modality_complementarity", "rule": "narration_explains_visual_change"},
            ]
        )
    if enabled["cognitiveLoad"]:
        constraints.extend(
            [
                {"id": "active_concept_budget", "maxActiveConcepts": 1},
                {"id": "stable_symbol", "rule": "preserve_semantic_color_and_identity"},
            ]
        )
    if enabled["signaling"]:
        constraints.append({"id": "signaling", "rule": "cue_has_target_start_end"})
    if enabled["socialAgency"]:
        constraints.append({"id": "social_agency", "rule": "gaze_or_gesture_matches_target"})
    if enabled["icap"]:
        constraints.append({"id": "icap", "rule": "summary_scene_requests_active_response"})
    return {"enabled": enabled, "constraints": constraints}


def _scene_role(scene_id: int, total: int) -> str:
    if scene_id == 1:
        return "activate_prior_knowledge"
    if scene_id == total:
        return "retrieve_and_self_explain"
    return "explain_and_apply"


def _dialogue_act(scene_id: int, total: int, condition: str) -> str:
    if condition != "A4":
        return "none"
    if scene_id == total:
        return "ask_for_reasoning"
    if scene_id == 1:
        return "guided_observation"
    return "explain"


def _gesture_for(point: str, scene_id: int, total: int) -> str:
    value = point.lower()
    if scene_id == total:
        return "open_palm_prompt"
    if any(token in value for token in ("公式", "pH", "角", "图", "线", "点", "轴")):
        return "deictic_point"
    return "beat_emphasis"


def _event_times(scene: dict[str, Any], count: int) -> list[tuple[float, float]]:
    duration = max(1.0, float(scene.get("duration_seconds", 18.0)))
    starts = scene.get("key_point_times", [])
    ends = scene.get("key_point_end_times", [])
    if len(starts) == count and len(ends) == count:
        return [
            (max(0.0, float(start)), min(duration, max(float(start) + 0.25, float(end))))
            for start, end in zip(starts, ends)
        ]
    interval = duration / max(1, count)
    return [(round(index * interval, 3), round((index + 1) * interval, 3)) for index in range(count)]


class PedagogicalIRCompiler:
    def compile(
        self,
        spec: dict[str, Any],
        condition: str = "A4",
        learner_state: LearnerState | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if condition not in E1_CONDITIONS:
            raise ValueError(f"不支持的 E1 条件：{condition}")
        if isinstance(learner_state, dict):
            state = LearnerState(
                mastery=float(learner_state.get("mastery", 0.5)),
                attention=float(learner_state.get("attention", 1.0)),
                engagement=float(learner_state.get("engagement", 0.8)),
                cognitive_load=float(
                    learner_state.get(
                        "cognitiveLoad",
                        learner_state.get("cognitive_load", 0.5),
                    )
                ),
                misconception=learner_state.get("misconception"),
                evidence=list(learner_state.get("evidence", [])),
            )
        else:
            state = learner_state or LearnerState()
        profile = _theory_profile(condition)
        total_scenes = len(spec.get("scenes", []))
        events: list[dict[str, Any]] = []
        global_offset = 0.0
        for scene in spec.get("scenes", []):
            scene_id = int(scene["scene_id"])
            key_points = list(scene.get("key_points", []))
            anchors = list(scene.get("focus_regions", []))
            scene_duration = max(1.0, float(scene.get("duration_seconds", 18.0)))
            times = _event_times(scene, len(key_points))
            for index, point in enumerate(key_points):
                local_start, local_end = times[index]
                start = round(global_offset + local_start, 3)
                end = round(global_offset + local_end, 3)
                anchor = anchors[index] if index < len(anchors) else scene.get("visual", "scene")
                cue_enabled = condition in {"A2", "A3", "A4"}
                behavior_enabled = condition == "A4"
                events.append(
                    {
                        "eventId": f"s{scene_id:02d}_e{index + 1:02d}",
                        "sceneId": scene_id,
                        "sequence": len(events) + 1,
                        "concept": point,
                        "teachingIntent": _scene_role(scene_id, total_scenes),
                        "start": start,
                        "end": end,
                        "narration": {
                            "text": scene.get("script_text", ""),
                            "span": [start, end],
                        },
                        "visual": {
                            "renderer": "manim",
                            "scene": scene.get("visual", ""),
                            "target": anchor,
                            "safeArea": scene.get("avatar_position", "right_bottom"),
                        },
                        "cue": {
                            "enabled": cue_enabled,
                            "type": "dynamic_focus" if cue_enabled else "none",
                            "target": anchor if cue_enabled else None,
                            "start": start if cue_enabled else None,
                            "end": end if cue_enabled else None,
                            "style": "palette_aware" if profile["enabled"]["signaling"] else "default",
                        },
                        "instructorBehavior": {
                            "enabled": behavior_enabled,
                            "gesture": _gesture_for(point, scene_id, total_scenes) if behavior_enabled else "none",
                            "gazeTarget": anchor if behavior_enabled else None,
                            "facialAffect": "encouraging" if scene_id == total_scenes else "neutral_attentive",
                            "start": start if behavior_enabled else None,
                            "end": end if behavior_enabled else None,
                        },
                        "dialogue": {
                            "act": _dialogue_act(scene_id, total_scenes, condition),
                            "prompt": "请说明判断依据。" if scene_id == total_scenes and condition == "A4" else None,
                        },
                        "learnerStateTrigger": {
                            "enabled": False,
                            "conditions": [],
                        },
                    }
                )
            global_offset += scene_duration
        return {
            "schemaVersion": SCHEMA_VERSION,
            "experiment": {
                "experimentId": "E1",
                "condition": condition,
                "representation": E1_CONDITIONS[condition],
            },
            "lesson": {
                "lessonId": spec["lesson_id"],
                "subject": spec["subject"],
                "grade": spec["grade"],
                "topic": spec["topic"],
                "objective": spec["objective"],
                "prerequisites": spec.get("prerequisites", []),
            },
            "learnerState": state.normalized(),
            "theoryProfile": profile,
            "timeline": {
                "durationSeconds": round(global_offset, 3),
                "eventCount": len(events),
                "events": events,
            },
        }


def _interval_iou(first: tuple[float, float], second: tuple[float, float]) -> float:
    intersection = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    union = max(first[1], second[1]) - min(first[0], second[0])
    return 0.0 if union <= 0 else intersection / union


def evaluate_pedagogical_ir(ir: dict[str, Any]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    temporal_scores: list[float] = []
    semantic_scores: list[float] = []
    events = ir.get("timeline", {}).get("events", [])
    previous_start = -1.0
    seen_ids: set[str] = set()
    for event in events:
        event_id = str(event.get("eventId", ""))
        start = float(event.get("start", -1))
        end = float(event.get("end", -1))
        target = event.get("visual", {}).get("target")
        if not event_id or event_id in seen_ids:
            violations.append({"eventId": event_id, "rule": "unique_event_id"})
        seen_ids.add(event_id)
        if start < 0 or end <= start:
            violations.append({"eventId": event_id, "rule": "positive_event_span"})
        if start < previous_start:
            violations.append({"eventId": event_id, "rule": "monotonic_timeline"})
        previous_start = start
        if not event.get("concept") or not event.get("teachingIntent") or not target:
            violations.append({"eventId": event_id, "rule": "required_pedagogical_fields"})
        cue = event.get("cue", {})
        behavior = event.get("instructorBehavior", {})
        channels = 0
        if cue.get("enabled"):
            channels += 1
            cue_start = cue.get("start")
            cue_end = cue.get("end")
            if cue.get("target") != target:
                violations.append({"eventId": event_id, "rule": "cue_target_matches_visual"})
                semantic_scores.append(0.0)
            else:
                semantic_scores.append(1.0)
            if cue_start is None or cue_end is None:
                violations.append({"eventId": event_id, "rule": "cue_has_timing"})
                temporal_scores.append(0.0)
            else:
                temporal_scores.append(_interval_iou((start, end), (float(cue_start), float(cue_end))))
        if behavior.get("enabled"):
            channels += 1
            behavior_start = behavior.get("start")
            behavior_end = behavior.get("end")
            if behavior.get("gazeTarget") != target:
                violations.append({"eventId": event_id, "rule": "gaze_target_matches_visual"})
                semantic_scores.append(0.0)
            else:
                semantic_scores.append(1.0)
            if behavior_start is None or behavior_end is None:
                violations.append({"eventId": event_id, "rule": "behavior_has_timing"})
                temporal_scores.append(0.0)
            else:
                temporal_scores.append(
                    _interval_iou((start, end), (float(behavior_start), float(behavior_end)))
                )
        if channels == 0:
            temporal_scores.append(0.0)
            semantic_scores.append(0.0)
    checked = max(1, len(events) * 5)
    satisfaction = max(0.0, 1.0 - len(violations) / checked)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "eventCount": len(events),
        "valid": not violations,
        "constraintSatisfaction": round(satisfaction, 4),
        "temporalAlignment": round(sum(temporal_scores) / max(1, len(temporal_scores)), 4),
        "semanticAlignment": round(sum(semantic_scores) / max(1, len(semantic_scores)), 4),
        "violations": violations,
    }


def _set_channel(event: dict[str, Any], channel: str, enabled: bool) -> None:
    value = event[channel]
    value["enabled"] = enabled
    if channel == "cue":
        value["type"] = "dynamic_focus" if enabled else "none"
        value["target"] = event["visual"]["target"] if enabled else None
    else:
        value["gesture"] = value.get("gesture", "deictic_point") if enabled else "none"
        value["gazeTarget"] = event["visual"]["target"] if enabled else None
    value["start"] = event["start"] if enabled else None
    value["end"] = event["end"] if enabled else None


def build_e2_variants(base_ir: dict[str, Any]) -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for condition, description in E2_CONDITIONS.items():
        value = deepcopy(base_ir)
        value["experiment"] = {
            "experimentId": "E2",
            "condition": condition,
            "representation": description,
        }
        for event in value["timeline"]["events"]:
            if condition == "B0":
                _set_channel(event, "cue", False)
                _set_channel(event, "instructorBehavior", False)
            elif condition == "B1":
                _set_channel(event, "cue", True)
                _set_channel(event, "instructorBehavior", False)
            elif condition == "B2":
                _set_channel(event, "cue", False)
                _set_channel(event, "instructorBehavior", True)
            else:
                _set_channel(event, "cue", True)
                _set_channel(event, "instructorBehavior", True)
            if condition == "B3":
                shift = 2.0
                event["cue"]["start"] = round(float(event["start"]) + shift, 3)
                event["cue"]["end"] = round(float(event["end"]) + shift, 3)
                event["instructorBehavior"]["start"] = round(float(event["start"]) - shift, 3)
                event["instructorBehavior"]["end"] = round(float(event["end"]) - shift, 3)
            if condition == "B5":
                event["learnerStateTrigger"] = {
                    "enabled": True,
                    "conditions": [
                        {"field": "attention", "operator": "lt", "value": 0.55},
                        {"field": "mastery", "operator": "lt", "value": 0.60},
                    ],
                    "action": "increase_cue_salience_and_deictic_behavior",
                }
        variants[condition] = {
            "description": description,
            "ir": value,
            "evaluation": evaluate_pedagogical_ir(value),
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": "E2",
        "lessonId": base_ir.get("lesson", {}).get("lessonId"),
        "variants": variants,
    }


def compile_lesson_ir(
    spec: dict[str, Any],
    condition: str = "A4",
    learner_state: LearnerState | dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ir = PedagogicalIRCompiler().compile(spec, condition, learner_state)
    return ir, evaluate_pedagogical_ir(ir)


def compile_course_structure_ir(
    structure: dict[str, Any],
    condition: str = "A4",
    learner_state: LearnerState | dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile upload/topic/code S1 structures into the same Pedagogical IR."""

    pages = list(structure.get("pages", []))
    scenes: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        page_id = int(page.get("page_id", index))
        key_points = [str(value) for value in page.get("key_points", []) if str(value).strip()]
        if not key_points:
            key_points = [str(page.get("title", f"第 {page_id} 页"))]
        layout = page.get("layout", {}) if isinstance(page.get("layout"), dict) else {}
        regions = layout.get("regions", []) if isinstance(layout.get("regions"), list) else []
        anchors = []
        for point_index, _point in enumerate(key_points):
            if point_index < len(regions):
                region = regions[point_index]
                name = str(region.get("name", "")).strip() if isinstance(region, dict) else ""
                anchors.append(name or f"page_{page_id:03d}:region_{point_index + 1:02d}")
            else:
                anchors.append(f"page_{page_id:03d}:concept_{point_index + 1:02d}")
        scenes.append(
            {
                "scene_id": page_id,
                "class_name": f"Page{page_id:03d}",
                "title": str(page.get("title", f"第 {page_id} 页")),
                "visual": str(layout.get("template", layout.get("visual_anchor", "ppt_page"))),
                "key_points": key_points,
                "focus_regions": anchors,
                "script_text": str(page.get("script_text", "")),
                "duration_seconds": float(page.get("duration_seconds", 45.0)),
                "avatar_position": str(layout.get("avatar_safe_area", "right_bottom")),
            }
        )
    spec = {
        "lesson_id": str(structure.get("task_id", "course")),
        "subject": str(structure.get("subject", "MOOC 课程")),
        "grade": str(structure.get("grade", structure.get("target_audience", "学习者"))),
        "topic": str(structure.get("course_topic", pages[0].get("title", "课程") if pages else "课程")),
        "objective": str(structure.get("objective", structure.get("course_topic", "完成课程学习"))),
        "prerequisites": [str(value) for value in structure.get("prerequisites", [])],
        "scenes": scenes,
    }
    ir, report = compile_lesson_ir(spec, condition, learner_state)
    ir["source"] = {
        "stage": "S1",
        "inputMode": structure.get("input_mode"),
        "pageCount": len(pages),
    }
    return ir, report
