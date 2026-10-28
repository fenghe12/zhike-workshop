"""Validate and snapshot translation quality requirements for each task."""
import math

DEFAULT_POLICY = {"semantic_similarity": 0.85, "terminology_coverage": 0.9,
                  "formula_number_proper_name_accuracy": 1.0, "contextual_consistency": 0.85,
                  "maxRetries": 3}


def validate_policy(value=None):
    if value is not None and not isinstance(value, dict):
        raise ValueError("校验参数必须为对象")
    policy = {**DEFAULT_POLICY, **(value or {})}
    if set(policy) != set(DEFAULT_POLICY):
        raise ValueError("包含不支持的校验参数")
    for name in DEFAULT_POLICY:
        current = policy[name]
        if name == "maxRetries":
            if isinstance(current, bool) or not isinstance(current, int) or not 0 <= current <= 3:
                raise ValueError("自动修正次数必须为 0 至 3 的整数")
        elif isinstance(current, bool) or not isinstance(current, (int, float)) or not math.isfinite(current) or not 0 <= current <= 1:
            raise ValueError("校验阈值必须在 0 至 1 之间")
    return policy


def meets_thresholds(report, policy):
    return all(isinstance(report.get(key), (float, int)) and math.isfinite(report[key])
               and policy[key] <= report[key] <= 1 for key in DEFAULT_POLICY if key != "maxRetries")
