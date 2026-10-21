from __future__ import annotations

import time
from typing import Any, Callable


STAGE_DEVICES = {"S1": "CPU", "S2": "CPU/API", "S3": "NPU", "S4": "NPU", "S5": "CPU"}


class PipelinePerformanceRecorder:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.started = time.perf_counter()
        self.stages: dict[str, dict[str, Any]] = {}

    def run_stage(self, stage: str, function: Callable[[], Any]) -> Any:
        started = time.perf_counter()
        status = "completed"
        try:
            return function()
        except Exception:
            status = "failed"
            raise
        finally:
            self.stages[stage] = {
                "device": STAGE_DEVICES.get(stage, "unknown"),
                "elapsedSeconds": round(time.perf_counter() - started, 3),
                "status": status,
            }

    def report(
        self,
        output_duration_seconds: float | None = None,
        npu_hourly_cost: float | None = None,
    ) -> dict[str, Any]:
        total = round(time.perf_counter() - self.started, 3)
        npu_seconds = round(
            sum(
                float(value["elapsedSeconds"])
                for value in self.stages.values()
                if value["device"] == "NPU"
            ),
            3,
        )
        npu_hours = round(npu_seconds / 3600, 6)
        duration = float(output_duration_seconds or 0)
        return {
            "schemaVersion": "2026.1",
            "taskId": self.task_id,
            "totalElapsedSeconds": total,
            "outputDurationSeconds": duration or None,
            "realtimeFactor": round(total / duration, 4) if duration > 0 else None,
            "stages": self.stages,
            "npuSeconds": npu_seconds,
            "npuHours": npu_hours,
            "npuHourlyCost": npu_hourly_cost,
            "estimatedNpuCost": round(npu_hours * npu_hourly_cost, 4)
            if npu_hourly_cost is not None
            else None,
            "costStatus": "measured"
            if npu_hourly_cost is not None
            else "hourly_price_not_configured",
        }
