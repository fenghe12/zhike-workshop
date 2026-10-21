"""Assemble approved microcourse units from completed per-page course media."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pymupdf


def _page_number(value):
    match = re.fullmatch(r"(?:src_)?page_(\d+)|(\d+)", str(value))
    if not match:
        raise ValueError("单元页面编号无效")
    return int(match.group(1) or match.group(2))


def _time_ms(value):
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def _srt_time(milliseconds):
    hours, remainder = divmod(int(milliseconds), 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _read_srt(path):
    entries = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = (item.strip() for item in lines[1].split("-->", 1))
        entries.append((_time_ms(start), _time_ms(end), "\n".join(lines[2:])))
    return entries


def _write_unit_srt(entries, timeline_pages, numbers, destination):
    page_lookup = {int(page["page_id"]): page for page in timeline_pages}
    output = []
    offset = 0
    for number in numbers:
        page = page_lookup[number]
        start = round(float(page["start_time"]) * 1000)
        end = round(float(page["end_time"]) * 1000)
        for first, last, text in entries:
            if first >= start - 50 and last <= end + 50:
                shifted_first = max(0, offset + first - start)
                shifted_last = max(shifted_first + 1, offset + last - start)
                output.append(f"{len(output)+1}\n{_srt_time(shifted_first)} --> {_srt_time(shifted_last)}\n{text}")
        offset += end - start
    destination.write_text("\n\n".join(output) + "\n", encoding="utf-8")
    return len(output)


def _video_duration(path):
    output = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        timeout=30,
    )
    return float(output.strip())


def assemble_units(settings, blueprint):
    if blueprint.get("status") != "APPROVED":
        raise ValueError("仅已批准的教学蓝图可以生成微课单元")
    course_id = blueprint["course_id"]
    locale = blueprint["target_locale"]
    artifact_root = Path(settings.artifact_root)
    task_root = artifact_root / "tasks" / course_id
    delivery = task_root / "delivery" / locale
    state = json.loads((Path(settings.data_root) / "state.json").read_text(encoding="utf-8"))
    task = state["tasks"].get(course_id)
    if not task or task.get("status") != "completed":
        raise ValueError("课程尚未完成全部媒体生成")
    source_pdf = delivery / "course.pdf"
    source_deck = delivery / "course.pptx"
    if not source_pdf.is_file() or not source_deck.is_file():
        raise ValueError("课程课件交付文件缺失")
    timeline = json.loads((delivery / "timeline.json").read_text(encoding="utf-8"))
    timeline_pages = timeline["pages"]
    valid_pages = {int(page["page_id"]) for page in timeline_pages}
    captions = _read_srt(delivery / "subtitles.srt")
    output_root = task_root / "teacher-blueprints" / blueprint["blueprint_id"] / locale
    output_root.mkdir(parents=True, exist_ok=True)
    units = []
    with pymupdf.open(source_pdf) as original_pdf:
        for unit in blueprint["units"]:
            unit_id = str(unit["unit_id"])
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", unit_id):
                raise ValueError("单元 ID 格式无效")
            numbers = [_page_number(value) for value in unit["page_ids"]]
            if not numbers or any(number not in valid_pages for number in numbers):
                raise ValueError("单元引用了不存在的课程页面")
            directory = output_root / unit_id
            directory.mkdir(parents=True, exist_ok=True)
            videos = [delivery / "pages" / f"page-{number:03d}.mp4" for number in numbers]
            if any(not video.is_file() for video in videos):
                raise ValueError(f"{unit_id} 缺少逐页视频")
            source_record = [
                {"name": path.name, "size": path.stat().st_size, "modifiedNs": path.stat().st_mtime_ns}
                for path in videos
            ]
            manifest_path = directory / "unit.json"
            request = {"blueprintRevision": blueprint["revision"], "pageIds": numbers, "sourceVideos": source_record}
            if manifest_path.is_file():
                saved = json.loads(manifest_path.read_text(encoding="utf-8"))
                if saved.get("request") == request and all((directory / name).is_file() for name in ("unit.mp4", "unit.pdf", "subtitles.srt")):
                    units.append(saved)
                    continue
            video_path = directory / "unit.mp4"
            pending_video = directory / ".unit.pending.mp4"
            if len(videos) == 1:
                shutil.copy2(videos[0], pending_video)
            else:
                concat_list = directory / "pages.concat.txt"
                concat_list.write_text("".join(f"file '{video.resolve()}'\n" for video in videos), encoding="utf-8")
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                     "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-movflags", "+faststart", str(pending_video)],
                    check=True, capture_output=True, timeout=7200,
                )
            expected_seconds = sum(float(next(page["duration"] for page in timeline_pages if int(page["page_id"]) == number)) for number in numbers)
            actual_seconds = _video_duration(pending_video)
            if abs(actual_seconds - expected_seconds) > max(1.0, len(numbers) * 0.2):
                raise ValueError(f"{unit_id} 的视频时长与页面时间轴不一致")
            pending_video.replace(video_path)
            pdf_path = directory / "unit.pdf"
            pending_pdf = directory / ".unit.pending.pdf"
            selected = pymupdf.open()
            for number in numbers:
                selected.insert_pdf(original_pdf, from_page=number - 1, to_page=number - 1)
            selected.save(pending_pdf)
            selected.close()
            pending_pdf.replace(pdf_path)
            subtitle_path = directory / "subtitles.srt"
            subtitle_count = _write_unit_srt(captions, timeline_pages, numbers, subtitle_path)
            manifest = {
                "unitId": unit_id,
                "title": unit.get("title", unit_id),
                "objectiveIds": unit.get("objective_ids", []),
                "pageIds": numbers,
                "locale": locale,
                "durationSeconds": actual_seconds,
                "subtitleCount": subtitle_count,
                "video": str(video_path),
                "pdf": str(pdf_path),
                "subtitles": str(subtitle_path),
                "sourceEditablePptx": str(source_deck),
                "request": request,
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            units.append(manifest)
    return {"blueprintId": blueprint["blueprint_id"], "courseId": course_id, "locale": locale, "units": units}
