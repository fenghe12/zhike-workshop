"""
智课工坊 - 全流水线调度器
S1(PPT生成) → S2(翻译) → S3(TTS) → S4(数字人) → S5(合成)

每个 stage 的输出走 /workspace/tasks/{task_id}/s{N}_output/
状态通过 status.json 跟踪，支持断点续跑
"""

import os
import sys
import json
import time
import logging
import traceback
from pathlib import Path
from typing import Dict, Optional, Callable
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Pipeline")

WORKSPACE_ROOT = os.environ.get("SMARTCOURSE_WORKSPACE_ROOT", "/mnt/smartcourse/data/tasks")

# Agent source paths
PPTX_TRANSLATE_DIR = os.environ.get("SMARTCOURSE_PPTX_TRANSLATE_ROOT", "/mnt/smartcourse/models/pptx-translate")
INDEX_TTS_DIR = os.environ.get("SMARTCOURSE_TTS_ROOT", "/mnt/smartcourse/models/index-tts")
FLOAT_DIR = os.environ.get("SMARTCOURSE_FLOAT_ROOT", "/mnt/smartcourse/models/float")
MERGER_DIR = os.environ.get("SMARTCOURSE_MERGER_ROOT", "/mnt/smartcourse/models/merger")

DEFAULT_SPEAKER_PROMPT = os.environ.get("SMARTCOURSE_DEFAULT_REFERENCE_AUDIO", "/mnt/smartcourse/data/uploads/default_speaker.wav")
DEFAULT_REF_IMAGE = os.environ.get("SMARTCOURSE_DEFAULT_REFERENCE_IMAGE", "/mnt/smartcourse/data/uploads/default_avatar.png")


class Pipeline:
    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root

    def _task_dir(self, task_id: str) -> str:
        return os.path.join(self.workspace_root, task_id)

    def _status_path(self, task_id: str) -> str:
        return os.path.join(self._task_dir(task_id), "status.json")

    def _load_status(self, task_id: str) -> Dict:
        path = self._status_path(task_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"task_id": task_id, "stages": {}, "created_at": datetime.now().isoformat()}

    def _save_status(self, task_id: str, status: Dict):
        os.makedirs(self._task_dir(task_id), exist_ok=True)
        status["updated_at"] = datetime.now().isoformat()
        with open(self._status_path(task_id), "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)

    def _update_stage(self, task_id: str, stage: str, state: str, result: Optional[Dict] = None, error: Optional[str] = None):
        status = self._load_status(task_id)
        status["stages"][stage] = {
            "state": state,
            "updated_at": datetime.now().isoformat(),
        }
        if result:
            status["stages"][stage]["result"] = result
        if error:
            status["stages"][stage]["error"] = error
        self._save_status(task_id, status)

    def run(
        self,
        task_id: str,
        # S1 params
        course_topic: str = "",
        total_pages: int = 10,
        target_language: str = "English",
        # S1 alt: provide existing PPT
        existing_pptx: Optional[str] = None,
        existing_script: Optional[str] = None,
        # S3 params
        speaker_prompt: str = DEFAULT_SPEAKER_PROMPT,
        # S4 params
        ref_image: str = DEFAULT_REF_IMAGE,
        gpu_id: int = 0,
        # Control
        start_stage: str = "s1",
        end_stage: str = "s5",
        skip_stages: Optional[list] = None,
    ) -> Dict:
        skip = set(skip_stages or [])
        status = self._load_status(task_id)
        os.makedirs(self._task_dir(task_id), exist_ok=True)

        logger.info(f"{'='*60}")
        logger.info(f"Pipeline START: task={task_id}")
        logger.info(f"  topic={course_topic}, pages={total_pages}, lang={target_language}")
        logger.info(f"  skip={skip}, start={start_stage}, end={end_stage}")
        logger.info(f"{'='*60}")

        pipeline_result = {"task_id": task_id, "stages": {}}

        # ========== S1: PPT Generation ==========
        if "s1" not in skip and start_stage <= "s1":
            try:
                self._update_stage(task_id, "s1", "running")
                logger.info("[S1] PPT Generation...")

                if existing_pptx and existing_script:
                    s1_result = self._s1_from_existing(task_id, existing_pptx, existing_script)
                else:
                    s1_result = self._run_s1(task_id, course_topic, total_pages, target_language)

                self._update_stage(task_id, "s1", "done", s1_result)
                pipeline_result["stages"]["s1"] = s1_result
                logger.info(f"[S1] Done: {s1_result.get('pages', '?')} pages")
            except Exception as e:
                logger.error(f"[S1] Failed: {e}")
                self._update_stage(task_id, "s1", "error", error=str(e))
                pipeline_result["stages"]["s1"] = {"error": str(e)}
                if end_stage >= "s1":
                    return pipeline_result

        # ========== S2: Translation ==========
        if "s2" not in skip and start_stage <= "s2" and end_stage >= "s2":
            try:
                self._update_stage(task_id, "s2", "running")
                logger.info("[S2] Translation...")

                s2_result = self._run_s2(task_id, target_language)

                self._update_stage(task_id, "s2", "done", s2_result)
                pipeline_result["stages"]["s2"] = s2_result
                logger.info(f"[S2] Done")
            except Exception as e:
                logger.error(f"[S2] Failed: {e}")
                self._update_stage(task_id, "s2", "error", error=str(e))
                pipeline_result["stages"]["s2"] = {"error": str(e)}
                if end_stage >= "s2":
                    return pipeline_result

        # ========== S3: TTS ==========
        if "s3" not in skip and start_stage <= "s3" and end_stage >= "s3":
            try:
                self._update_stage(task_id, "s3", "running")
                logger.info("[S3] TTS...")

                s3_result = self._run_s3(task_id, speaker_prompt)

                self._update_stage(task_id, "s3", "done", s3_result)
                pipeline_result["stages"]["s3"] = s3_result
                logger.info(f"[S3] Done: {s3_result.get('total_duration', 0):.1f}s")
            except Exception as e:
                logger.error(f"[S3] Failed: {e}")
                self._update_stage(task_id, "s3", "error", error=str(e))
                pipeline_result["stages"]["s3"] = {"error": str(e)}
                if end_stage >= "s3":
                    return pipeline_result

        # ========== S4: Digital Human ==========
        if "s4" not in skip and start_stage <= "s4" and end_stage >= "s4":
            try:
                self._update_stage(task_id, "s4", "running")
                logger.info("[S4] Digital Human...")

                s4_result = self._run_s4(task_id, ref_image, gpu_id)

                self._update_stage(task_id, "s4", "done", s4_result)
                pipeline_result["stages"]["s4"] = s4_result
                logger.info(f"[S4] Done: {s4_result.get('success_pages', 0)}/{s4_result.get('total_pages', 0)}")
            except Exception as e:
                logger.error(f"[S4] Failed: {e}")
                self._update_stage(task_id, "s4", "error", error=str(e))
                pipeline_result["stages"]["s4"] = {"error": str(e)}
                if end_stage >= "s4":
                    return pipeline_result

        # ========== S5: Video Composition ==========
        if "s5" not in skip and start_stage <= "s5" and end_stage >= "s5":
            try:
                self._update_stage(task_id, "s5", "running")
                logger.info("[S5] Video Composition...")

                s5_result = self._run_s5(task_id)

                self._update_stage(task_id, "s5", "done", s5_result)
                pipeline_result["stages"]["s5"] = s5_result
                logger.info(f"[S5] Done: {s5_result.get('output_path', '?')}")
            except Exception as e:
                logger.error(f"[S5] Failed: {e}")
                self._update_stage(task_id, "s5", "error", error=str(e))
                pipeline_result["stages"]["s5"] = {"error": str(e)}

        # Final status
        self._update_stage(task_id, "pipeline", "done", pipeline_result)
        logger.info(f"{'='*60}")
        logger.info(f"Pipeline DONE: task={task_id}")
        logger.info(f"{'='*60}")
        return pipeline_result

    # ========== Stage Runners ==========

    def _s1_from_existing(self, task_id, pptx_path, script_path):
        """Register existing PPT as S1 output."""
        output_dir = os.path.join(self._task_dir(task_id), "s1_output")
        os.makedirs(output_dir, exist_ok=True)

        import shutil
        dst_pptx = os.path.join(output_dir, "generated.pptx")
        if os.path.abspath(pptx_path) != os.path.abspath(dst_pptx):
            shutil.copy2(pptx_path, dst_pptx)

        # Build course_structure.json from script
        pages = []
        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8") as f:
                text = f.read()
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for i, para in enumerate(paragraphs, 1):
                pages.append({"page_id": i, "script_text": para})

        structure = {"task_id": task_id, "pages": pages}
        structure_path = os.path.join(output_dir, "course_structure.json")
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False)

        return {
            "task_id": task_id,
            "pptx_path": dst_pptx,
            "structure_path": structure_path,
            "pages": len(pages),
            "source": "existing",
        }

    def _run_s1(self, task_id, course_topic, total_pages, target_language):
        sys.path.insert(0, PPTX_TRANSLATE_DIR)
        from ppt_generator import PPTGenerator

        agent = PPTGenerator(workspace_root=self.workspace_root)
        return agent.run(
            task_id=task_id,
            course_topic=course_topic,
            total_pages=total_pages,
            target_language=target_language,
        )

    def _run_s2(self, task_id, target_language):
        s1_output = os.path.join(self._task_dir(task_id), "s1_output")
        source_json = os.path.join(s1_output, "course_structure.json")
        pptx_path = os.path.join(s1_output, "generated.pptx")

        if not os.path.exists(source_json):
            raise FileNotFoundError(f"S1 output not found: {source_json}")

        # S2a: Translate structure (script_text, key_points, etc.)
        sys.path.insert(0, PPTX_TRANSLATE_DIR)
        from translate_agent import TranslateAgent

        agent = TranslateAgent(workspace_root=self.workspace_root)
        s2a_result = agent.run(
            task_id=task_id,
            source_json=source_json,
            target_language=target_language,
        )

        # S2b: Translate PPTX text in-place
        if os.path.exists(pptx_path):
            s2_output_dir = os.path.join(self._task_dir(task_id), "s2_output")
            translated_pptx = os.path.join(s2_output_dir, "translated.pptx")

            from ppt_translate_gateway_v2 import translate_presentation
            import asyncio
            asyncio.run(translate_presentation(
                presentation_path=pptx_path,
                target_language=target_language,
                output_path=translated_pptx,
            ))
            s2a_result["translated_pptx"] = translated_pptx

        return s2a_result

    def _run_s3(self, task_id, speaker_prompt):
        s2_output = os.path.join(self._task_dir(task_id), "s2_output")
        source_json = os.path.join(s2_output, "translated_structure.json")

        if not os.path.exists(source_json):
            raise FileNotFoundError(f"S2 output not found: {source_json}")

        sys.path.insert(0, INDEX_TTS_DIR)

        # Change to index-tts dir for checkpoint loading
        old_cwd = os.getcwd()
        os.chdir(INDEX_TTS_DIR)
        try:
            # Import dynamically to use correct working directory
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "tts_agent", os.path.join(INDEX_TTS_DIR, "0416_test.py")
            )
            tts_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tts_module)

            agent = tts_module.TTSAgent(
                workspace_root=self.workspace_root,
                speaker_prompt=speaker_prompt,
            )
            return agent.run(task_id=task_id, source_json=source_json)
        finally:
            os.chdir(old_cwd)

    def _run_s4(self, task_id, ref_image, gpu_id):
        s2_output = os.path.join(self._task_dir(task_id), "s2_output")
        s4_output = os.path.join(self._task_dir(task_id), "s4_output")

        # S4a: BBox
        pptx_path = os.path.join(s2_output, "translated.pptx")
        if not os.path.exists(pptx_path):
            pptx_path = os.path.join(self._task_dir(task_id), "s1_output", "generated.pptx")

        bbox_result = None
        if os.path.exists(pptx_path):
            sys.path.insert(0, PPTX_TRANSLATE_DIR)
            from bounding_box import BBoxAgent
            bbox_agent = BBoxAgent(workspace_root=self.workspace_root)
            bbox_result = bbox_agent.run(task_id=task_id, pptx_path=pptx_path)
            logger.info(f"[S4a] BBox done: {bbox_result.get('total_slides', 0)} slides")

        # S4b: Avatar generation
        timeline_json = os.path.join(self._task_dir(task_id), "s3_output", "timeline.json")
        if not os.path.exists(timeline_json):
            raise FileNotFoundError(f"S3 timeline not found: {timeline_json}")

        sys.path.insert(0, FLOAT_DIR)
        from s4_avatar_agent import AvatarAgent

        avatar_agent = AvatarAgent(
            workspace_root=self.workspace_root,
            ref_image=ref_image,
            gpu_id=gpu_id,
        )
        avatar_result = avatar_agent.run(
            task_id=task_id,
            timeline_json=timeline_json,
        )

        if bbox_result:
            avatar_result["bbox"] = bbox_result

        return avatar_result

    def _run_s5(self, task_id):
        task_dir = self._task_dir(task_id)
        s2_output = os.path.join(task_dir, "s2_output")
        s3_output = os.path.join(task_dir, "s3_output")
        s4_output = os.path.join(task_dir, "s4_output")

        # Find PPTX
        pptx_path = os.path.join(s2_output, "translated.pptx")
        if not os.path.exists(pptx_path):
            pptx_path = os.path.join(task_dir, "s1_output", "generated.pptx")

        timeline_json = os.path.join(s3_output, "timeline.json")
        avatars_dir = os.path.join(s4_output, "avatars")
        bbox_json = os.path.join(s4_output, "bbox.json")
        srt_path = os.path.join(s3_output, "subtitles.srt")

        from s5_compose_agent import ComposeAgent
        agent = ComposeAgent(workspace_root=self.workspace_root)
        return agent.run(
            task_id=task_id,
            pptx_path=pptx_path,
            timeline_json=timeline_json,
            avatars_dir=avatars_dir,
            bbox_json=bbox_json if os.path.exists(bbox_json) else None,
            subtitle_srt=srt_path if os.path.exists(srt_path) else None,
        )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SmartCourse Pipeline")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--topic", default="", help="Course topic (for S1)")
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--target-lang", default="English")
    parser.add_argument("--pptx", default=None, help="Existing PPTX (skip S1)")
    parser.add_argument("--script", default=None, help="Existing script (skip S1)")
    parser.add_argument("--speaker", default=DEFAULT_SPEAKER_PROMPT)
    parser.add_argument("--ref-image", default=DEFAULT_REF_IMAGE)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--start", default="s1", choices=["s1", "s2", "s3", "s4", "s5"])
    parser.add_argument("--end", default="s5", choices=["s1", "s2", "s3", "s4", "s5"])
    parser.add_argument("--skip", nargs="*", default=[], help="Stages to skip")
    parser.add_argument("--workspace", default=WORKSPACE_ROOT)
    args = parser.parse_args()

    pipe = Pipeline(workspace_root=args.workspace)
    result = pipe.run(
        task_id=args.task_id,
        course_topic=args.topic,
        total_pages=args.pages,
        target_language=args.target_lang,
        existing_pptx=args.pptx,
        existing_script=args.script,
        speaker_prompt=args.speaker,
        ref_image=args.ref_image,
        gpu_id=args.gpu,
        start_stage=args.start,
        end_stage=args.end,
        skip_stages=args.skip,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
