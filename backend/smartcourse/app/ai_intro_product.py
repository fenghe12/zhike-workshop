from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ai_intro_status(root: str | Path) -> dict[str, Any]:
    product = Path(root).resolve()
    outline = _read(product / "outline.json")
    manim = _read(product / "manim-v2/manifest.json") or _read(product / "manim/manifest.json")
    tts = _read(product / "s3/timeline.json")
    avatar = _read(product / "s4-longcat/manifest.json")
    compose = _read(product / "s5/manifest.json")
    actions = []
    interruptions = []
    scene_timeline = []
    if outline:
        actions = [
            {
                "sceneId": item.get("scene_id"),
                "sceneTitle": item.get("title"),
                "action": item.get("full_body_action"),
                "triggerSentence": item.get("action_trigger_sentence"),
            }
            for item in outline.get("scenes", [])
        ]
        interruptions = [
            {
                "interruptId": str(item.get("interrupt_id")),
                "afterScene": item.get("after_scene"),
                "studentState": item.get("student_state"),
                "studentUtterance": item.get("student_utterance"),
                "branchTitle": item.get("branch_title"),
                "carrier": item.get("branch_carrier"),
                "resumeInstruction": item.get("resume_instruction"),
            }
            for item in outline.get("interruptions", [])
        ]
    if compose:
        cursor = 0.0
        tts_by_scene = {
            int(item.get("sceneId", index)): item
            for index, item in enumerate((tts or {}).get("scenes", []), start=1)
        }
        for index, item in enumerate(compose.get("main", []), start=1):
            scene_id = int(item.get("sceneId", index))
            duration = float(
                item.get("result", {}).get("durationSeconds")
                or tts_by_scene.get(scene_id, {}).get("durationSeconds")
                or 0.0
            )
            scene_timeline.append(
                {
                    "sceneId": scene_id,
                    "startSeconds": round(cursor, 3),
                    "endSeconds": round(cursor + duration, 3),
                    "durationSeconds": round(duration, 3),
                }
            )
            cursor += duration
    timeline_by_scene = {int(item["sceneId"]): item for item in scene_timeline}
    for interruption in interruptions:
        after_scene = int(interruption.get("afterScene", 0))
        interruption["resumeTimeSeconds"] = timeline_by_scene.get(after_scene, {}).get(
            "endSeconds"
        )
    stages = {
        "outline": bool(outline),
        "manim": bool(manim and manim.get("passed")),
        "tts": bool(tts and len(tts.get("scenes", [])) == 6 and len(tts.get("interruptions", [])) == 4),
        "longcat": bool(avatar and avatar.get("passed")),
        "compose": bool(compose and compose.get("passed")),
    }
    return {
        "course": outline.get("course", {}) if outline else {},
        "root": str(product),
        "stages": stages,
        "ready": all(stages.values()),
        "sceneCount": len(outline.get("scenes", [])) if outline else 0,
        "sceneTimeline": scene_timeline,
        "fullBodyActions": actions,
        "interruptions": interruptions,
        "mainVideo": compose.get("mainVideo") if compose else None,
        "playback": compose.get("playback", []) if compose else [],
    }


def execute_fixed_ai_intro_interrupt(root: str | Path, interrupt_id: str) -> dict[str, Any]:
    status = ai_intro_status(root)
    interruption = next(
        (item for item in status["interruptions"] if item["interruptId"] == str(interrupt_id)),
        None,
    )
    if not interruption:
        raise ValueError(f"固定打断不存在：{interrupt_id}")
    playback_item = next(
        (
            item
            for item in status.get("playback", [])
            if item.get("type") == "interrupt_option" and str(item.get("interruptId")) == str(interrupt_id)
        ),
        {},
    )
    after_scene = int(interruption["afterScene"])
    resume_time = interruption.get("resumeTimeSeconds")
    return {
        "course": status["course"],
        "interrupt": interruption,
        "stateTrace": [
            {"state": "playing", "sceneId": after_scene},
            {"state": "paused", "reason": "student_interrupt", "studentUtterance": interruption["studentUtterance"]},
            {"state": "branch_generating", "carrier": interruption["carrier"]},
            {"state": "branch_playing", "video": playback_item.get("branchVideo")},
            {
                "state": "resumed",
                "sceneId": after_scene + 1,
                "timeSeconds": resume_time,
                "instruction": interruption["resumeInstruction"],
            },
        ],
        "branchVideo": playback_item.get("branchVideo"),
        "resumeScene": after_scene + 1,
        "resumeTimeSeconds": resume_time,
        "ready": bool(playback_item.get("branchVideo")),
    }
