"""
S4b 数字人生成智能体：音频 → 数字人说话视频
输入: s3_output/timeline.json (每页音频时间线)
输出: s4_output/avatars/page_*.mp4
依赖: s4_float_inference.py 中的 InferenceAgent
"""

import os
import sys
import json
import time
import logging
import argparse

try:
    from .device import accelerator_context, select_device
except ImportError:
    from device import accelerator_context, select_device

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("AvatarAgent")

# ==================== 统一配置加载 ====================
import yaml as _yaml
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AGENT_DIR, "config.yaml"), "r", encoding="utf-8") as _cf:
    _CFG = _yaml.safe_load(_cf)

SOURCE_ROOT = os.environ.get("SMARTCOURSE_SOURCE_ROOT", "/mnt/smartcourse/models")
WORKSPACE_ROOT = os.environ.get("SMARTCOURSE_WORKSPACE_ROOT", _CFG["paths"]["workspace"])
FLOAT_DIR = os.environ.get("SMARTCOURSE_FLOAT_ROOT", os.path.join(SOURCE_ROOT, "float"))
DEFAULT_REF_IMAGE = ""
DEFAULT_CKPT = os.path.join(FLOAT_DIR, "checkpoints", "float.pth")


class AvatarAgent:
    def __init__(
        self,
        workspace_root: str = WORKSPACE_ROOT,
        float_dir: str = FLOAT_DIR,
        ref_image: str = DEFAULT_REF_IMAGE,
        ckpt_path: str = DEFAULT_CKPT,
        gpu_id: int = 0,
        emo: str = "neutral",
        seed: int = 15,
        a_cfg: float = 2.0,
        e_cfg: float = 1.0,
        no_crop: bool = True,
    ):
        self.workspace_root = workspace_root
        self.float_dir = float_dir
        self.ref_image = ref_image
        self.ckpt_path = ckpt_path
        self.gpu_id = gpu_id
        self.device = select_device(gpu_id)
        self.emo = emo
        self.seed = seed
        self.a_cfg = a_cfg
        self.e_cfg = e_cfg
        self.no_crop = no_crop
        self._agent = None

    def _load_model(self):
        if self._agent is not None:
            return
        logger.info("Loading FLOAT model...")
        sys.path.insert(0, self.float_dir)
        from generate import InferenceAgent, InferenceOptions

        parser = argparse.ArgumentParser(add_help=False)
        opt = InferenceOptions().initialize(parser).parse_args([])
        opt.ref_path = self.ref_image
        opt.aud_path = ""
        opt.pretrained_dir = os.path.join(self.float_dir, "checkpoints")
        opt.ckpt_path = self.ckpt_path
        opt.wav2vec_model_path = os.path.join(
            self.float_dir, "checkpoints", "wav2vec2-base-960h"
        )
        emotion_dir = os.path.join(
            self.float_dir,
            "checkpoints",
            "wav2vec-english-speech-emotion-recognition-safe",
        )
        if not os.path.isdir(emotion_dir):
            emotion_dir = os.path.join(
                self.float_dir,
                "checkpoints",
                "wav2vec-english-speech-emotion-recognition",
            )
        opt.audio2emotion_path = emotion_dir
        opt.fps = int(round(opt.fps))
        opt.emo = self.emo
        opt.seed = self.seed
        opt.a_cfg_scale = self.a_cfg
        opt.e_cfg_scale = self.e_cfg
        opt.no_crop = self.no_crop
        opt.rank = self.device
        opt.ngpus = 1

        opt.device = self.device
        self._agent = InferenceAgent(opt)
        logger.info("FLOAT model loaded on %s.", self.device)

    def run(
        self,
        task_id: str,
        timeline_json: str,
        ref_image: str = None,
        start_page: int = None,
        end_page: int = None,
    ) -> dict:
        logger.info(f"=== AvatarAgent START: task={task_id} ===")

        ref = ref_image or self.ref_image
        if not os.path.exists(ref):
            raise FileNotFoundError(f"Reference image not found: {ref}")

        with open(timeline_json, "r", encoding="utf-8") as f:
            timeline = json.load(f)

        pages = timeline.get("pages", [])
        if not pages:
            return {"error": "No pages in timeline"}

        if start_page is not None:
            pages = [p for p in pages if p["page_id"] >= start_page]
        if end_page is not None:
            pages = [p for p in pages if p["page_id"] <= end_page]

        output_dir = os.path.join(self.workspace_root, task_id, "s4_output", "avatars")
        os.makedirs(output_dir, exist_ok=True)

        self._load_model()

        results = []
        for page in pages:
            page_id = page["page_id"]
            wav_path = page["wav_path"]
            out_video = os.path.join(output_dir, f"page_{page_id:03d}.mp4")

            if not os.path.exists(wav_path):
                logger.warning(f"Page {page_id}: wav not found {wav_path}")
                results.append({"page_id": page_id, "video_path": None, "status": "wav_missing"})
                continue

            logger.info(f"Page {page_id}: generating avatar...")
            t0 = time.time()

            try:
                with accelerator_context(self.device):
                    self._agent.run_inference(
                        res_video_path=out_video,
                        ref_path=ref,
                        audio_path=wav_path,
                        a_cfg_scale=self.a_cfg,
                        e_cfg_scale=self.e_cfg,
                        emo=self.emo,
                        seed=self.seed,
                        no_crop=self.no_crop,
                    )
                elapsed = time.time() - t0
                logger.info(f"Page {page_id}: done ({elapsed:.1f}s)")
                results.append({
                    "page_id": page_id,
                    "video_path": out_video,
                    "duration": elapsed,
                    "status": "success",
                })
            except Exception as e:
                logger.error(f"Page {page_id}: failed - {e}")
                results.append({"page_id": page_id, "video_path": None, "status": f"error: {e}"})

        success = sum(1 for r in results if r["status"] in ("success", "cached"))
        logger.info(f"=== AvatarAgent DONE: {success}/{len(results)} pages ===")

        return {
            "task_id": task_id,
            "total_pages": len(results),
            "success_pages": success,
            "avatars_dir": output_dir,
            "results": results,
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="S4 Avatar Agent")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--timeline", required=True, help="Path to s3_output/timeline.json")
    parser.add_argument("--ref-image", default=DEFAULT_REF_IMAGE)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--workspace", default=WORKSPACE_ROOT)
    parser.add_argument("--start-page", type=int)
    parser.add_argument("--end-page", type=int)
    args = parser.parse_args()

    agent = AvatarAgent(workspace_root=args.workspace, ref_image=args.ref_image, gpu_id=args.gpu)
    result = agent.run(
        task_id=args.task_id,
        timeline_json=args.timeline,
        start_page=args.start_page,
        end_page=args.end_page,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
