from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import SUPPORTED_LANGUAGES


STAGES = [
    {
        "key": "s1",
        "index": 1,
        "code": "S1",
        "title": "课件结构化",
        "agent": "课程生成智能体",
        "summary": "解析已有 PPT，或依据课程主题生成大纲、逐页内容、讲稿及配套 PPT。",
    },
    {
        "key": "s2",
        "index": 2,
        "code": "S2",
        "title": "多语种翻译与校验",
        "agent": "翻译校验智能体",
        "summary": "翻译 PPT 与讲稿，并执行语义、术语、公式数字专名和整体语义校验。",
    },
    {
        "key": "s3",
        "index": 3,
        "code": "S3",
        "title": "语音合成",
        "agent": "语音合成智能体",
        "summary": "依据参考音频保持说话人声线，生成句级时间戳和 PPT 页级时间轴。",
    },
    {
        "key": "s4",
        "index": 4,
        "code": "S4",
        "title": "数字人生成",
        "agent": "数字人生成智能体",
        "summary": "依据参考图片生成唇形、表情与头部动作，并自动选择页面放置区域。",
    },
    {
        "key": "s5",
        "index": 5,
        "code": "S5",
        "title": "视频合成",
        "agent": "视频合成与字幕模块",
        "summary": "按统一时间轴合成 PPT、数字人、语音和字幕，输出课程视频与 SRT。",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_language(value: str) -> str:
    value = value.strip()
    if value in SUPPORTED_LANGUAGES:
        return SUPPORTED_LANGUAGES[value]
    if value in SUPPORTED_LANGUAGES.values():
        return value
    raise ValueError(f"不支持的目标语言：{value}")


def validate_creation(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("任务名称不能为空")
    mode = str(payload.get("mode", "")).strip()
    if mode not in {"upload", "topic", "code"}:
        raise ValueError("mode 必须为 upload、topic 或 code")
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    if mode == "upload":
        ppt = inputs.get("ppt")
        if not isinstance(ppt, dict) or not str(ppt.get("name", "")).lower().endswith((".pptx", ".pdf")):
            raise ValueError("请上传有效的 PPTX 或 PDF 课件")
        script = inputs.get("script")
        if script is not None and (
            not isinstance(script, dict) or not str(script.get("name", "")).lower().endswith(".docx")
        ):
            raise ValueError("逐页讲稿须为 DOCX 文件")
    if mode == "topic" and not str(inputs.get("topic", "")).strip():
        raise ValueError("课程主题不能为空")
    if mode == 'topic':
        for key, default, maximum in [('totalPages', 10, 30), ('durationMinutes', 10, 180)]:
            value = inputs.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
                raise ValueError(f'{key} 必须为 1 至 {maximum} 的整数')
        if not str(inputs.get('targetLearners', '高校本科生')).strip():
            raise ValueError('请填写教学对象')
    if mode == "code":
        lesson_id=str(inputs.get("lessonId", "")).strip()
        code_text=str(inputs.get("codeText", "")).strip()
        if bool(lesson_id)==bool(code_text):
            raise ValueError("请选择示例动画课程或提供待讲解代码")
        if code_text:
            if len(code_text)>30000:raise ValueError("待讲解代码不能超过 30000 字符")
            page_count=inputs.get("totalPages",3)
            if isinstance(page_count,bool) or not isinstance(page_count,int) or not 1<=page_count<=10:
                raise ValueError("代码讲解页数必须为 1 至 10")

    raw_languages = payload.get("targetLanguages", [])
    if not isinstance(raw_languages, list) or not raw_languages:
        raise ValueError("至少选择一种目标语言")
    source_language = '中文' if mode == 'topic' else normalize_language(str(payload.get("sourceLanguage", "中文")))
    target_languages = list(dict.fromkeys(normalize_language(str(item)) for item in raw_languages))
    return {
        "name": name,
        "mode": mode,
        "inputs": copy.deepcopy(inputs),
        "sourceLanguage": source_language,
        "targetLanguages": target_languages,
    }


def create_task(payload: dict[str, Any], template: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = validate_creation(payload)
    now = utc_now()
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task = copy.deepcopy(template or {})
    task.update(
        {
            "id": task_id,
            "name": normalized["name"],
            "mode": normalized["mode"],
            "modeLabel": {
                "upload": "已有课件素材",
                "topic": "课程主题生成",
                "code": "代码动画课件",
            }[normalized["mode"]],
            "sourceLanguage": normalized["sourceLanguage"],
            "targetLanguages": normalized["targetLanguages"],
            "languageSummary": "、".join(normalized["targetLanguages"]),
            "status": "queued",
            "currentStage": 1,
            "overallProgress": 0,
            "createdAt": now,
            "updatedAt": now,
            "inputs": normalized["inputs"],
            "assets": {"referenceAudio": None, "referenceImage": None},
            "isRecoveredArtifact": False,
        }
    )
    task["stages"] = [
        {
            **stage,
            "status": "queued" if stage["index"] == 1 else "waiting",
            "progress": 0,
        }
        for stage in STAGES
    ]
    task["outputs"] = {}
    return task


def retry_stage(task: dict[str, Any], stage_index: int) -> dict[str, Any]:
    if stage_index not in range(1, 6):
        raise ValueError("阶段编号必须为 1 至 5")
    for stage in task.get("stages", []):
        if stage["index"] < stage_index and (stage.get("status") != "completed" or stage["key"] not in task.get("outputs", {})):
            raise ValueError("前置阶段尚未完成，不能跳过执行")
    task["status"] = "processing"
    task.pop("error", None)
    task["currentStage"] = stage_index
    total = 0
    outputs = task.setdefault("outputs", {})
    outputs.pop('result', None)
    for stage in task.get("stages", []):
        if stage["index"] == stage_index:
            stage.update(status="running", progress=0)
        elif stage["index"] > stage_index:
            stage.update(status="waiting", progress=0)
        if stage["index"] >= stage_index:
            stage.pop("error", None)
            for field in (
                "startedAt",
                "startedAtEpoch",
                "completedAt",
                "elapsedSeconds",
                "etaSeconds",
                "queuedAtEpoch",
                "queueWaitSeconds",
                "detail",
            ):
                stage.pop(field, None)
            outputs.pop(stage["key"], None)
        total += int(stage.get("progress", 0))
    task["overallProgress"] = round(total / 5)
    task["updatedAt"] = utc_now()
    return task


def safe_artifact_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_") or "artifact"


def replace_task_assets(task, assets):
    previous = task.setdefault("assets", {})
    changed = [3 if key == "referenceAudio" else 4 for key, value in assets.items() if previous.get(key) != value]
    previous.update(copy.deepcopy(assets))
    if changed:
        first = min(changed)
        outputs = task.setdefault("outputs", {})
        if any("s"+str(index) in outputs for index in range(first, 6)):
            for index in range(first, 6):
                outputs.pop("s"+str(index), None)
            outputs.pop("result", None)
            for stage in task["stages"]:
                if stage["index"] >= first:
                    stage.update(status="waiting", progress=0)
                    for key in ["startedAt", "startedAtEpoch", "completedAt", "elapsedSeconds", "etaSeconds", "queuedAtEpoch", "queueWaitSeconds", "detail", "error"]:
                        stage.pop(key, None)
            task.update(status="needs_regeneration", currentStage=first)
            task.pop("error", None)
            task["overallProgress"] = sum(stage.get("progress", 0) for stage in task["stages"])/5
    task["updatedAt"] = utc_now()
    return task
