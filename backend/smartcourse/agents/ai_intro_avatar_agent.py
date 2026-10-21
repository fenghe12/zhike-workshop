from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

try:
    from .s4_longcat_avatar_agent import LongCatAvatarAgent
except ImportError:
    from s4_longcat_avatar_agent import LongCatAvatarAgent


class AIIntroAvatarAgent:
    """Build and collect six main-course and four interruption LongCat jobs."""

    def __init__(self, longcat: LongCatAvatarAgent):
        self.longcat = longcat

    @staticmethod
    def _duration(path: Path) -> float:
        value = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            text=True,
        )
        return float(value.strip())

    def _job(
        self,
        job_id: str,
        title: str,
        action: str,
        audio: Path,
        reference_image: Path,
        output: Path,
        maximum_duration_seconds: float | None = 3.6,
    ) -> dict[str, Any]:
        source_duration = self._duration(audio)
        duration = (
            source_duration
            if maximum_duration_seconds is None
            else min(maximum_duration_seconds, source_duration)
        )
        output.mkdir(parents=True, exist_ok=True)
        action_audio = output / "action.wav"
        command = ["ffmpeg", "-y", "-i", str(audio)]
        if maximum_duration_seconds is not None:
            command.extend(["-t", f"{duration:.3f}"])
        command.extend(["-ar", "44100", "-ac", "1", str(action_audio)])
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        segments = max(1, math.ceil(max(0.0, duration * 25 - 13) / 80))
        input_json = output / "input.json"
        input_json.write_text(
            json.dumps(
                {
                    "prompt": self.longcat._prompt(title, [action]),
                    "cond_image": str(reference_image.resolve()),
                    "cond_audio": {"person1": str(action_audio.resolve())},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        command = [
            str(self.longcat.python), "-m", "torch.distributed.run",
            f"--nproc_per_node={len(self.longcat.gpu_ids)}",
            str(self.longcat.longcat_root / "run_demo_avatar_single_audio_to_video.py"),
            f"--context_parallel_size={len(self.longcat.gpu_ids)}",
            f"--checkpoint_dir={self.longcat.checkpoint_dir}", "--stage_1=ai2v",
            f"--input_json={input_json}", f"--output_dir={output}", f"--num_segments={segments}",
            "--resolution=480p", "--ref_img_index=10", "--mask_frame_range=3",
            "--use_distill", "--model_type=avatar-v1.5", "--use_int8",
        ]
        return {
            "jobId": job_id,
            "title": title,
            "action": action,
            "sourceAudio": str(audio.resolve()),
            "audio": str(action_audio.resolve()),
            "sourceDurationSeconds": round(source_duration, 3),
            "durationSeconds": round(duration, 3),
            "numSegments": segments,
            "inputJson": str(input_json),
            "outputDirectory": str(output),
            "command": command,
        }

    def build_full_jobs(
        self,
        outline_path: str | Path,
        tts_timeline_path: str | Path,
        reference_image: str | Path,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        outline = json.loads(Path(outline_path).read_text(encoding="utf-8"))
        timeline = json.loads(Path(tts_timeline_path).read_text(encoding="utf-8"))
        gesture_schedule = json.loads(Path(timeline["gestureSchedule"]).read_text(encoding="utf-8"))
        gestures = {int(item["sceneId"]): item for item in gesture_schedule["schedule"]}
        output = Path(output_dir).resolve()
        reference = Path(reference_image)
        main = []
        for scene in timeline.get("scenes", []):
            scene_id = int(scene["sceneId"])
            gesture = gestures[scene_id]
            item = self._job(
                f"main_scene_{scene_id:02d}",
                str(scene.get("title", f"场景{scene_id}")),
                str(gesture["gesture"]),
                Path(scene["audio"]),
                reference,
                output / "main" / f"scene_{scene_id:02d}",
                maximum_duration_seconds=None,
            )
            item["sceneId"] = scene_id
            item["triggerSentence"] = gesture["triggerSentence"]
            main.append(item)

        branch_outline = {
            str(item.get("interrupt_id")): item for item in outline.get("interruptions", [])
        }
        interruptions = []
        for index, branch in enumerate(timeline.get("interruptions", []), start=1):
            interrupt_id = str(branch["interruptId"])
            definition = branch_outline[interrupt_id]
            item = self._job(
                f"interrupt_{index:02d}",
                str(definition["branch_title"]),
                str(definition["branch_action"]),
                Path(branch["audio"]),
                reference,
                output / "branches" / f"interrupt_{index:02d}",
                maximum_duration_seconds=None,
            )
            item["interruptId"] = interrupt_id
            item["afterScene"] = branch["afterScene"]
            item["studentState"] = branch["studentState"]
            interruptions.append(item)

        manifest = {
            "engine": "longcat-video-avatar-1.5",
            "teacherAlways": True,
            "readiness": self.longcat.readiness(),
            "supportedActions": gesture_schedule["supportedActions"],
            "gestureSchedule": gesture_schedule,
            "main": main,
            "interruptions": interruptions,
            "totalJobs": len(main) + len(interruptions),
        }
        manifest_path = output / "jobs.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest"] = str(manifest_path)
        return manifest

    def build_jobs(
        self,
        outline_path: str | Path,
        tts_timeline_path: str | Path,
        reference_image: str | Path,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        outline = json.loads(Path(outline_path).read_text(encoding="utf-8"))
        timeline = json.loads(Path(tts_timeline_path).read_text(encoding="utf-8"))
        gesture_schedule = json.loads(Path(timeline["gestureSchedule"]).read_text(encoding="utf-8"))
        gestures = {int(item["sceneId"]): item for item in gesture_schedule["schedule"]}
        output = Path(output_dir).resolve()
        reference = Path(reference_image)
        main = []
        for scene in timeline.get("scenes", []):
            scene_id = int(scene["sceneId"])
            gesture = gestures[scene_id]
            main.append(
                self._job(
                    f"main_scene_{scene_id:02d}",
                    str(scene.get("title", f"场景{scene_id}")),
                    str(gesture["gesture"]),
                    Path(scene["actionAudio"]),
                    reference,
                    output / "main" / f"scene_{scene_id:02d}",
                )
            )
            main[-1]["sceneId"] = scene_id
            main[-1]["triggerSentence"] = gesture["triggerSentence"]
        branch_outline = {str(item.get("interrupt_id")): item for item in outline.get("interruptions", [])}
        interruptions = []
        for index, branch in enumerate(timeline.get("interruptions", []), start=1):
            interrupt_id = str(branch["interruptId"])
            definition = branch_outline[interrupt_id]
            interruptions.append(
                self._job(
                    f"interrupt_{index:02d}",
                    str(definition["branch_title"]),
                    str(definition["branch_action"]),
                    Path(branch["actionAudio"]),
                    reference,
                    output / "branches" / f"interrupt_{index:02d}",
                )
            )
            interruptions[-1]["interruptId"] = interrupt_id
            interruptions[-1]["afterScene"] = branch["afterScene"]
            interruptions[-1]["studentState"] = branch["studentState"]
        manifest = {
            "engine": "longcat-video-avatar-1.5",
            "readiness": self.longcat.readiness(),
            "supportedActions": gesture_schedule["supportedActions"],
            "gestureSchedule": gesture_schedule,
            "main": main,
            "interruptions": interruptions,
            "totalJobs": len(main) + len(interruptions),
        }
        manifest_path = output / "jobs.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest"] = str(manifest_path)
        return manifest

    def collect(self, jobs_path: str | Path, output_path: str | Path) -> dict[str, Any]:
        jobs = json.loads(Path(jobs_path).read_text(encoding="utf-8"))
        result = {"engine": jobs["engine"], "teacherAlways": bool(jobs.get("teacherAlways")), "supportedActions": jobs["supportedActions"], "gestureSchedule": jobs.get("gestureSchedule", {}), "main": [], "interruptions": []}
        for group in ("main", "interruptions"):
            for job in jobs[group]:
                videos = sorted(Path(job["outputDirectory"]).glob("*.mp4"), key=lambda value: value.stat().st_mtime)
                if not videos:
                    raise FileNotFoundError(f"LongCat任务没有输出：{job['jobId']}")
                item = {key: job[key] for key in job if key not in {"command"}}
                item["video"] = str(videos[-1].resolve())
                item["resultDurationSeconds"] = round(self._duration(videos[-1]), 3)
                result[group].append(item)
        result["passed"] = len(result["main"]) == 6 and len(result["interruptions"]) == 4
        destination = Path(output_path)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["manifest"] = str(destination.resolve())
        return result
