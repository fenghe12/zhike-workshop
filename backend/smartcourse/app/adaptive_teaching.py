from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "2026.1"

E3_CONDITIONS = {
    "C0": "static_lesson",
    "C1": "response_conditioned",
    "C2": "diagnosis_conditioned",
    "C3": "history_aware",
    "C4": "multimodal_learner_state",
}

E5_CONDITIONS = {
    "E0": "direct_corrective_explanation",
    "E1": "hint_first",
    "E2": "socratic_question",
    "E3": "counterfactual_question",
    "E4": "rule_based_adaptive_policy",
    "E5": "multi_horizon_policy_baseline",
}

ADAPTIVE_EXPERIMENT_CATALOG = [
    {
        "experimentId": "E3",
        "title": "学习者状态驱动自适应",
        "priority": "P0",
        "conditions": list(E3_CONDITIONS),
        "outputs": ["learner_state.json", "state_diagnosis.json"],
    },
    {
        "experimentId": "E5",
        "title": "教学策略动态选择",
        "priority": "P0",
        "conditions": list(E5_CONDITIONS),
        "outputs": ["adaptive_plan.json", "policy_report.json"],
    },
]


def _clamp(value: Any, default: float) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return default


def normalize_learner_state(value: dict[str, Any] | None = None) -> dict[str, Any]:
    source = value or {}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mastery": _clamp(source.get("mastery"), 0.5),
        "attention": _clamp(source.get("attention"), 1.0),
        "engagement": _clamp(source.get("engagement"), 0.8),
        "cognitiveLoad": _clamp(
            source.get("cognitiveLoad", source.get("cognitive_load")), 0.5
        ),
        "misconception": source.get("misconception"),
        "evidence": list(source.get("evidence", [])),
        "updatedAt": str(source.get("updatedAt", "")) or None,
    }


def diagnose_learner_error(observation: dict[str, Any]) -> dict[str, Any]:
    correctness = _clamp(
        observation.get("score", 1.0 if observation.get("correct") else 0.0),
        0.0,
    )
    explicit = str(observation.get("errorType", "")).strip()
    if correctness >= 0.8:
        label = "none"
        confidence = correctness
    elif explicit in {
        "recall_failure",
        "conceptual_gap",
        "procedural_error",
        "transfer_deficit",
    }:
        label = explicit
        confidence = 0.9
    elif bool(observation.get("transferTask")):
        label = "transfer_deficit"
        confidence = 0.74
    elif observation.get("misconception"):
        label = "conceptual_gap"
        confidence = 0.78
    elif _clamp(observation.get("procedureCompletion"), 1.0) < 0.55:
        label = "procedural_error"
        confidence = 0.7
    else:
        label = "recall_failure"
        confidence = 0.62
    return {
        "label": label,
        "confidence": round(confidence, 4),
        "correctness": correctness,
    }


def update_learner_state(
    current_state: dict[str, Any] | None,
    observation: dict[str, Any],
) -> dict[str, Any]:
    state = normalize_learner_state(current_state)
    diagnosis = diagnose_learner_error(observation)
    correctness = diagnosis["correctness"]
    explanation = _clamp(observation.get("selfExplanationQuality"), correctness)
    transfer = _clamp(observation.get("transferScore"), correctness)
    evidence_score = 0.5 * correctness + 0.25 * explanation + 0.25 * transfer
    state["mastery"] = round(0.72 * state["mastery"] + 0.28 * evidence_score, 4)

    if "attention" in observation:
        state["attention"] = _clamp(observation.get("attention"), state["attention"])
    if "engagement" in observation:
        state["engagement"] = _clamp(observation.get("engagement"), state["engagement"])

    response_time = max(0.0, float(observation.get("responseTimeSeconds", 0) or 0))
    expected_time = max(1.0, float(observation.get("expectedTimeSeconds", 30) or 30))
    time_ratio = response_time / expected_time if response_time else 1.0
    inferred_load = min(1.0, max(0.0, 0.42 + 0.28 * max(0.0, time_ratio - 1.0) + 0.25 * (1 - correctness)))
    state["cognitiveLoad"] = _clamp(
        observation.get("cognitiveLoad", inferred_load), state["cognitiveLoad"]
    )
    state["misconception"] = (
        str(observation.get("misconception") or diagnosis["label"])
        if diagnosis["label"] not in {"none", "recall_failure"}
        else None
    )
    evidence_record = {
        "concept": str(observation.get("concept", "unknown")),
        "correctness": correctness,
        "responseTimeSeconds": response_time,
        "diagnosis": diagnosis["label"],
        "timestamp": str(observation.get("timestamp", ""))
        or datetime.now(timezone.utc).isoformat(),
    }
    state["evidence"] = [*state["evidence"][-49:], evidence_record]
    state["updatedAt"] = evidence_record["timestamp"]
    return {"learnerState": state, "diagnosis": diagnosis}


def select_teaching_policy(
    learner_state: dict[str, Any],
    condition: str = "E4",
) -> dict[str, Any]:
    if condition not in E5_CONDITIONS:
        raise ValueError(f"不支持的 E5 条件：{condition}")
    state = normalize_learner_state(learner_state)
    diagnosis = str(state.get("misconception") or "recall_failure")
    fixed = {
        "E0": ["direct_explanation"],
        "E1": ["hint"],
        "E2": ["socratic_question"],
        "E3": ["counterfactual_question"],
    }
    rationale: list[str] = []
    if condition in fixed:
        actions = fixed[condition]
        rationale.append(f"固定实验条件 {condition}")
    else:
        if state["cognitiveLoad"] >= 0.75:
            actions = ["reduce_information_density", "worked_example", "pause_for_retrieval"]
            rationale.append("认知负荷较高，降低单屏信息量并使用分步示例")
        elif state["attention"] < 0.55:
            actions = ["visual_replay", "embodied_cue", "attention_check"]
            rationale.append("注意状态较低，增强视觉线索并加入教师指向行为")
        elif diagnosis == "conceptual_gap":
            actions = ["counterfactual_question", "contrastive_example", "socratic_question"]
            rationale.append("检测到概念性偏差，使用矛盾事实和对比例子")
        elif diagnosis == "procedural_error":
            actions = ["hint", "stepwise_visual_replay", "ask_for_next_step"]
            rationale.append("检测到步骤错误，提供局部提示并要求继续下一步")
        elif diagnosis == "transfer_deficit":
            actions = ["socratic_question", "new_context_example", "ask_for_reasoning"]
            rationale.append("基础知识存在但迁移不足，使用新情境进行引导")
        elif state["mastery"] < 0.6:
            actions = ["hint", "retrieval_prompt", "direct_explanation_if_needed"]
            rationale.append("知识掌握度较低，先提示和回忆，再按需解释")
        else:
            actions = ["ask_for_reasoning", "far_transfer_question"]
            rationale.append("知识掌握度较高，进入解释和迁移任务")
        if condition == "E5":
            actions = [*actions, "delayed_reassessment"]
            rationale.append("加入跨轮次复测，形成多阶段教学轨迹基线")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": "E5",
        "condition": condition,
        "policy": E5_CONDITIONS[condition],
        "learnerState": state,
        "actions": actions,
        "primaryAction": actions[0],
        "rationale": rationale,
        "renderControls": {
            "cueSalience": "high" if state["attention"] < 0.55 else "normal",
            "avatarBehavior": "deictic" if "embodied_cue" in actions else "attentive",
            "pacing": "slower" if state["cognitiveLoad"] >= 0.75 else "normal",
        },
    }


def apply_adaptive_policy(
    pedagogical_ir: dict[str, Any],
    learner_state: dict[str, Any],
    condition: str = "E4",
) -> dict[str, Any]:
    value = deepcopy(pedagogical_ir)
    policy = select_teaching_policy(learner_state, condition)
    events = value.get("timeline", {}).get("events", [])
    for index, event in enumerate(events):
        event["learnerStateTrigger"] = {
            "enabled": True,
            "conditions": [
                {"field": "mastery", "operator": "lt", "value": 0.60},
                {"field": "attention", "operator": "lt", "value": 0.55},
                {"field": "cognitiveLoad", "operator": "gte", "value": 0.75},
            ],
            "matched": (
                policy["learnerState"]["mastery"] < 0.60
                or policy["learnerState"]["attention"] < 0.55
                or policy["learnerState"]["cognitiveLoad"] >= 0.75
            ),
            "action": policy["primaryAction"],
        }
        if event["learnerStateTrigger"]["matched"]:
            event["dialogue"]["act"] = policy["primaryAction"]
            event["cue"]["style"] = policy["renderControls"]["cueSalience"]
            event["instructorBehavior"]["gesture"] = policy["renderControls"]["avatarBehavior"]
        if condition == "E5" and index == len(events) - 1:
            event["dialogue"]["act"] = "delayed_reassessment"
    value["adaptiveTeaching"] = {
        "experimentId": "E5",
        "condition": condition,
        "policy": policy,
    }
    return {"adaptiveIr": value, "policyReport": policy}


def build_adaptive_experiment(
    pedagogical_ir: dict[str, Any],
    learner_state: dict[str, Any],
) -> dict[str, Any]:
    state = normalize_learner_state(learner_state)
    e3_variants: dict[str, Any] = {}
    for condition, description in E3_CONDITIONS.items():
        visible_state = {
            "C0": {},
            "C1": {"mastery": state["mastery"]},
            "C2": {"mastery": state["mastery"], "misconception": state["misconception"]},
            "C3": {
                "mastery": state["mastery"],
                "misconception": state["misconception"],
                "evidence": state["evidence"],
            },
            "C4": state,
        }[condition]
        e3_variants[condition] = {
            "description": description,
            "state": visible_state,
            "fieldCount": len(visible_state),
        }
    e5_variants = {
        condition: apply_adaptive_policy(pedagogical_ir, state, condition)
        for condition in E5_CONDITIONS
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experiments": ["E3", "E5"],
        "lessonId": pedagogical_ir.get("lesson", {}).get("lessonId"),
        "learnerState": state,
        "e3Variants": e3_variants,
        "e5Variants": e5_variants,
    }
