from __future__ import annotations

from pathlib import Path
from typing import Any


GESTURE_TYPES = (
    "Action_Greet",
    "Action_Explain",
    "Action_Point_Left",
    "Action_Point_Right",
    "Action_Think",
    "Action_Summarize",
)

GESTURE_ALIASES = {
    "neutral": "Action_Explain",
    "neutral_explain": "Action_Explain",
    "single_hand_out": "Action_Point_Right",
    "right_hand_point": "Action_Point_Right",
    "left_hand_point": "Action_Point_Left",
    "two_hands_out": "Action_Explain",
    "both_hands_open": "Action_Explain",
    "right_hand_count": "Action_Explain",
    "both_hands_compare": "Action_Summarize",
    "deictic_point": "Action_Point_Right",
    "open_palm_prompt": "Action_Explain",
}


def longcat_engine_readiness(
    bundle_root: str | Path,
    environment_python: str | Path | None = None,
) -> dict[str, Any]:
    bundle = Path(bundle_root).resolve()
    repo = bundle / "LongCat-Video"
    checkpoint = bundle / "weights" / "LongCat-Video-Avatar-1.5"
    base = bundle / "weights" / "LongCat-Video"
    python = (
        Path(environment_python).expanduser().absolute()
        if environment_python
        else bundle / "envs" / "longcat-avatar15-xtuners" / "bin" / "python"
    )
    checks = {
        "repository": (repo / "run_demo_avatar_single_audio_to_video.py").is_file(),
        "python": python.is_file(),
        "baseTokenizer": (base / "tokenizer").is_dir(),
        "baseTextEncoder": (base / "text_encoder").is_dir(),
        "baseVae": (base / "vae").is_dir(),
        "avatarInt8": any((checkpoint / "base_model_int8").glob("*.safetensors")),
        "whisper": (checkpoint / "whisper-large-v3").is_dir(),
        "distillLora": (checkpoint / "lora" / "dmd_lora.safetensors").is_file(),
    }
    return {
        "engine": "longcat-video-avatar-1.5",
        "ready": all(checks.values()),
        "checks": checks,
        "repository": str(repo),
        "bundle": str(bundle),
        "checkpoint": str(checkpoint),
        "python": str(python),
        "recommendedMode": "int8_distilled_480p_two_gpu",
    }


def _asset(value: Any) -> str | None:
    if isinstance(value, dict):
        raw = value.get("path") or value.get("url") or value.get("name")
    else:
        raw = value
    text = str(raw or "").strip()
    return text or None


def build_teacher_profile(
    profile_id: str,
    reference_image: Any = None,
    reference_audio: Any = None,
    gesture_clips: dict[str, Any] | None = None,
    consent: dict[str, Any] | None = None,
    full_body_engine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clips = gesture_clips or {}
    normalized_clips = {gesture: _asset(clips.get(gesture)) for gesture in GESTURE_TYPES}
    image = _asset(reference_image)
    audio = _asset(reference_audio)
    consent_value = consent or {}
    missing = []
    if not image:
        missing.append("reference_image")
    if not audio:
        missing.append("reference_audio")
    for gesture, path in normalized_clips.items():
        if not path:
            missing.append(f"gesture:{gesture}")
    authorized = bool(consent_value.get("authorized", False))
    engine = full_body_engine or {"name": None, "available": False}
    if not authorized:
        missing.append("consent")
    return {
        "schemaVersion": "2026.1",
        "profileId": profile_id,
        "identity": {"referenceImage": image},
        "voice": {"referenceAudio": audio},
        "gestureClips": normalized_clips,
        "fullBodyEngine": engine,
        "consent": {
            "authorized": authorized,
            "scope": str(consent_value.get("scope", "")),
            "source": str(consent_value.get("source", "")),
        },
        "readiness": {
            "faceCourse": bool(image and audio and authorized),
            "gestureCourse": bool(
                image
                and audio
                and authorized
                and (all(normalized_clips.values()) or engine.get("available"))
            ),
            "missing": missing,
        },
    }


def validate_profile_files(profile: dict[str, Any], artifact_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(artifact_root).resolve() if artifact_root else None

    def resolve(value: str | None) -> Path | None:
        if not value:
            return None
        text = value
        if root and text.startswith("/artifacts/"):
            return root / text.removeprefix("/artifacts/")
        return Path(text).expanduser()

    assets = {
        "reference_image": profile.get("identity", {}).get("referenceImage"),
        "reference_audio": profile.get("voice", {}).get("referenceAudio"),
        **{
            f"gesture:{name}": value
            for name, value in profile.get("gestureClips", {}).items()
        },
    }
    checks = {}
    for name, value in assets.items():
        path = resolve(value)
        checks[name] = {
            "configured": bool(value),
            "exists": bool(path and path.is_file()),
            "path": str(path) if path else None,
        }
    return {
        "profileId": profile.get("profileId"),
        "checks": checks,
        "faceAssetsAvailable": all(
            checks[name]["exists"] for name in ("reference_image", "reference_audio")
        ),
        "gestureAssetsAvailable": all(
            checks[f"gesture:{name}"]["exists"] for name in GESTURE_TYPES
        ),
    }


def schedule_gestures(
    pedagogical_ir: dict[str, Any],
    teacher_profile: dict[str, Any],
    minimum_gap_seconds: float = 6.0,
) -> dict[str, Any]:
    clips = teacher_profile.get("gestureClips", {})
    schedule = []
    last_gesture_end = -minimum_gap_seconds
    missing_requested: set[str] = set()
    for event in pedagogical_ir.get("timeline", {}).get("events", []):
        intent = str(event.get("teachingIntent", ""))
        gesture_hint = str(event.get("instructorBehavior", {}).get("gesture", ""))
        concept = str(event.get("concept", ""))
        explicit = GESTURE_ALIASES.get(gesture_hint, gesture_hint)
        if explicit in GESTURE_TYPES:
            requested = explicit
        elif any(token in concept for token in ("欢迎", "开始", "导入", "问候")):
            requested = "Action_Greet"
        elif any(token in concept for token in ("对比", "比较", "两类", "差异")):
            requested = "Action_Explain"
        elif intent == "retrieve_and_self_explain" or any(
            token in concept for token in ("总结", "结论", "共同", "结合")
        ):
            requested = "Action_Summarize"
        elif any(token in concept for token in ("思考", "推理", "不确定", "为什么")):
            requested = "Action_Think"
        elif any(token in concept for token in ("左侧", "左边")):
            requested = "Action_Point_Left"
        elif any(token in concept for token in ("右侧", "右边")):
            requested = "Action_Point_Right"
        elif any(
            token in concept for token in ("图", "公式", "角", "线", "位置", "数值")
        ):
            requested = "Action_Point_Right"
        else:
            requested = "Action_Explain"
        start = float(event.get("start", 0))
        end = float(event.get("end", start + 1))
        if requested != "Action_Explain" and start - last_gesture_end < minimum_gap_seconds:
            requested = "Action_Explain"
        clip = clips.get(requested)
        fallback = None
        if not clip:
            engine = teacher_profile.get("fullBodyEngine", {})
            if engine.get("available"):
                fallback = f"generate_with:{engine.get('name', 'full_body_engine')}"
            else:
                missing_requested.add(requested)
                fallback = "face_only" if teacher_profile.get("readiness", {}).get("faceCourse") else "unavailable"
        if requested != "Action_Explain":
            last_gesture_end = end
        schedule.append(
            {
                "eventId": event.get("eventId"),
                "concept": concept,
                "start": start,
                "end": end,
                "gesture": requested,
                "clip": clip,
                "fallback": fallback,
                "gazeTarget": event.get("visual", {}).get("target"),
            }
        )
    return {
        "schemaVersion": "2026.1",
        "profileId": teacher_profile.get("profileId"),
        "eventCount": len(schedule),
        "minimumGestureGapSeconds": minimum_gap_seconds,
        "gestureAssetsReady": bool(teacher_profile.get("readiness", {}).get("gestureCourse")),
        "missingRequestedGestures": sorted(missing_requested),
        "schedule": schedule,
    }


def schedule_outline_actions(
    outline: dict[str, Any],
    scene_times: dict[int, dict[str, float]],
) -> dict[str, Any]:
    schedule = []
    for index, scene in enumerate(outline.get("scenes", []), start=1):
        scene_id = int(scene.get("scene_id", index))
        timing = scene_times.get(scene_id, {})
        action = GESTURE_ALIASES.get(
            str(scene.get("full_body_action", "Action_Explain")),
            str(scene.get("full_body_action", "Action_Explain")),
        )
        if action not in GESTURE_TYPES:
            raise ValueError(f"不支持的全身动作：{action}")
        schedule.append(
            {
                "eventId": f"s{scene_id:02d}_action",
                "sceneId": scene_id,
                "concept": str(scene.get("title", "")),
                "start": float(timing.get("start", 0.0)),
                "end": float(timing.get("end", timing.get("start", 0.0) + 4.0)),
                "gesture": action,
                "triggerSentence": str(scene.get("action_trigger_sentence", "")),
                "semanticAlignment": str(scene.get("action_semantic_alignment", scene.get("visual_description", ""))),
                "gazeTarget": (
                    scene.get("visual_focus", [{}])[0].get("object")
                    if scene.get("visual_focus")
                    else None
                ),
                "fallback": "generate_with:longcat-video-avatar-1.5",
            }
        )
    return {
        "schemaVersion": "2026.1",
        "supportedActions": list(GESTURE_TYPES),
        "eventCount": len(schedule),
        "schedule": schedule,
    }
