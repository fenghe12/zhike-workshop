from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import NormalDist, mean, stdev
from typing import Any


SCHEMA_VERSION = "2026.1"

PRIMARY_ENDPOINTS = {
    "E1": ["pedagogical_constraint_satisfaction", "far_transfer"],
    "E2": ["aoi_dwell_time", "far_transfer"],
    "E3": ["state_diagnosis_accuracy", "delayed_test"],
    "E4": ["intervention_efficiency", "cognitive_load"],
    "E5": ["misconception_repair", "near_transfer"],
    "E6": ["history_aware_action_accuracy", "delayed_test"],
    "E7": ["far_transfer", "interest"],
    "E8": ["answer_extraction_rate", "independent_problem_solving"],
    "E9": ["proxy_human_spearman", "bad_configuration_recall"],
}


def approximate_two_group_sample_size(
    effect_size: float = 0.5,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int:
    if effect_size <= 0:
        raise ValueError("effect_size 必须大于 0")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("alpha 和 power 必须位于 0 与 1 之间")
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power = normal.inv_cdf(power)
    return int(2 * ((z_alpha + z_power) / effect_size) ** 2 + 0.9999)


def build_experiment_protocol(
    experiment_id: str,
    conditions: list[str],
    effect_size: float = 0.5,
    alpha: float = 0.05,
    power: float = 0.8,
) -> dict[str, Any]:
    if experiment_id not in PRIMARY_ENDPOINTS:
        raise ValueError(f"不支持的实验编号：{experiment_id}")
    per_two_group = approximate_two_group_sample_size(effect_size, alpha, power)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": experiment_id,
        "conditions": conditions,
        "design": "balanced_randomized_between_subjects",
        "randomization": {
            "stratifyBy": ["lesson_id", "pretest_band"],
            "allocation": "equal",
            "seedRequired": True,
        },
        "primaryEndpoints": PRIMARY_ENDPOINTS[experiment_id],
        "secondaryEndpoints": [
            "posttest",
            "retention",
            "near_transfer",
            "far_transfer",
            "interest",
            "cognitive_load",
            "social_presence",
        ],
        "measurementSchedule": [
            "pretest",
            "immediate_posttest",
            "delayed_test_7_to_14_days",
        ],
        "exclusionRules": [
            "missing_primary_endpoint",
            "failed_attention_check",
            "video_completion_below_80_percent",
            "duplicate_participant_record",
        ],
        "analysis": {
            "reportEffectSize": True,
            "reportConfidenceInterval": True,
            "reportMissingness": True,
            "correctionForMultipleComparisons": "holm",
        },
        "powerPlanning": {
            "effectSizeAssumption": effect_size,
            "alpha": alpha,
            "power": power,
            "approximateParticipantsPerTwoGroupComparison": per_two_group,
            "note": "多条件正式实验需根据先导数据和主要比较重新进行功效分析",
        },
        "registrationStatus": "draft_not_preregistered",
    }


NUMERIC_METRICS = [
    "pretest",
    "posttest",
    "delayed_test",
    "near_transfer",
    "far_transfer",
    "interest",
    "cognitive_load",
    "social_presence",
    "aoi_dwell_time",
    "scanpath_efficiency",
    "response_time_seconds",
]


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cohen_d(first: list[float], second: list[float]) -> float | None:
    if len(first) < 2 or len(second) < 2:
        return None
    first_sd = stdev(first)
    second_sd = stdev(second)
    pooled = sqrt(
        ((len(first) - 1) * first_sd**2 + (len(second) - 1) * second_sd**2)
        / (len(first) + len(second) - 2)
    )
    if pooled == 0:
        return 0.0
    return round((mean(first) - mean(second)) / pooled, 4)


def analyze_learning_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("lesson_id", "")),
            str(row.get("experiment_id", "")),
            str(row.get("condition", "")),
        )
        groups[key].append(row)
    summaries = []
    metric_values: dict[tuple[str, str, str, str], list[float]] = {}
    total_missing = 0
    for (lesson_id, experiment_id, condition), values in sorted(groups.items()):
        metrics = {}
        for metric in NUMERIC_METRICS:
            observed = [number for row in values if (number := _number(row.get(metric))) is not None]
            total_missing += len(values) - len(observed)
            metric_values[(lesson_id, experiment_id, condition, metric)] = observed
            metrics[metric] = {
                "n": len(observed),
                "mean": round(mean(observed), 4) if observed else None,
                "sd": round(stdev(observed), 4) if len(observed) >= 2 else None,
                "status": "measured" if observed else "not_measured",
            }
        pre = metric_values[(lesson_id, experiment_id, condition, "pretest")]
        post = metric_values[(lesson_id, experiment_id, condition, "posttest")]
        paired = min(len(pre), len(post))
        metrics["raw_learning_gain"] = {
            "n": paired,
            "mean": round(mean([post[index] - pre[index] for index in range(paired)]), 4)
            if paired
            else None,
            "status": "measured" if paired else "not_measured",
        }
        summaries.append(
            {
                "lessonId": lesson_id,
                "experimentId": experiment_id,
                "condition": condition,
                "rowCount": len(values),
                "metrics": metrics,
            }
        )
    pairwise = []
    by_experiment: dict[tuple[str, str], list[str]] = defaultdict(list)
    for lesson_id, experiment_id, condition in groups:
        if condition not in by_experiment[(lesson_id, experiment_id)]:
            by_experiment[(lesson_id, experiment_id)].append(condition)
    for (lesson_id, experiment_id), conditions in sorted(by_experiment.items()):
        conditions = sorted(conditions)
        for first_index in range(len(conditions)):
            for second_index in range(first_index + 1, len(conditions)):
                first, second = conditions[first_index], conditions[second_index]
                for metric in ("posttest", "delayed_test", "near_transfer", "far_transfer"):
                    first_values = metric_values.get((lesson_id, experiment_id, first, metric), [])
                    second_values = metric_values.get((lesson_id, experiment_id, second, metric), [])
                    pairwise.append(
                        {
                            "lessonId": lesson_id,
                            "experimentId": experiment_id,
                            "first": first,
                            "second": second,
                            "metric": metric,
                            "cohenD": _cohen_d(first_values, second_values),
                            "status": "measured"
                            if len(first_values) >= 2 and len(second_values) >= 2
                            else "insufficient_data",
                        }
                    )
    measured_values = sum(
        metric["n"]
        for summary in summaries
        for name, metric in summary["metrics"].items()
        if name != "raw_learning_gain"
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "rowCount": len(rows),
        "groupCount": len(groups),
        "measuredValueCount": measured_values,
        "missingValueCount": total_missing,
        "humanOutcomeStatus": "measured" if measured_values else "not_measured",
        "groupSummaries": summaries,
        "pairwiseEffectSizes": pairwise,
    }
