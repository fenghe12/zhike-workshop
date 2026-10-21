from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any


class CodeVideoComposeAgent:
    """Compose Manim scene videos, FLOAT avatars, speech and subtitles."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"

    @staticmethod
    def _duration(path: Path) -> float:
        value = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        )
        return float(value.strip())

    @staticmethod
    def _video_encoder(ffmpeg: str) -> str:
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if "libx264" in result.stdout:
                return "libx264"
        except Exception:
            pass
        return "mpeg4"

    def _compose_scene(
        self,
        background: Path,
        avatar: Path,
        audio: Path,
        duration: float,
        output: Path,
    ) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        encoder = self._video_encoder(self.ffmpeg)
        filter_complex = (
            "[0:v]scale=1500:844:force_original_aspect_ratio=decrease,"
            "pad=1500:844:(ow-iw)/2:(oh-ih)/2:color=#071722,"
            "pad=1920:1080:40:36:color=#071722,setsar=1,"
            "drawbox=x=1520:y=36:w=360:h=850:color=#0D2530@0.92:t=fill[stage];"
            "[1:v]scale=320:320:force_original_aspect_ratio=decrease,"
            "pad=320:320:(ow-iw)/2:(oh-ih)/2:color=#0D2530,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=#24C7A3@0.85:t=4[avatar];"
            "[stage][avatar]overlay=1540:548:shortest=0[with_avatar];"
            "[with_avatar]drawbox=x=40:y=916:w=1840:h=132:"
            "color=#0D2530@0.97:t=fill,"
            "drawbox=x=40:y=916:w=1840:h=132:color=#24C7A3@0.58:t=2[v]"
        )
        command = [
            self.ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(background),
            "-stream_loop",
            "-1",
            "-i",
            str(avatar),
            "-i",
            str(audio),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "2:a:0",
            "-t",
            f"{duration:.3f}",
            "-r",
            "30",
            "-c:v",
            encoder,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output),
        ]
        if encoder == "libx264":
            position = command.index("-pix_fmt")
            command[position:position] = ["-preset", "medium", "-crf", "20"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            raise RuntimeError(f"代码动画场景合成失败：{result.stderr[-3000:]}")

    def _concat(self, videos: list[Path], output: Path) -> None:
        concat_path = output.with_suffix(".concat.txt")
        concat_path.write_text(
            "".join(f"file '{path}'\n" for path in videos),
            encoding="utf-8",
        )
        encoder = self._video_encoder(self.ffmpeg)
        command = [
            self.ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c:v",
            encoder,
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        if encoder == "libx264":
            position = command.index("-c:a")
            command[position:position] = ["-preset", "medium", "-crf", "20"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                raise RuntimeError(f"代码动画视频连接失败：{result.stderr[-3000:]}")
        finally:
            concat_path.unlink(missing_ok=True)

    @staticmethod
    def _display_width(value: str) -> int:
        return sum(
            2 if unicodedata.east_asian_width(char) in {"W", "F", "A"} else 1
            for char in value
        )

    @classmethod
    def _wrap_subtitle_text(cls, value: str, max_width: int = 56) -> str:
        text = re.sub(r"\s+", " ", value).strip()
        total_width = cls._display_width(text)
        if total_width <= max_width:
            return text
        if total_width <= max_width * 2:
            candidates: list[tuple[int, int]] = []
            for index, char in enumerate(text[:-1], start=1):
                if char not in "，。；：！？、,.!?;: ":
                    continue
                left = text[:index].strip()
                right = text[index:].strip()
                left_width = cls._display_width(left)
                right_width = cls._display_width(right)
                if left_width <= max_width and right_width <= max_width:
                    candidates.append((abs(left_width - right_width), index))
            if candidates:
                _, split_at = min(candidates)
                return text[:split_at].strip() + "\n" + text[split_at:].strip()
        punctuation = set("，。；：！？、,.!?;: ")
        lines: list[str] = []
        current: list[str] = []
        current_width = 0
        for char in text:
            width = cls._display_width(char)
            if current and current_width + width > max_width:
                lines.append("".join(current).strip())
                current = []
                current_width = 0
            current.append(char)
            current_width += width
            if char in punctuation and current_width >= int(max_width * 0.72):
                lines.append("".join(current).strip())
                current = []
                current_width = 0
        if current:
            lines.append("".join(current).strip())
        return "\n".join(line for line in lines if line)

    @classmethod
    def _write_wrapped_srt(cls, source: Path, destination: Path) -> None:
        blocks = re.split(r"\n\s*\n", source.read_text(encoding="utf-8-sig").strip())
        normalized: list[str] = []
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) < 3:
                continue
            subtitle_text = cls._wrap_subtitle_text(" ".join(lines[2:]))
            normalized.append("\n".join([lines[0], lines[1], subtitle_text]))
        destination.write_text("\n\n".join(normalized) + "\n", encoding="utf-8")

    def _subtitles(self, video: Path, srt: Path, output: Path) -> None:
        fonts_dir = os.environ.get(
            "SMARTCOURSE_SUBTITLE_FONTS",
            "/usr/share/fonts/opentype/noto",
        )
        wrapped_srt = output.parent / "subtitles_layout.srt"
        self._write_wrapped_srt(srt, wrapped_srt)
        escaped_srt = str(wrapped_srt).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        escaped_fonts = fonts_dir.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        style = (
            "FontName=Noto Sans CJK SC,FontSize=12,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00121A20,BackColour=&H000D2530,BorderStyle=1,"
            "Outline=1.0,Shadow=0,MarginL=24,MarginR=24,MarginV=8,"
            "Alignment=2,WrapStyle=0"
        )
        filter_value = (
            f"subtitles=filename='{escaped_srt}':fontsdir='{escaped_fonts}':"
            f"force_style='{style}'"
        )
        command = [
            self.ffmpeg,
            "-y",
            "-i",
            str(video),
            "-vf",
            filter_value,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(f"代码动画字幕合成失败：{result.stderr[-3000:]}")

    def replace_course_layer(
        self,
        task_id: str,
        scene_videos: list[str],
        base_video: str,
    ) -> dict[str, Any]:
        """Replace only the course region while retaining avatar, audio and subtitle regions."""
        output_dir = self.workspace_root / task_id / "s5_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        course_track = output_dir / "course_track.mp4"
        self._concat([Path(path) for path in scene_videos], course_track)
        base_path = Path(base_video).resolve()
        output_path = output_dir / "final_video.mp4"
        duration = self._duration(base_path)
        encoder = self._video_encoder(self.ffmpeg)
        filter_complex = (
            "[0:v]scale=1500:844:force_original_aspect_ratio=decrease,"
            "pad=1500:844:(ow-iw)/2:(oh-ih)/2:color=#071722,"
            "setsar=1,tpad=stop_mode=clone:stop_duration=1[course];"
            "[1:v][course]overlay=40:36:shortest=0[v]"
        )
        command = [
            self.ffmpeg,
            "-y",
            "-i",
            str(course_track),
            "-i",
            str(base_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.3f}",
            "-r",
            "30",
            "-c:v",
            encoder,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        if encoder == "libx264":
            position = command.index("-pix_fmt")
            command[position:position] = ["-preset", "medium", "-crf", "20"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(f"课程画面替换失败：{result.stderr[-3000:]}")
        manifest_data = {
            "taskId": task_id,
            "outputPath": str(output_path),
            "durationSeconds": round(self._duration(output_path), 3),
            "sceneCount": len(scene_videos),
            "resolution": "1920x1080",
            "frameRate": 30,
            "focusColorMode": "dynamic_contrast_and_color_distance",
            "layout": {
                "courseArea": "1500x844@40,36",
                "courseHeader": "subject_title_page_number",
                "courseContentSafeArea": "bounded_between_header_and_footer",
                "courseFooter": "course_progress_percentage_and_bar",
                "avatarArea": "retained_from_base_video",
                "subtitleSafeArea": "retained_from_base_video",
            },
            "fileSizeBytes": output_path.stat().st_size,
        }
        manifest = output_dir / "compose_manifest.json"
        manifest.write_text(
            json.dumps(manifest_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manifest_data["manifest"] = str(manifest)
        return manifest_data

    def run(
        self,
        task_id: str,
        scene_videos: list[str],
        timeline_json: str,
        avatars_dir: str,
        subtitle_srt: str,
    ) -> dict[str, Any]:
        timeline = json.loads(Path(timeline_json).read_text(encoding="utf-8"))
        pages = timeline.get("pages", [])
        if len(scene_videos) != len(pages):
            raise ValueError(
                f"动画场景数量与语音页面数量不一致：{len(scene_videos)} / {len(pages)}"
            )
        output_dir = self.workspace_root / task_id / "s5_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        segments: list[Path] = []
        avatars_root = Path(avatars_dir)
        for scene_path, page in zip(scene_videos, pages):
            page_id = int(page["page_id"])
            avatar = avatars_root / f"page_{page_id:03d}.mp4"
            audio = Path(page["wav_path"])
            if not avatar.is_file():
                raise FileNotFoundError(f"缺少数字人片段：{avatar}")
            if not audio.is_file():
                raise FileNotFoundError(f"缺少语音片段：{audio}")
            destination = output_dir / f"segment_{page_id:03d}.mp4"
            self._compose_scene(
                Path(scene_path),
                avatar,
                audio,
                float(page["duration"]),
                destination,
            )
            segments.append(destination)

        silent_subtitle_video = output_dir / "final_without_subtitles.mp4"
        self._concat(segments, silent_subtitle_video)
        final_path = output_dir / "final_video.mp4"
        self._subtitles(silent_subtitle_video, Path(subtitle_srt), final_path)
        result = {
            "taskId": task_id,
            "outputPath": str(final_path),
            "durationSeconds": round(self._duration(final_path), 3),
            "sceneCount": len(segments),
            "avatarSceneCount": len(segments),
            "resolution": "1920x1080",
            "frameRate": 30,
            "subtitles": str(Path(subtitle_srt).resolve()),
            "layout": {
                "courseArea": "1500x844@40,36",
                "avatarArea": "320x320@1540,548",
                "subtitleSafeArea": "1840x132@40,916",
                "subtitleWrapDisplayWidth": 56,
            },
            "fileSizeBytes": final_path.stat().st_size,
        }
        manifest = output_dir / "compose_manifest.json"
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["manifest"] = str(manifest)
        return result
