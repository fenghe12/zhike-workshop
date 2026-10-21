from __future__ import annotations

import json
from pathlib import Path
from typing import Any


AI_LITERACY_PRESET = {
    "demoId": "ai-literacy-general",
    "title": "人工智能通识课",
    "audience": "高校非计算机专业学习者",
    "objective": "理解人工智能的基本概念、发展历程、典型应用、局限与责任边界。",
    "units": [
        "人工智能的定义与发展历程",
        "机器学习、深度学习与生成式人工智能",
        "感知、推理、规划与智能体",
        "教育、医疗、交通和工业应用",
        "模型幻觉、偏见、隐私与安全",
        "如何负责任地使用人工智能",
    ],
    "interactionPlan": [
        {"minute": 5, "type": "prediction", "prompt": "哪些任务需要学习能力？"},
        {"minute": 10, "type": "contrast", "prompt": "规则系统和学习系统有什么区别？"},
        {"minute": 15, "type": "case", "prompt": "判断一个教育 AI 应用的风险。"},
        {"minute": 20, "type": "quiz", "prompt": "总结生成式人工智能的能力和边界。"},
    ],
}


def build_demo_course_manifest(runtime_root: str | Path) -> dict[str, Any]:
    root = Path(runtime_root).resolve()
    preview_assets = root / "previews" / "ai4edu" / "assets"
    runtime_assets = root / "assets"
    candidates = {
        "finalVideo": preview_assets / "final-video.mp4",
        "poster": preview_assets / "full-course-poster.jpg",
        "pptx": preview_assets / "generated-course.pptx",
        "subtitles": preview_assets / "subtitles.srt",
        "referenceImage": runtime_assets / "images" / "hdtf-reference.jpg",
        "referenceAudio": runtime_assets / "audio" / "speaker-reference-10s.wav",
        "mathLesson": preview_assets / "code2video-math.mp4",
        "physicsLesson": preview_assets / "code2video-physics.mp4",
        "chemistryLesson": preview_assets / "code2video-chemistry.mp4",
    }
    files = {
        key: {"path": str(path), "exists": path.is_file(), "sizeBytes": path.stat().st_size if path.is_file() else None}
        for key, path in candidates.items()
    }
    required = ("finalVideo", "poster", "pptx", "subtitles", "referenceImage", "referenceAudio")
    return {
        "schemaVersion": "2026.1",
        "preset": AI_LITERACY_PRESET,
        "status": "ready_for_internal_preview"
        if all(files[key]["exists"] for key in required)
        else "incomplete",
        "files": files,
        "gestureAssetsReady": False,
        "marketingAuthorizationStatus": "not_recorded",
        "usageRestriction": "内部演示；公开推广前必须确认人像、声音与课程素材授权",
    }


def prepare_demo_package(runtime_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    manifest = build_demo_course_manifest(runtime_root)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "demo_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest"] = str(path)
    return manifest
