from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from app.demo_course import build_demo_course_manifest, prepare_demo_package
from app.performance import PipelinePerformanceRecorder
from app.rehearsal_analyzer import analyze_rehearsal
from app.teacher_avatar import build_teacher_profile, schedule_gestures, schedule_outline_actions
from app.interactive_course import (
    COURSE_GESTURE_EVENTS,
    execute_fixed_interrupt,
    get_interruption,
    list_interruptions,
)
from app.ai_intro_product import ai_intro_status, execute_fixed_ai_intro_interrupt
from agents.s4_longcat_avatar_agent import LongCatAvatarAgent
from agents.ai_intro_manim_agent import AIIntroManimAgent
from agents.ai_intro_composer import AIIntroComposer
from agents.ai_intro_avatar_agent import AIIntroAvatarAgent


class TeacherProductTests(unittest.TestCase):
    def test_longcat_engine_makes_gesture_course_possible_without_recorded_clips(self):
        profile = build_teacher_profile(
            "teacher_demo",
            "/tmp/person.png",
            "/tmp/voice.wav",
            {},
            {"authorized": True, "scope": "internal_demo"},
            {"name": "longcat-video-avatar-1.5", "available": True},
        )
        self.assertTrue(profile["readiness"]["faceCourse"])
        self.assertTrue(profile["readiness"]["gestureCourse"])

    def test_gesture_schedule_uses_longcat_generation_fallback(self):
        profile = build_teacher_profile(
            "teacher_demo",
            "/tmp/person.png",
            "/tmp/voice.wav",
            {},
            {"authorized": True},
            {"name": "longcat-video-avatar-1.5", "available": True},
        )
        ir = {
            "timeline": {
                "events": [
                    {
                        "eventId": "s01_e01",
                        "concept": "观察函数图像",
                        "teachingIntent": "explain_and_apply",
                        "start": 0,
                        "end": 8,
                        "visual": {"target": "chart"},
                        "instructorBehavior": {"gesture": "deictic_point"},
                    },
                    {
                        "eventId": "s02_e01",
                        "concept": "总结三个结论",
                        "teachingIntent": "retrieve_and_self_explain",
                        "start": 12,
                        "end": 20,
                        "visual": {"target": "summary"},
                        "instructorBehavior": {"gesture": "open_palm_prompt"},
                    },
                ]
            }
        }
        schedule = schedule_gestures(ir, profile)
        self.assertEqual(schedule["schedule"][0]["gesture"], "Action_Point_Right")
        self.assertTrue(schedule["schedule"][0]["fallback"].startswith("generate_with:"))
        self.assertEqual(schedule["missingRequestedGestures"], [])

    def test_rehearsal_reports_long_interaction_gap(self):
        structure = {"course_topic": "课程", "pages": [{"page_id": 1, "title": "概念", "key_points": ["A"], "script_text": "这是完整讲稿。"}]}
        ir = {"timeline": {"durationSeconds": 1300, "events": [{"eventId": "s01_e01", "start": 0, "end": 20, "dialogue": {"act": "none"}, "teachingIntent": "explain_and_apply"}]}}
        report = analyze_rehearsal(structure, ir, 600)
        self.assertFalse(report["publishReady"])
        self.assertTrue(any(issue["type"] == "interaction_gap" for issue in report["issues"]))

    def test_longcat_agent_builds_official_int8_distilled_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timeline = root / "timeline.json"
            timeline.write_text(json.dumps({"pages": [{"page_id": 1, "duration": 5.0, "wav_path": str(root / "voice.wav")}]}), encoding="utf-8")
            agent = LongCatAvatarAgent(root / "repo", root / "env/bin/python", root / "weights/LongCat-Video-Avatar-1.5", (0, 1))
            result = agent.run(
                "task",
                str(timeline),
                str(root / "person.png"),
                {"schedule": [{"eventId": "s01_e01", "gesture": "right_hand_point"}]},
                {"pages": [{"page_id": 1, "title": "人工智能概述"}]},
                str(root / "out"),
                dry_run=True,
            )
            command = result["pages"][0]["command"]
            self.assertIn("--use_int8", command)
            self.assertIn("--use_distill", command)
            self.assertIn("--model_type=avatar-v1.5", command)
            self.assertIn("--context_parallel_size=2", command)
            payload = json.loads(Path(result["pages"][0]["inputJson"]).read_text(encoding="utf-8"))
            self.assertIn("extends the right arm", payload["prompt"])
            self.assertIn("left hand relaxed", payload["prompt"])

    def test_outline_schedule_contains_six_distinct_full_body_actions(self):
        actions = [
            "Action_Greet", "Action_Explain", "Action_Point_Left",
            "Action_Point_Right", "Action_Think", "Action_Summarize",
        ]
        outline = {
            "scenes": [
                {"scene_id": index, "title": f"场景{index}", "full_body_action": action, "action_trigger_sentence": f"触发句{index}"}
                for index, action in enumerate(actions, 1)
            ]
        }
        times = {index: {"start": index * 10.0, "end": index * 10.0 + 4.0} for index in range(1, 7)}
        result = schedule_outline_actions(outline, times)
        self.assertEqual(result["eventCount"], 6)
        self.assertEqual({item["gesture"] for item in result["schedule"]}, set(actions))

    def test_performance_report_does_not_invent_cost(self):
        recorder = PipelinePerformanceRecorder("task")
        recorder.run_stage("S1", lambda: "ok")
        report = recorder.report(20)
        self.assertIsNone(report["estimatedNpuCost"])
        self.assertEqual(report["costStatus"], "hourly_price_not_configured")

    def test_demo_manifest_reports_missing_or_available_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = build_demo_course_manifest(root)
            self.assertEqual(manifest["status"], "incomplete")
            prepared = prepare_demo_package(root, root / "output")
            self.assertTrue(Path(prepared["manifest"]).is_file())

    def test_fixed_interruption_catalog_has_four_distinct_intents(self):
        catalog = list_interruptions()
        self.assertEqual(catalog["scenarioCount"], 4)
        self.assertEqual(len({item["intent"] for item in catalog["scenarios"]}), 4)

    def test_course_gestures_follow_explanation_pointing_and_summary(self):
        gestures = [item["gesture"] for item in COURSE_GESTURE_EVENTS]
        self.assertIn("neutral", gestures)
        self.assertIn("single_hand_out", gestures)
        self.assertIn("two_hands_out", gestures)
        for event in COURSE_GESTURE_EVENTS:
            self.assertTrue(event["text"])
            self.assertTrue(event["visualTarget"])

    def test_interrupt_trace_pauses_generates_branch_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = execute_fixed_interrupt("specific_question", directory)
            states = [item["state"] for item in result["playbackTrace"]]
            self.assertEqual(states[0], "playing")
            self.assertIn("paused", states)
            self.assertIn("branch_generated", states)
            self.assertEqual(states[-1], "resumed")
            self.assertTrue(Path(result["artifacts"]["branchHtml"]).is_file())
            self.assertTrue(Path(result["artifacts"]["manimSource"]).is_file())

    def test_each_interruption_has_carrier_gestures_and_resume_anchor(self):
        for scenario_id in (
            "not_understood",
            "specific_question",
            "deeper_exploration",
            "need_simpler",
        ):
            scenario = get_interruption(scenario_id)
            self.assertIn(scenario["carrier"], {"pptx", "manim"})
            self.assertGreaterEqual(len(scenario["gestureSequence"]), 3)
            self.assertGreater(scenario["resume"]["courseTimeSeconds"], 0)

    def test_ai_intro_manim_agent_emits_six_scenes_and_four_branches(self):
        source = AIIntroManimAgent.source(
            {"course": {"title": "AI导论"}, "scenes": [{}] * 6, "interruptions": [{}] * 4},
            {"neural_network": "/tmp/network.svg", "ct_scan": "/tmp/ct.jpg", "self_driving": "/tmp/car.jpg"},
        )
        compile(source, "ai_intro_course.py", "exec", dont_inherit=True)
        for name in [*(f"class Scene{i:02d}" for i in range(1, 7)), *(f"class Branch{i:02d}" for i in range(1, 5))]:
            self.assertIn(name, source)

    def test_ai_intro_composer_writes_six_main_and_four_interrupt_specs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outline = {
                "course": {"title": "AI导论"},
                "scenes": [{"scene_id": i} for i in range(1, 7)],
                "interruptions": [
                    {"interrupt_id": f"i{i}", "student_utterance": f"问题{i}"}
                    for i in range(1, 5)
                ],
            }
            manim = {"videos": [{"path": str(root / f"Scene{i:02d}.mp4")} for i in range(1, 7)] + [{"path": str(root / f"Branch{i:02d}.mp4")} for i in range(1, 5)]}
            tts = {
                "scenes": [
                    {"sceneId": i, "start": (i-1)*10, "audio": str(root/f"s{i}.wav"), "sentenceTimestamps": []}
                    for i in range(1, 7)
                ],
                "interruptions": [
                    {"interruptId": f"i{i}", "afterScene": i, "studentState": "固定", "audio": str(root/f"b{i}.wav"), "durationSeconds": 4, "sentenceTimestamps": [], "resumeInstruction": "恢复"}
                    for i in range(1, 5)
                ],
            }
            avatars = {
                "main": [{"sceneId": i, "video": str(root/f"a{i}.mp4")} for i in range(1, 7)],
                "interruptions": [{"interruptId": f"i{i}", "video": str(root/f"ia{i}.mp4")} for i in range(1, 5)],
                "gestureSchedule": {"schedule": [{"sceneId": i, "start": (i-1)*10+1, "end": (i-1)*10+4} for i in range(1, 7)]},
            }
            for name, value in (("outline.json", outline), ("manim.json", manim), ("tts.json", tts), ("avatar.json", avatars)):
                (root/name).write_text(json.dumps(value), encoding="utf-8")
            result = AIIntroComposer().build(root/"outline.json", root/"manim.json", root/"tts.json", root/"avatar.json", root/"out", execute=False)
            self.assertEqual(len(result["main"]), 6)
            self.assertEqual(len(result["branches"]), 4)
            self.assertEqual(len([item for item in result["playback"] if item["type"] == "interrupt_option"]), 4)

    def test_ai_intro_avatar_job_uses_requested_six_action_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "action.wav"
            with wave.open(str(audio), "wb") as value:
                value.setnchannels(1)
                value.setsampwidth(2)
                value.setframerate(44100)
                value.writeframes(b"\0\0" * 44100 * 4)
            reference = root / "teacher.png"
            reference.write_bytes(b"image")
            longcat = LongCatAvatarAgent(root / "repo", root / "env/bin/python", root / "weights/LongCat-Video-Avatar-1.5", (0, 1))
            agent = AIIntroAvatarAgent(longcat)
            agent._duration = lambda _path: 4.0
            job = agent._job("scene", "总结检测、融合与空间理解", "Action_Summarize", audio, reference, root / "out")
            payload = json.loads(Path(job["inputJson"]).read_text(encoding="utf-8"))
            self.assertEqual(job["action"], "Action_Summarize")
            self.assertIn("moves both hands inward", payload["prompt"])
            self.assertIn("brings them together", payload["prompt"])

    def test_ai_intro_status_and_fixed_interrupt_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"manim-v2").mkdir()
            (root/"s3").mkdir()
            (root/"s4-longcat").mkdir()
            (root/"s5").mkdir()
            outline = {
                "course": {"title": "AI导论"},
                "scenes": [{"scene_id": i, "title": f"场景{i}", "full_body_action": "neutral_explain", "action_trigger_sentence": "触发"} for i in range(1, 7)],
                "interruptions": [
                    {"interrupt_id": str(i), "after_scene": i, "student_state": "固定", "student_utterance": f"问题{i}", "branch_title": f"分支{i}", "branch_carrier": "manim", "resume_instruction": "恢复"}
                    for i in range(1, 5)
                ],
            }
            (root/"outline.json").write_text(json.dumps(outline), encoding="utf-8")
            (root/"manim-v2/manifest.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            (root/"s3/timeline.json").write_text(json.dumps({"scenes": [{}]*6, "interruptions": [{}]*4}), encoding="utf-8")
            (root/"s4-longcat/manifest.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            playback = [{"type": "interrupt_option", "interruptId": str(i), "branchVideo": f"branch{i}.mp4"} for i in range(1, 5)]
            (root/"s5/manifest.json").write_text(json.dumps({"passed": True, "mainVideo": "main.mp4", "playback": playback}), encoding="utf-8")
            status = ai_intro_status(root)
            self.assertTrue(status["ready"])
            result = execute_fixed_ai_intro_interrupt(root, "2")
            self.assertEqual(result["stateTrace"][1]["state"], "paused")
            self.assertEqual(result["stateTrace"][-1]["state"], "resumed")
            self.assertEqual(result["resumeScene"], 3)


if __name__ == "__main__":
    unittest.main()
