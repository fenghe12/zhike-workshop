from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


class LongCatAvatarAgent:
    """Generate full-body teacher segments with official LongCat-Video-Avatar 1.5."""

    def __init__(
        self,
        longcat_root: str,
        environment_python: str,
        checkpoint_dir: str,
        gpu_ids: tuple[int, ...] = (0, 1),
    ):
        self.longcat_root = Path(longcat_root).resolve()
        self.python = Path(environment_python).expanduser().absolute()
        self.checkpoint_dir = Path(checkpoint_dir).resolve()
        self.gpu_ids = gpu_ids

    def readiness(self) -> dict[str, Any]:
        base_dir = self.checkpoint_dir.parent / "LongCat-Video"
        checks = {
            "python": self.python.is_file(),
            "entrypoint": (self.longcat_root / "run_demo_avatar_single_audio_to_video.py").is_file(),
            "avatarConfig": (self.checkpoint_dir / "base_model_int8" / "config.json").is_file(),
            "avatarWeights": any((self.checkpoint_dir / "base_model_int8").glob("*.safetensors")),
            "distillLora": (self.checkpoint_dir / "lora" / "dmd_lora.safetensors").is_file(),
            "whisper": (self.checkpoint_dir / "whisper-large-v3").is_dir(),
            "vocalSeparator": (self.checkpoint_dir / "vocal_separator" / "Kim_Vocal_2.onnx").is_file(),
            "tokenizer": (base_dir / "tokenizer").is_dir(),
            "textEncoder": (base_dir / "text_encoder").is_dir(),
            "vae": (base_dir / "vae").is_dir(),
        }
        return {
            "engine": "longcat-video-avatar-1.5",
            "ready": all(checks.values()),
            "checks": checks,
            "gpuIds": list(self.gpu_ids),
            "mode": "int8_distilled_480p",
        }

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
    def _prompt(title: str, gestures: list[str]) -> str:
        aliases = {
            "neutral": "Action_Explain", "neutral_explain": "Action_Explain",
            "single_hand_out": "Action_Point_Right", "right_hand_point": "Action_Point_Right",
            "left_hand_point": "Action_Point_Left", "two_hands_out": "Action_Explain",
            "both_hands_open": "Action_Explain", "right_hand_count": "Action_Explain",
            "both_hands_compare": "Action_Summarize",
        }
        normalized = {aliases.get(value, value) for value in gestures}
        action_prompts = {
            "Action_Greet": "raises the right arm and gives one clear natural wave as a greeting while the left hand remains relaxed, then returns to a neutral standing pose",
            "Action_Explain": "opens both hands naturally at waist to chest level with visible palms while explaining, holds the open explanatory pose briefly, then returns both hands",
            "Action_Point_Left": "keeps the right hand relaxed, clearly extends the left arm and points toward the courseware on the left side, holds briefly, then returns the left hand",
            "Action_Point_Right": "keeps the left hand relaxed, clearly extends the right arm and points toward the courseware on the right side, holds briefly, then returns the right hand",
            "Action_Think": "brings one hand gently near the chin and draws the other hand slightly inward, holds a reflective thinking pose, then returns to a neutral stance",
            "Action_Summarize": "moves both hands inward and brings them together at the center to emphasize a summary, holds briefly, then returns both hands",
        }
        action_text = ", and ".join(action_prompts[value] for value in normalized if value in action_prompts)
        if not action_text:
            action_text = action_prompts["Action_Explain"]
        return (
            "A professional university instructor stands in a clean modern classroom, framed from head to knees. "
            f"The instructor is speaking clearly about {title}, maintains a stable identity and natural posture, "
            f"{action_text}. Subtle facial expressions, realistic hands, fixed camera, no subtitles, no on-screen text."
        )

    def build_commands(
        self,
        task_id: str,
        timeline_json: str,
        reference_image: str,
        gesture_schedule: dict[str, Any],
        course_structure: dict[str, Any],
        output_root: str,
    ) -> list[dict[str, Any]]:
        timeline = json.loads(Path(timeline_json).read_text(encoding="utf-8"))
        pages = {int(page.get("page_id", index)): page for index, page in enumerate(course_structure.get("pages", []), 1)}
        gestures_by_page: dict[int, list[str]] = {}
        for item in gesture_schedule.get("schedule", []):
            event_id = str(item.get("eventId", ""))
            try:
                page_id = int(event_id.split("_")[0].removeprefix("s"))
            except (ValueError, IndexError):
                continue
            gestures_by_page.setdefault(page_id, []).append(str(item.get("gesture", "neutral")))
        output = Path(output_root).resolve()
        commands = []
        for page in timeline.get("pages", []):
            page_id = int(page["page_id"])
            audio = Path(str(page.get("wav_path", ""))).resolve()
            duration = float(page.get("duration", 0) or (self._duration(audio) if audio.is_file() else 0))
            segments = max(1, math.ceil(max(0.0, duration * 25 - 13) / 80))
            page_dir = output / f"page_{page_id:03d}"
            input_json = page_dir / "input.json"
            page_dir.mkdir(parents=True, exist_ok=True)
            title = str(pages.get(page_id, {}).get("title", f"Page {page_id}"))
            payload = {
                "prompt": self._prompt(title, gestures_by_page.get(page_id, [])),
                "cond_image": str(Path(reference_image).resolve()),
                "cond_audio": {"person1": str(audio)},
            }
            input_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            command = [
                str(self.python),
                "-m",
                "torch.distributed.run",
                f"--nproc_per_node={len(self.gpu_ids)}",
                str(self.longcat_root / "run_demo_avatar_single_audio_to_video.py"),
                f"--context_parallel_size={len(self.gpu_ids)}",
                f"--checkpoint_dir={self.checkpoint_dir}",
                "--stage_1=ai2v",
                f"--input_json={input_json}",
                f"--output_dir={page_dir}",
                f"--num_segments={segments}",
                "--resolution=480p",
                "--ref_img_index=10",
                "--mask_frame_range=3",
                "--use_distill",
                "--model_type=avatar-v1.5",
                "--use_int8",
            ]
            commands.append(
                {
                    "pageId": page_id,
                    "durationSeconds": duration,
                    "numSegments": segments,
                    "inputJson": str(input_json),
                    "outputDirectory": str(page_dir),
                    "command": command,
                }
            )
        return commands

    def run(
        self,
        task_id: str,
        timeline_json: str,
        reference_image: str,
        gesture_schedule: dict[str, Any],
        course_structure: dict[str, Any],
        output_root: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        readiness = self.readiness()
        commands = self.build_commands(
            task_id,
            timeline_json,
            reference_image,
            gesture_schedule,
            course_structure,
            output_root,
        )
        if dry_run:
            return {"taskId": task_id, "readiness": readiness, "dryRun": True, "pages": commands}
        if not readiness["ready"]:
            raise RuntimeError(f"LongCat-Video-Avatar 1.5 环境未就绪：{readiness['checks']}")
        avatar_root = Path(output_root).resolve() / "avatars"
        avatar_root.mkdir(parents=True, exist_ok=True)
        environment = dict(os.environ)
        environment["CUDA_VISIBLE_DEVICES"] = ",".join(str(value) for value in self.gpu_ids)
        environment["_CHECK_PEFT"] = "0"
        environment["LONGCAT_AUDIO_TEMP_DIR"] = str(Path(output_root).resolve() / "audio_temp")
        results = []
        for item in commands:
            started = time.perf_counter()
            process = subprocess.run(
                item["command"],
                cwd=self.longcat_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=7200,
            )
            page_dir = Path(item["outputDirectory"])
            (page_dir / "stdout.log").write_text(process.stdout, encoding="utf-8")
            (page_dir / "stderr.log").write_text(process.stderr, encoding="utf-8")
            if process.returncode != 0:
                raise RuntimeError(f"LongCat 页面 {item['pageId']} 生成失败：{process.stderr[-2000:]}")
            videos = sorted(page_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime)
            if not videos:
                raise FileNotFoundError(f"LongCat 页面 {item['pageId']} 未生成 MP4")
            destination = avatar_root / f"page_{item['pageId']:03d}.mp4"
            shutil.copy2(videos[-1], destination)
            results.append(
                {
                    "pageId": item["pageId"],
                    "video": str(destination),
                    "elapsedSeconds": round(time.perf_counter() - started, 3),
                    "durationSeconds": self._duration(destination),
                }
            )
        return {
            "taskId": task_id,
            "engine": "longcat-video-avatar-1.5",
            "readiness": readiness,
            "avatarsDir": str(avatar_root),
            "totalPages": len(results),
            "successPages": len(results),
            "pages": results,
        }
