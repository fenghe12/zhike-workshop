from __future__ import annotations

import csv
import json
import random
import time
import uuid
from pathlib import Path
from typing import Any

from .adaptive_teaching import build_adaptive_experiment, normalize_learner_state
from .advanced_experiments import (
    build_personalization_plan,
    check_pedagogical_alignment,
    prescreen_candidate,
    select_proactive_intervention,
    update_structured_memory,
)
from .code_lessons import get_lesson_spec
from .pedagogical_ir import (
    E1_CONDITIONS,
    E2_CONDITIONS,
    build_e2_variants,
    compile_lesson_ir,
)


E3_CONDITIONS = ["C0", "C1", "C2", "C3", "C4"]
E4_CONDITIONS = ["D0", "D1", "D2", "D3", "D4"]
E5_CONDITIONS = ["E0", "E1", "E2", "E3", "E4", "E5"]
E6_CONDITIONS = ["F0", "F1", "F2", "F3", "F4"]
E7_CONDITIONS = ["G0", "G1", "G2", "G3", "G4", "G5"]
E8_CONDITIONS = ["H0", "H1", "H2", "H3", "H4"]
E9_CONDITIONS = ["I0", "I1", "I2", "I3", "I4"]


DEFAULT_LEARNER_STATES = {
    "linear-function": {"mastery": 0.42, "attention": 0.76, "engagement": 0.70, "cognitiveLoad": 0.56, "misconception": "conceptual_gap"},
    "light-reflection": {"mastery": 0.58, "attention": 0.38, "engagement": 0.62, "cognitiveLoad": 0.48, "misconception": "procedural_error"},
    "ph-indicator": {"mastery": 0.36, "attention": 0.71, "engagement": 0.67, "cognitiveLoad": 0.82, "misconception": "recall_failure"},
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class ExperimentRunner:
    def __init__(self, output_root: str | Path):
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _conditions(
        self,
        experiment_id: str,
        lesson_id: str,
        state: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        spec = get_lesson_spec(lesson_id)
        base_ir, base_report = compile_lesson_ir(spec, "A4", state)
        if experiment_id == "E1":
            result = {}
            for condition in E1_CONDITIONS:
                ir, report = compile_lesson_ir(spec, condition, state)
                result[condition] = {
                    "configuration": ir["experiment"],
                    "automaticMetrics": report,
                    "artifacts": {"pedagogicalIr": ir},
                }
            return result
        if experiment_id == "E2":
            variants = build_e2_variants(base_ir)["variants"]
            return {
                condition: {
                    "configuration": {"description": value["description"]},
                    "automaticMetrics": value["evaluation"],
                    "artifacts": {"pedagogicalIr": value["ir"]},
                }
                for condition, value in variants.items()
            }
        if experiment_id in {"E3", "E5"}:
            adaptive = build_adaptive_experiment(base_ir, state)
            if experiment_id == "E3":
                return {
                    condition: {
                        "configuration": value,
                        "automaticMetrics": {"stateFieldCount": value["fieldCount"]},
                        "artifacts": {},
                    }
                    for condition, value in adaptive["e3Variants"].items()
                }
            return {
                condition: {
                    "configuration": value["policyReport"],
                    "automaticMetrics": {
                        "actionCount": len(value["policyReport"]["actions"]),
                        "triggeredEventCount": sum(
                            event["learnerStateTrigger"]["matched"]
                            for event in value["adaptiveIr"]["timeline"]["events"]
                        ),
                    },
                    "artifacts": {"adaptiveIr": value["adaptiveIr"]},
                }
                for condition, value in adaptive["e5Variants"].items()
            }
        if experiment_id == "E4":
            return {
                condition: {
                    "configuration": select_proactive_intervention(
                        state,
                        condition,
                        {"stateUncertainty": 0.4, "elapsedSinceInterventionSeconds": 120, "atCheckpoint": True},
                    ),
                    "automaticMetrics": {},
                    "artifacts": {},
                }
                for condition in E4_CONDITIONS
            }
        if experiment_id == "E6":
            return {
                condition: {
                    "configuration": update_structured_memory(
                        None,
                        {"concept": spec["topic"], "success": state["mastery"] >= 0.6, "confidence": 0.85, "spacingIntervalDays": 7},
                        condition,
                    ),
                    "automaticMetrics": {},
                    "artifacts": {},
                }
                for condition in E6_CONDITIONS
            }
        if experiment_id == "E7":
            return {
                condition: {
                    "configuration": build_personalization_plan(state, {"interestDomain": "STEM"}, condition),
                    "automaticMetrics": {},
                    "artifacts": {},
                }
                for condition in E7_CONDITIONS
            }
        if experiment_id == "E8":
            return {
                condition: {
                    "configuration": check_pedagogical_alignment(
                        state,
                        {"requestsDirectAnswer": True, "studentReasoning": ""},
                        condition,
                    ),
                    "automaticMetrics": {},
                    "artifacts": {},
                }
                for condition in E8_CONDITIONS
            }
        if experiment_id == "E9":
            aligned = build_e2_variants(base_ir)["variants"]["B4"]["evaluation"]
            return {
                condition: {
                    "configuration": {"proxyMode": condition},
                    "automaticMetrics": prescreen_candidate(base_report, aligned, condition),
                    "artifacts": {},
                }
                for condition in E9_CONDITIONS
            }
        raise ValueError(f"不支持的实验编号：{experiment_id}")

    @staticmethod
    def _human_rating_template(path: Path, rows: list[dict[str, Any]]) -> None:
        fields = [
            "run_id", "lesson_id", "experiment_id", "condition", "rater_id",
            "factual_correctness", "pedagogical_structure", "visual_clarity",
            "cross_modal_alignment", "social_presence", "comments",
        ]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fields})

    @staticmethod
    def _learning_study_template(path: Path, rows: list[dict[str, Any]]) -> None:
        fields = [
            "participant_id", "lesson_id", "experiment_id", "condition",
            "pretest", "posttest", "delayed_test", "near_transfer", "far_transfer",
            "interest", "cognitive_load", "social_presence", "aoi_dwell_time",
            "scanpath_efficiency", "response_time_seconds", "notes",
        ]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fields})

    def run(
        self,
        experiment_ids: list[str],
        lesson_ids: list[str],
        seed: int = 20260822,
    ) -> dict[str, Any]:
        random.seed(seed)
        run_id = "run_" + uuid.uuid4().hex[:12]
        run_root = self.output_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        started = time.time()
        result_rows: list[dict[str, Any]] = []
        human_rows: list[dict[str, Any]] = []
        study_rows: list[dict[str, Any]] = []
        for lesson_id in lesson_ids:
            state = normalize_learner_state(DEFAULT_LEARNER_STATES.get(lesson_id, {}))
            for experiment_id in experiment_ids:
                conditions = self._conditions(experiment_id, lesson_id, state)
                for condition, value in conditions.items():
                    path = run_root / lesson_id / experiment_id / f"{condition}.json"
                    _write_json(path, value)
                    result_rows.append(
                        {
                            "lessonId": lesson_id,
                            "experimentId": experiment_id,
                            "condition": condition,
                            "automaticMetrics": value["automaticMetrics"],
                            "humanOutcomeStatus": "not_measured",
                            "artifact": str(path),
                        }
                    )
                    human_rows.append({"run_id": run_id, "lesson_id": lesson_id, "experiment_id": experiment_id, "condition": condition})
                    study_rows.append({"lesson_id": lesson_id, "experiment_id": experiment_id, "condition": condition})
        human_path = run_root / "human_rating_template.csv"
        study_path = run_root / "learning_study_template.csv"
        self._human_rating_template(human_path, human_rows)
        self._learning_study_template(study_path, study_rows)
        manifest = {
            "runId": run_id,
            "seed": seed,
            "experimentIds": experiment_ids,
            "lessonIds": lesson_ids,
            "controls": {
                "sameBaseModel": True,
                "sameRenderer": True,
                "sameInformationBudget": True,
                "sameTargetDuration": True,
            },
            "conditionCount": len(result_rows),
            "automaticEvaluationOnly": True,
            "humanOutcomeStatus": "not_measured",
            "results": result_rows,
            "humanRatingTemplate": str(human_path),
            "learningStudyTemplate": str(study_path),
            "elapsedSeconds": round(time.time() - started, 3),
        }
        manifest_path = run_root / "run_manifest.json"
        _write_json(manifest_path, manifest)
        manifest["manifest"] = str(manifest_path)
        return manifest
