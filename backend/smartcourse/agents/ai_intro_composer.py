from __future__ import annotations

from io import BytesIO
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter


class AIIntroComposer:
    """Compose Manim, IndexTTS2 subtitles and LongCat full-body actions."""

    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe"):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def _probe(self, path: Path) -> dict[str, Any]:
        value = json.loads(
            subprocess.check_output(
                [
                    self.ffprobe, "-v", "error", "-show_entries",
                    "stream=width,height,r_frame_rate,codec_type:format=duration,size", "-of", "json", str(path),
                ],
                text=True,
            )
        )
        video = next((item for item in value.get("streams", []) if item.get("codec_type") == "video"), {})
        audio = next((item for item in value.get("streams", []) if item.get("codec_type") == "audio"), {})
        return {
            "path": str(path.resolve()),
            "width": int(video.get("width", 0)),
            "height": int(video.get("height", 0)),
            "frameRate": video.get("r_frame_rate"),
            "hasAudio": bool(audio),
            "durationSeconds": round(float(value.get("format", {}).get("duration", 0)), 3),
            "sizeBytes": int(value.get("format", {}).get("size", 0)),
        }

    def _video_frame(self, path: Path, second: float) -> Image.Image:
        value = subprocess.check_output(
            [
                self.ffmpeg, "-v", "error", "-ss", f"{max(0.0, second):.3f}",
                "-i", str(path), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-",
            ]
        )
        return Image.open(BytesIO(value)).convert("RGB")

    @staticmethod
    def _person_mask(frame: Image.Image, width: int, height: int) -> np.ndarray:
        value = np.asarray(frame, dtype=np.int16)
        minimum = value.min(axis=2)
        channel_range = value.max(axis=2) - minimum
        foreground = ~((minimum >= 125) & (channel_range <= 24))
        mask = Image.fromarray((foreground.astype(np.uint8) * 255), mode="L")
        mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(7))
        mask = mask.resize((width, height), Image.Resampling.LANCZOS)
        return np.asarray(mask) >= 72

    @staticmethod
    def _content_mask(frame: Image.Image) -> np.ndarray:
        resized = frame.resize((1920, 1080), Image.Resampling.LANCZOS)
        value = np.asarray(resized, dtype=np.int16)
        background = np.array([7, 23, 34], dtype=np.int16)
        occupied = np.max(np.abs(value - background), axis=2) >= 20
        mask = Image.fromarray((occupied.astype(np.uint8) * 255), mode="L")
        mask = mask.filter(ImageFilter.MaxFilter(13))
        return np.asarray(mask) >= 72

    def _choose_teacher_layout(self, manim: Path, avatar: Path, action: str = "") -> dict[str, Any]:
        manim_info = self._probe(manim)
        avatar_info = self._probe(avatar)
        duration = max(0.1, float(manim_info["durationSeconds"]))
        sample_count = max(6, int(np.ceil(duration / 2.4)))
        sample_seconds = np.linspace(min(0.8, duration * 0.08), max(0.9, duration - 0.8), sample_count).tolist()
        content_masks = [self._content_mask(self._video_frame(manim, second)) for second in sample_seconds]
        avatar_frame = self._video_frame(avatar, min(1.2, max(0.0, float(avatar_info["durationSeconds"]) * 0.08)))

        avatar_width = max(1, int(avatar_info["width"]))
        avatar_height = max(1, int(avatar_info["height"]))
        preferred_side = "right" if "Point_Left" in action else "left" if "Point_Right" in action else ""
        candidates: list[dict[str, Any]] = []
        for height in (520, 480, 440, 400, 360, 320):
            width = max(2, round(avatar_width * height / avatar_height / 2) * 2)
            person_mask = self._person_mask(avatar_frame, width, height)
            bottom_y = 970 - height
            middle_y = max(152, (1080 - height) // 2)
            placements = [
                ("left", 34, bottom_y, "bottom"),
                ("right", 1920 - width - 34, bottom_y, "bottom"),
                ("left", 34, middle_y, "middle"),
                ("right", 1920 - width - 34, middle_y, "middle"),
                ("left", 34, 152, "top"),
                ("right", 1920 - width - 34, 152, "top"),
                ("center", (1920 - width) // 2, bottom_y, "bottom"),
            ]
            for side, x, y, vertical in placements:
                overlap_values = []
                rectangle_values = []
                for content in content_masks:
                    region = content[y:y + height, x:x + width]
                    overlap_values.append(float(np.count_nonzero(region & person_mask)) / max(1, int(person_mask.sum())))
                    rectangle_values.append(float(region.mean()))
                overlap_cost = 0.72 * max(overlap_values) + 0.28 * float(np.mean(overlap_values))
                rectangle_cost = 0.18 * max(rectangle_values) + 0.07 * float(np.mean(rectangle_values))
                size_penalty = (520 - height) / 100.0 * 0.012
                side_penalty = 0.080 if preferred_side and side not in (preferred_side, "center") else 0.0
                center_penalty = 0.022 if side == "center" else 0.0
                vertical_penalty = 0.010 if vertical == "top" else 0.003 if vertical == "middle" else 0.0
                sample_costs = [
                    0.82 * overlap + 0.18 * rectangle + side_penalty + center_penalty + vertical_penalty
                    for overlap, rectangle in zip(overlap_values, rectangle_values)
                ]
                candidates.append(
                    {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "side": side,
                        "vertical": vertical,
                        "score": round(overlap_cost + rectangle_cost + size_penalty + side_penalty + center_penalty + vertical_penalty, 6),
                        "maximumContentOverlap": round(max(overlap_values), 6),
                        "action": action,
                        "sampleCosts": sample_costs,
                        "sampleOverlaps": overlap_values,
                    }
                )

        plans = []
        for height in (520, 480, 440, 400, 360, 320):
            states = [item for item in candidates if item["height"] == height]
            if preferred_side:
                states = [item for item in states if item["side"] in (preferred_side, "center")]
            state_count = len(states)
            time_count = len(sample_seconds)
            costs = np.full((time_count, state_count), np.inf, dtype=np.float64)
            previous = np.full((time_count, state_count), -1, dtype=np.int32)
            for state_index, state in enumerate(states):
                costs[0, state_index] = state["sampleCosts"][0]
            for time_index in range(1, time_count):
                for state_index, state in enumerate(states):
                    best_cost = np.inf
                    best_previous = -1
                    for prior_index, prior in enumerate(states):
                        changed = state_index != prior_index
                        distance = (
                            abs(state["x"] - prior["x"]) / 1920.0
                            + abs(state["y"] - prior["y"]) / 1080.0
                        )
                        transition = (0.010 + 0.018 * distance) if changed else 0.0
                        value = costs[time_index - 1, prior_index] + transition
                        if value < best_cost:
                            best_cost = value
                            best_previous = prior_index
                    costs[time_index, state_index] = best_cost + state["sampleCosts"][time_index]
                    previous[time_index, state_index] = best_previous
            final_index = int(np.argmin(costs[-1]))
            choices = [final_index]
            for time_index in range(time_count - 1, 0, -1):
                choices.append(int(previous[time_index, choices[-1]]))
            choices.reverse()
            maximum_overlap = max(
                float(states[state_index]["sampleOverlaps"][time_index])
                for time_index, state_index in enumerate(choices)
            )
            plans.append(
                {
                    "height": height,
                    "states": states,
                    "choices": choices,
                    "maximumOverlap": maximum_overlap,
                    "totalCost": float(costs[-1, final_index]),
                }
            )

        acceptable = [plan for plan in plans if plan["maximumOverlap"] <= 0.002]
        plan = max(acceptable, key=lambda item: item["height"]) if acceptable else min(plans, key=lambda item: item["totalCost"])
        states = plan["states"]
        choices = plan["choices"]
        windows = []
        group_start = 0
        for index in range(1, len(choices) + 1):
            if index < len(choices) and choices[index] == choices[group_start]:
                continue
            start = 0.0 if group_start == 0 else (sample_seconds[group_start - 1] + sample_seconds[group_start]) / 2
            end = duration if index == len(choices) else (sample_seconds[index - 1] + sample_seconds[index]) / 2
            state = states[choices[group_start]]
            windows.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "x": int(state["x"]),
                    "y": int(state["y"]),
                    "side": state["side"],
                    "vertical": state["vertical"],
                }
            )
            group_start = index

        initial = states[choices[0]]
        selected = {
            key: value for key, value in initial.items()
            if key not in {"sampleCosts", "sampleOverlaps"}
        }
        selected["mode"] = "dynamic-overlay"
        selected["courseWidth"] = 1920
        selected["courseHeight"] = 1080
        selected["courseX"] = 0
        selected["courseY"] = 0
        selected["windows"] = windows
        selected["windowCount"] = len(windows)
        selected["maximumContentOverlap"] = round(plan["maximumOverlap"], 6)
        if not acceptable:
            left_density = float(np.mean([mask[150:970, :300].mean() for mask in content_masks]))
            right_density = float(np.mean([mask[150:970, 1620:].mean() for mask in content_masks]))
            dock_side = preferred_side or ("left" if left_density <= right_density else "right")
            dock_height = 500
            dock_width = max(2, round(avatar_width * dock_height / avatar_height / 2) * 2)
            selected.update(
                {
                    "x": 22 if dock_side == "left" else 1920 - dock_width - 22,
                    "y": 290,
                    "width": dock_width,
                    "height": dock_height,
                    "side": dock_side,
                    "vertical": "middle",
                    "mode": "adaptive-dock",
                    "courseWidth": 1650,
                    "courseHeight": 928,
                    "courseX": 270 if dock_side == "left" else 0,
                    "courseY": 55,
                    "windows": [
                        {
                            "start": 0.0,
                            "end": round(duration, 3),
                            "x": 22 if dock_side == "left" else 1920 - dock_width - 22,
                            "y": 290,
                            "side": dock_side,
                            "vertical": "middle",
                        }
                    ],
                    "windowCount": 1,
                    "maximumContentOverlap": 0.0,
                    "edgeDensity": {"left": round(left_density, 6), "right": round(right_density, 6)},
                }
            )
        selected["flipHorizontal"] = bool(
            ("Point_Left" in action and selected["side"] == "left")
            or ("Point_Right" in action and selected["side"] == "right")
        )
        selected["decision"] = "content-timeline-safe-region"
        selected["sampleSeconds"] = [round(value, 3) for value in sample_seconds]
        return selected

    @staticmethod
    def _ass_time(value: float) -> str:
        centis = round(max(0.0, value) * 100)
        hours, centis = divmod(centis, 360_000)
        minutes, centis = divmod(centis, 6_000)
        seconds, centis = divmod(centis, 100)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"

    def _write_ass(self, timestamps: list[dict], path: Path, duration: float) -> None:
        header = [
            "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1200", "WrapStyle: 2", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Bottom,Hiragino Sans GB,36,&H00F4F7FA,&H000000FF,&H00071320,&H00071320,-1,0,0,0,100,100,0,0,1,1.6,0,2,90,90,32,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        events = []
        for item in timestamps:
            start = float(item.get("start", 0))
            end = min(duration, float(item.get("end", duration)))
            text = str(item.get("text", "")).replace("\n", "\\N").replace(",", "，")
            events.append(f"Dialogue: 0,{self._ass_time(start)},{self._ass_time(end)},Bottom,,0,0,0,,{text}")
        path.write_text("\n".join([*header, *events]), encoding="utf-8")

    @staticmethod
    def _motion_expression(windows: list[dict[str, Any]], key: str, transition: float = 0.45) -> str:
        if len(windows) <= 1:
            return str(int(windows[0][key]))

        def expression(index: int) -> str:
            if index >= len(windows):
                return str(int(windows[-1][key]))
            start = float(windows[index]["start"])
            previous = int(windows[index - 1][key])
            current = int(windows[index][key])
            following = expression(index + 1)
            if previous == current:
                return f"if(lt(t,{start:.3f}),{previous},{following})"
            end = start + transition
            interpolation = f"{previous}+({current - previous})*(t-{start:.3f})/{transition:.3f}"
            return (
                f"if(lt(t,{start:.3f}),{previous},"
                f"if(lt(t,{end:.3f}),{interpolation},{following}))"
            )

        return expression(1)

    def _compose(
        self,
        manim: Path,
        audio: Path,
        subtitles: list[dict],
        avatar: Path,
        avatar_start: float,
        avatar_end: float,
        destination: Path,
        placement: dict[str, Any],
    ) -> None:
        manim_info = self._probe(manim)
        audio_info = self._probe(audio)
        avatar_info = self._probe(avatar)
        target_duration = audio_info["durationSeconds"]
        speed_factor = target_duration / max(0.1, manim_info["durationSeconds"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        ass = destination.with_suffix(".ass")
        self._write_ass(subtitles, ass, target_duration)
        avatar_duration = max(0.1, avatar_info["durationSeconds"])
        window = max(0.1, avatar_end - avatar_start)
        avatar_factor = window / avatar_duration
        neutral_background_mask = (
            "if(gte(min(r(X,Y),min(g(X,Y),b(X,Y))),125)*"
            "lte(max(r(X,Y),max(g(X,Y),b(X,Y)))-"
            "min(r(X,Y),min(g(X,Y),b(X,Y))),24),0,255)"
        )
        teacher_width = int(placement["width"])
        teacher_height = int(placement["height"])
        teacher_x = int(placement["x"])
        teacher_y = int(placement["y"])
        course_width = int(placement.get("courseWidth", 1920))
        course_height = int(placement.get("courseHeight", 1080))
        course_x = int(placement.get("courseX", 0))
        course_y = int(placement.get("courseY", 0))
        source_windows = placement.get("windows") or [
            {"start": 0.0, "end": manim_info["durationSeconds"], "x": teacher_x, "y": teacher_y}
        ]
        target_windows = [
            {
                **item,
                "start": round(float(item["start"]) * speed_factor, 3),
                "end": round(min(target_duration, float(item["end"]) * speed_factor), 3),
            }
            for item in source_windows
        ]
        placement["targetWindows"] = target_windows
        teacher_x_expression = self._motion_expression(target_windows, "x")
        teacher_y_expression = self._motion_expression(target_windows, "y")
        horizontal_flip = "hflip," if placement.get("flipHorizontal") else ""
        filter_value = (
            f"[0:v]scale={course_width}:{course_height},setpts={speed_factor:.8f}*PTS,minterpolate=fps=60:mi_mode=blend,trim=duration={target_duration:.3f},"
            f"pad=1920:1200:{course_x}:{course_y}:color=#071722[course];"
            f"[1:v]scale={teacher_width}:{teacher_height},{horizontal_flip}setpts={avatar_factor:.8f}*PTS,"
            f"minterpolate=fps=60:mi_mode=blend,trim=duration={window:.3f},format=rgba,"
            f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{neutral_background_mask}',split[teacher_rgb][teacher_alpha_source];"
            "[teacher_alpha_source]alphaextract,erosion,gblur=sigma=0.6[teacher_alpha];"
            f"[teacher_rgb][teacher_alpha]alphamerge,setpts=PTS+{avatar_start:.3f}/TB[teacher];"
            f"[course][teacher]overlay=x='{teacher_x_expression}':y='{teacher_y_expression}':eval=frame:eof_action=pass:"
            f"enable='between(t,{avatar_start:.3f},{avatar_end:.3f})'[with_teacher];"
            f"[with_teacher]subtitles='{ass.as_posix()}'[out]"
        )
        process = subprocess.run(
            [
                self.ffmpeg, "-y", "-i", str(manim), "-i", str(avatar), "-i", str(audio),
                "-filter_complex", filter_value, "-map", "[out]", "-map", "2:a:0",
                "-t", f"{target_duration:.3f}", "-r", "60", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "128k", "-shortest", str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        destination.with_suffix(".stdout.log").write_text(process.stdout, encoding="utf-8")
        destination.with_suffix(".stderr.log").write_text(process.stderr, encoding="utf-8")
        if process.returncode != 0:
            raise RuntimeError("课程合成失败：" + process.stderr[-4000:])

    def build(
        self,
        outline_path: str | Path,
        manim_manifest_path: str | Path,
        tts_timeline_path: str | Path,
        avatar_manifest_path: str | Path,
        output_dir: str | Path,
        *,
        execute: bool = True,
    ) -> dict[str, Any]:
        outline = json.loads(Path(outline_path).read_text(encoding="utf-8"))
        manim = json.loads(Path(manim_manifest_path).read_text(encoding="utf-8"))
        tts = json.loads(Path(tts_timeline_path).read_text(encoding="utf-8"))
        avatar = json.loads(Path(avatar_manifest_path).read_text(encoding="utf-8"))
        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        manim_by_name = {Path(item["path"]).stem: Path(item["path"]) for item in manim.get("videos", [])}
        avatar_by_scene = {int(item["sceneId"]): item for item in avatar.get("main", [])}
        avatar_by_interrupt = {str(item["interruptId"]): item for item in avatar.get("interruptions", [])}
        gesture_by_scene = {int(item["sceneId"]): item for item in avatar.get("gestureSchedule", {}).get("schedule", [])}
        teacher_always = bool(avatar.get("teacherAlways"))

        main_outputs = []
        for scene in tts.get("scenes", []):
            scene_id = int(scene["sceneId"])
            gesture = gesture_by_scene[scene_id]
            scene_start = float(scene["start"])
            if teacher_always:
                action_start = 0.0
                action_end = float(scene["durationSeconds"])
            else:
                action_start = max(0.0, float(gesture["start"]) - scene_start)
                action_end = max(action_start + 0.1, float(gesture["end"]) - scene_start)
            destination = root / "main" / f"scene_{scene_id:02d}.mp4"
            avatar_item = avatar_by_scene[scene_id]
            action = str(avatar_item.get("action") or gesture.get("gesture") or "")
            manim_path = manim_by_name[f"Scene{scene_id:02d}"]
            avatar_path = Path(avatar_item["video"])
            placement = (
                self._choose_teacher_layout(manim_path, avatar_path, action)
                if execute else {"decision": "pending-content-analysis", "action": action}
            )
            command_spec = {
                "sceneId": scene_id,
                "manim": str(manim_path),
                "audio": scene["audio"],
                "avatar": str(avatar_path),
                "avatarStart": action_start,
                "avatarEnd": action_end,
                "placement": placement,
                "output": str(destination),
            }
            if execute:
                self._compose(
                    Path(command_spec["manim"]), Path(command_spec["audio"]), scene["sentenceTimestamps"],
                    Path(command_spec["avatar"]), action_start, action_end, destination, placement,
                )
                command_spec["result"] = self._probe(destination)
            main_outputs.append(command_spec)

        branch_outputs = []
        outline_interruptions = {str(item.get("interrupt_id")): item for item in outline.get("interruptions", [])}
        for index, branch in enumerate(tts.get("interruptions", []), start=1):
            interrupt_id = str(branch["interruptId"])
            outline_branch = outline_interruptions[interrupt_id]
            destination = root / "branches" / f"interrupt_{index:02d}.mp4"
            avatar_item = avatar_by_interrupt[interrupt_id]
            action = str(avatar_item.get("action") or outline_branch.get("branch_action") or "")
            manim_path = manim_by_name[f"Branch{index:02d}"]
            avatar_path = Path(avatar_item["video"])
            placement = (
                self._choose_teacher_layout(manim_path, avatar_path, action)
                if execute else {"decision": "pending-content-analysis", "action": action}
            )
            command_spec = {
                "interruptId": interrupt_id,
                "afterScene": branch["afterScene"],
                "studentState": branch["studentState"],
                "studentUtterance": outline_branch["student_utterance"],
                "manim": str(manim_path),
                "audio": branch["audio"],
                "avatar": str(avatar_path),
                "placement": placement,
                "resumeInstruction": branch["resumeInstruction"],
                "output": str(destination),
            }
            if execute:
                branch_avatar_duration = self._probe(Path(command_spec["avatar"]))["durationSeconds"]
                branch_avatar_end = (
                    float(branch["durationSeconds"])
                    if teacher_always
                    else min(float(branch["durationSeconds"]), branch_avatar_duration)
                )
                self._compose(
                    Path(command_spec["manim"]), Path(command_spec["audio"]), branch["sentenceTimestamps"],
                    Path(command_spec["avatar"]), 0.0, branch_avatar_end, destination, placement,
                )
                command_spec["result"] = self._probe(destination)
            branch_outputs.append(command_spec)

        main_video = root / "ai-intro-mooc.mp4"
        main_video_result = None
        if execute:
            concat_file = root / "main-concat.txt"
            concat_file.write_text(
                "\n".join(f"file '{Path(item['output']).as_posix()}'" for item in main_outputs),
                encoding="utf-8",
            )
            process = subprocess.run(
                [self.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(main_video)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            (root / "concat.stdout.log").write_text(process.stdout, encoding="utf-8")
            (root / "concat.stderr.log").write_text(process.stderr, encoding="utf-8")
            if process.returncode != 0:
                raise RuntimeError("主课程拼接失败：" + process.stderr[-4000:])
            main_video_result = self._probe(main_video)

        playback = []
        branch_by_scene = {int(item["afterScene"]): item for item in branch_outputs}
        for scene in main_outputs:
            playback.append({"type": "main", "sceneId": scene["sceneId"], "video": scene["output"]})
            if scene["sceneId"] in branch_by_scene:
                item = branch_by_scene[scene["sceneId"]]
                playback.append(
                    {
                        "type": "interrupt_option",
                        "afterScene": scene["sceneId"],
                        "interruptId": item["interruptId"],
                        "studentState": item["studentState"],
                        "studentUtterance": item["studentUtterance"],
                        "branchVideo": item["output"],
                        "resumeInstruction": item["resumeInstruction"],
                        "resumeScene": scene["sceneId"] + 1,
                    }
                )
        manifest = {
            "course": outline.get("course", {}),
            "mainVideo": str(main_video),
            "mainVideoResult": main_video_result,
            "main": main_outputs,
            "branches": branch_outputs,
            "playback": playback,
            "executed": execute,
            "teacherAlways": teacher_always,
            "passed": (not execute) or (
                len(main_outputs) == 6 and len(branch_outputs) == 4
                and all(item.get("result", {}).get("width") == 1920 and item.get("result", {}).get("height") == 1200 for item in [*main_outputs, *branch_outputs])
            ),
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest"] = str(manifest_path)
        return manifest
