from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import exp
from typing import Any

from .adaptive_teaching import normalize_learner_state


SCHEMA_VERSION = "2026.1"

ADVANCED_EXPERIMENT_CATALOG = [
    {"experimentId": "E4", "title": "主动式教学干预", "priority": "P1", "conditions": ["D0", "D1", "D2", "D3", "D4"]},
    {"experimentId": "E6", "title": "结构化长期记忆", "priority": "P1", "conditions": ["F0", "F1", "F2", "F3", "F4"]},
    {"experimentId": "E7", "title": "多层个性化教学", "priority": "P1", "conditions": ["G0", "G1", "G2", "G3", "G4", "G5"]},
    {"experimentId": "E8", "title": "抑制答案提取的交互设计", "priority": "P2", "conditions": ["H0", "H1", "H2", "H3", "H4"]},
    {"experimentId": "E9", "title": "自动预筛选与真人校准", "priority": "P2", "conditions": ["I0", "I1", "I2", "I3", "I4"]},
]


def select_proactive_intervention(
    learner_state: dict[str, Any],
    condition: str = "D4",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if condition not in {"D0", "D1", "D2", "D3", "D4"}:
        raise ValueError(f"不支持的 E4 条件：{condition}")
    state = normalize_learner_state(learner_state)
    ctx = context or {}
    elapsed = float(ctx.get("elapsedSinceInterventionSeconds", 0) or 0)
    uncertainty = float(ctx.get("stateUncertainty", 0.0) or 0.0)
    explicit_request = bool(ctx.get("studentRequestedHelp"))
    if condition == "D0":
        trigger = "student_request" if explicit_request else "none"
        intervene = explicit_request
    elif condition == "D1":
        trigger = "pre_generated_checkpoint"
        intervene = bool(ctx.get("atCheckpoint"))
    elif condition == "D2":
        trigger = "fixed_interval"
        intervene = elapsed >= float(ctx.get("intervalSeconds", 90) or 90)
    elif condition == "D3":
        trigger = "state_uncertainty"
        intervene = uncertainty >= 0.35
    else:
        conditions = {
            "low_attention": state["attention"] < 0.55,
            "low_mastery": state["mastery"] < 0.60,
            "high_load": state["cognitiveLoad"] >= 0.78,
            "low_engagement": state["engagement"] < 0.50,
        }
        matched = [name for name, value in conditions.items() if value]
        trigger = matched[0] if matched else "none"
        intervene = bool(matched)
    action = {
        "low_attention": "attention_check",
        "low_mastery": "retrieval_question",
        "high_load": "pause_and_simplify",
        "low_engagement": "relevance_prompt",
        "state_uncertainty": "diagnostic_question",
        "fixed_interval": "progress_check",
        "pre_generated_checkpoint": "checkpoint_question",
        "student_request": "respond_to_help_request",
    }.get(trigger, "continue_instruction")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": "E4",
        "condition": condition,
        "shouldIntervene": intervene,
        "trigger": trigger,
        "action": action,
        "learnerState": state,
    }


def update_structured_memory(
    memory: dict[str, Any] | None,
    evidence: dict[str, Any],
    condition: str = "F4",
) -> dict[str, Any]:
    if condition not in {"F0", "F1", "F2", "F3", "F4"}:
        raise ValueError(f"不支持的 E6 条件：{condition}")
    value = deepcopy(memory or {"schemaVersion": SCHEMA_VERSION, "entries": []})
    concept = str(evidence.get("concept", "unknown"))
    now = str(evidence.get("timestamp", "")) or datetime.now(timezone.utc).isoformat()
    entry = {
        "concept": concept,
        "evidenceType": str(evidence.get("evidenceType", "response")),
        "errorType": evidence.get("errorType"),
        "success": bool(evidence.get("success", False)),
        "confidence": min(1.0, max(0.0, float(evidence.get("confidence", 0.5)))),
        "timestamp": now,
        "spacingIntervalDays": float(evidence.get("spacingIntervalDays", 0) or 0),
    }
    if condition == "F0":
        value["entries"] = [entry]
    else:
        value["entries"] = [*value.get("entries", [])[-199:], entry]
    summaries: dict[str, dict[str, Any]] = {}
    for item in value["entries"]:
        key = item["concept"]
        summary = summaries.setdefault(key, {"concept": key, "evidenceCount": 0, "weightedMastery": 0.0, "lastEvidence": None})
        age = max(0.0, float(item.get("spacingIntervalDays", 0) or 0))
        decay = exp(-age / 30.0) if condition == "F4" else 1.0
        score = (1.0 if item.get("success") else 0.0) * float(item.get("confidence", 0.5)) * decay
        summary["evidenceCount"] += 1
        summary["weightedMastery"] += score
        summary["lastEvidence"] = item["timestamp"]
    for summary in summaries.values():
        summary["weightedMastery"] = round(summary["weightedMastery"] / max(1, summary["evidenceCount"]), 4)
    value["experimentId"] = "E6"
    value["condition"] = condition
    value["conceptSummaries"] = list(summaries.values())
    return value


def build_personalization_plan(
    learner_state: dict[str, Any],
    preferences: dict[str, Any] | None = None,
    condition: str = "G5",
) -> dict[str, Any]:
    if condition not in {"G0", "G1", "G2", "G3", "G4", "G5"}:
        raise ValueError(f"不支持的 E7 条件：{condition}")
    state = normalize_learner_state(learner_state)
    pref = preferences or {}
    enabled = {
        "curriculum": condition in {"G1", "G5"},
        "examples": condition in {"G1", "G5"},
        "narration": condition in {"G2", "G5"},
        "cuesAndPacing": condition in {"G3", "G5"},
        "avatarBehavior": condition in {"G4", "G5"},
    }
    plan = {
        "difficulty": "foundational" if state["mastery"] < 0.45 else "advanced" if state["mastery"] > 0.8 else "standard",
        "exampleDomain": str(pref.get("interestDomain", "general")),
        "narrationStyle": "concise" if state["cognitiveLoad"] > 0.7 else str(pref.get("narrationStyle", "guided")),
        "pacing": "slower" if state["cognitiveLoad"] > 0.7 else "faster" if state["mastery"] > 0.8 else "normal",
        "cueIntensity": "high" if state["attention"] < 0.55 else "normal",
        "avatarAffect": "encouraging" if state["engagement"] < 0.55 else "attentive",
    }
    return {"schemaVersion": SCHEMA_VERSION, "experimentId": "E7", "condition": condition, "enabledLayers": enabled, "plan": plan}


def check_pedagogical_alignment(
    learner_state: dict[str, Any],
    interaction: dict[str, Any],
    condition: str = "H4",
) -> dict[str, Any]:
    if condition not in {"H0", "H1", "H2", "H3", "H4"}:
        raise ValueError(f"不支持的 E8 条件：{condition}")
    state = normalize_learner_state(learner_state)
    reasoning = str(interaction.get("studentReasoning", "")).strip()
    asks_answer = bool(interaction.get("requestsDirectAnswer", True))
    if condition == "H0":
        policy = "direct_answer"
    elif condition == "H1":
        policy = "hint_before_answer"
    elif condition == "H2":
        policy = "require_self_explanation" if not reasoning else "answer_with_feedback"
    elif condition == "H3":
        policy = "require_prediction" if not interaction.get("prediction") else "feedback_then_answer"
    else:
        if state["mastery"] < 0.6 and not reasoning:
            policy = "require_self_explanation"
        elif state["cognitiveLoad"] > 0.8:
            policy = "guided_hint"
        elif state["mastery"] > 0.8:
            policy = "answer_with_transfer_prompt"
        else:
            policy = "hint_before_answer"
    risk = 1.0 if asks_answer and not reasoning else 0.35 if asks_answer else 0.1
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": "E8",
        "condition": condition,
        "policy": policy,
        "answerExtractionRisk": risk,
        "studentReasoningRequired": policy in {"require_self_explanation", "require_prediction"},
    }


def prescreen_candidate(
    constraint_report: dict[str, Any],
    sync_report: dict[str, Any],
    condition: str = "I0",
) -> dict[str, Any]:
    if condition not in {"I0", "I1", "I2", "I3", "I4"}:
        raise ValueError(f"不支持的 E9 条件：{condition}")
    constraint = float(constraint_report.get("constraintSatisfaction", 0.0))
    temporal = float(sync_report.get("temporalAlignment", 0.0))
    semantic = float(sync_report.get("semanticAlignment", 0.0))
    score = round(0.4 * constraint + 0.3 * temporal + 0.3 * semantic, 4)
    failures = []
    if constraint < 0.9:
        failures.append("pedagogical_constraints")
    if temporal < 0.8:
        failures.append("temporal_alignment")
    if semantic < 0.9:
        failures.append("semantic_alignment")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": "E9",
        "condition": condition,
        "mode": "deterministic_proxy_baseline",
        "score": score,
        "passed": not failures,
        "failures": failures,
        "requiresHumanCalibration": True,
        "usage": "generation_prescreen_only",
    }
