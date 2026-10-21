from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_DIRECTORY = "a800-local-0722"
LANGUAGE_OUTPUTS = {
    "en-US": {"name": "英语", "directory": "pipeline/output"},
    "ja-JP": {"name": "日语", "directory": "pipeline/output_ja"},
    "de-DE": {"name": "德语", "directory": "pipeline/output_de"},
}
TRANSLATION_CACHES = {
    "ko-KR": ("韩语", "pipeline/translation_cache*_Korean_*.json"),
    "fr-FR": ("法语", "pipeline/translation_cache*_French_*.json"),
    "ru-RU": ("俄语", "pipeline/translation_cache*_Russian_*.json"),
}


def json_read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path, source_root: Path) -> str:
    return str(path.relative_to(source_root))


def file_record(path: Path, source_root: Path) -> dict[str, Any]:
    return {
        "path": relative(path, source_root),
        "sizeBytes": path.stat().st_size,
    }


def first_file(directory: Path, pattern: str) -> Path | None:
    return next(iter(sorted(directory.rglob(pattern))), None)


def summarize_output(source_root: Path, code: str, spec: dict[str, str]) -> dict[str, Any]:
    directory = source_root / spec["directory"] / "ch01"
    record: dict[str, Any] = {
        "code": code,
        "name": spec["name"],
        "status": "missing",
        "directory": relative(directory, source_root),
        "files": {},
    }
    if not directory.is_dir():
        return record

    patterns = {
        "translatedStructure": "s2_translated_structure.json",
        "translatedPpt": "*.pptx",
        "timeline": "s3_timeline.json",
        "avatarManifest": "s4_manifest.json",
        "finalVideo": "*final.mp4",
    }
    for key, pattern in patterns.items():
        path = first_file(directory, pattern)
        if path:
            record["files"][key] = file_record(path, source_root)

    timeline_file = first_file(directory, "s3_timeline.json")
    if timeline_file:
        timeline = json_read(timeline_file)
        record["pageCount"] = int(timeline.get("total_pages", 0))
        record["segmentCount"] = len(timeline.get("segments", []))
        record["durationSeconds"] = round(float(timeline.get("total_duration_sec", 0)), 2)
    record["subtitleFileCount"] = len(list(directory.rglob("*.srt")))
    record["audioFileCount"] = len(list(directory.rglob("*.wav")))
    record["avatarVideoCount"] = len(
        [path for path in directory.rglob("*.mp4") if "s4_" in str(path)]
    )
    record["status"] = "completed" if "finalVideo" in record["files"] else "partial"
    return record


def make_preview(video: Path, destination: Path) -> bool:
    if destination.exists() and destination.stat().st_size > 0:
        return True
    if not shutil.which("ffmpeg"):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "00:00:08",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=960:-2",
            "-q:v",
            "3",
            str(destination),
        ],
        check=False,
    )
    return result.returncode == 0 and destination.exists()


def build_manifest(source_root: Path, data_root: Path, preview_root: Path | None) -> dict[str, Any]:
    if source_root.name != EXPECTED_DIRECTORY:
        raise ValueError(f"只允许读取 {EXPECTED_DIRECTORY}，当前路径为 {source_root}")
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)

    source_structure = (
        source_root
        / "index-tts/new-ch1/Overview_of_Artificial_Intelligence/page_texts.json"
    )
    source_data = json_read(source_structure)
    language_outputs = {
        code: summarize_output(source_root, code, spec)
        for code, spec in LANGUAGE_OUTPUTS.items()
    }

    language_outputs["zh-CN"] = {
        "code": "zh-CN",
        "name": "中文",
        "status": "supported",
        "note": "中文为系统支持语言；该恢复样例的原始讲稿为英语。",
        "files": {},
    }
    for code, (name, pattern) in TRANSLATION_CACHES.items():
        matches = sorted(source_root.glob(pattern))
        record = {
            "code": code,
            "name": name,
            "status": "translation-data-ready" if matches else "missing",
            "files": {},
        }
        if matches:
            cache = json_read(matches[0])
            record["translationEntryCount"] = len(cache)
            record["files"]["translationCache"] = file_record(matches[0], source_root)
        language_outputs[code] = record

    manifest: dict[str, Any] = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": {
            "sourceDirectory": str(source_root),
            "rule": "仅遍历 weights/a800-local-0722，未读取相邻目录",
        },
        "course": {
            "taskId": source_data.get("task_id"),
            "topic": source_data.get("course_topic"),
            "sourceLanguage": source_data.get("language"),
            "pageCount": source_data.get("total_pages", len(source_data.get("pages", []))),
            "sourceStructure": file_record(source_structure, source_root),
        },
        "languages": language_outputs,
        "pipeline": [
            "课件结构化",
            "多语种翻译与校验",
            "语音合成",
            "数字人生成",
            "视频合成",
        ],
    }

    if preview_root:
        previews: dict[str, str] = {}
        for code, output in language_outputs.items():
            video_record = output.get("files", {}).get("finalVideo")
            if not video_record:
                continue
            video = source_root / video_record["path"]
            destination = preview_root / f"preview-{code}.jpg"
            if make_preview(video, destination):
                previews[code] = str(destination)
        manifest["previews"] = previews

    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest["manifestSha256"] = hashlib.sha256(serialized).hexdigest()
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "recovered-artifacts.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="整理智课工坊恢复产物")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--preview-root", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(
        args.source_root.resolve(),
        args.data_root.resolve(),
        args.preview_root.resolve() if args.preview_root else None,
    )
    print(
        json.dumps(
            {
                "coursePages": manifest["course"]["pageCount"],
                "languages": {
                    code: value["status"] for code, value in manifest["languages"].items()
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
