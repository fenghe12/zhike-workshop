from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TIME_PATTERN = re.compile(r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2}),(?P<ms>\d{3})")


def to_milliseconds(value: str) -> int:
    match = TIME_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"无效的 SRT 时间：{value}")
    return (
        int(match["h"]) * 3_600_000
        + int(match["m"]) * 60_000
        + int(match["s"]) * 1_000
        + int(match["ms"])
    )


def from_milliseconds(value: int) -> str:
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_srt(path: Path, offset_ms: int) -> list[tuple[int, int, str]]:
    entries: list[tuple[int, int, str]] = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace").strip()):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            continue
        start, end = lines[1].split(" --> ", 1)
        text = "\n".join(lines[2:]).strip()
        if text:
            entries.append(
                (to_milliseconds(start) + offset_ms, to_milliseconds(end) + offset_ms, text)
            )
    return entries


def merge(timeline_path: Path, subtitle_directory: Path, output_path: Path) -> int:
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    offsets = {
        int(item["segment"]): round(float(item.get("seg_start", 0)) * 1_000)
        for item in timeline.get("segments", [])
    }
    entries: list[tuple[int, int, str]] = []
    for path in sorted(subtitle_directory.glob("segment_*.srt")):
        match = re.search(r"segment_(\d+)", path.stem)
        if not match:
            continue
        segment = int(match.group(1))
        entries.extend(parse_srt(path, offsets.get(segment, 0)))
    entries.sort(key=lambda item: (item[0], item[1]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = []
    for index, (start, end, text) in enumerate(entries, start=1):
        content.append(
            f"{index}\n{from_milliseconds(start)} --> {from_milliseconds(end)}\n{text}\n"
        )
    output_path.write_text("\n".join(content), encoding="utf-8")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="合并分段 SRT 并换算为课程绝对时间")
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--subtitle-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = merge(args.timeline, args.subtitle_directory, args.output)
    print(json.dumps({"subtitleCount": count, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
