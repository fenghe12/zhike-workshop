"""Execute FLOAT outside the HTTP server process."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path


def run_float_avatar(task_root, runtime_root, code, timeline, reference_image, float_dir, gpu_id, progress_callback=None):
    task_root = Path(task_root)
    runtime_root = Path(runtime_root)
    float_dir = Path(float_dir)
    output_dir = task_root / "s4" / code
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "float-worker.log"
    pages = json.loads(Path(timeline).read_text(encoding="utf-8"))["pages"]
    backend_root = Path(__file__).resolve().parents[1]
    allowed = (
        "PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "CUDA_VISIBLE_DEVICES",
        "SMARTCOURSE_DEVICE", "SMARTCOURSE_SOURCE_ROOT", "XDG_CACHE_HOME", "HF_HOME",
        "HF_HUB_CACHE", "HF_HUB_OFFLINE", "NO_ALBUMENTATIONS_UPDATE",
    )
    worker_env = {key: os.environ[key] for key in allowed if key in os.environ}
    worker_env["PYTHONPATH"] = f"{backend_root}:{backend_root / 'agents'}"
    worker_env["PYTHONUNBUFFERED"] = "1"
    worker_env["NO_ALBUMENTATIONS_UPDATE"] = "1"
    results = []
    for page in pages:
        page_id = int(page["page_id"])
        for attempt in range(1, 4):
            result_path = output_dir / f"float-worker-page-{page_id}-{uuid.uuid4().hex}.json"
            command = [
                sys.executable, "-X", "faulthandler", "-u", "-m", "app.avatar_stage_worker",
                "--task-id", code,
                "--timeline", str(timeline),
                "--reference-image", str(reference_image),
                "--workspace", str(runtime_root),
                "--float-dir", str(float_dir),
                "--checkpoint", str(float_dir / "checkpoints/float.pth"),
                "--gpu-id", str(gpu_id),
                "--page-id", str(page_id),
                "--result", str(result_path),
            ]
            with log_path.open("ab") as log:
                log.write(f"FLOAT page {page_id}, attempt {attempt}\n".encode("utf-8"))
                process = subprocess.run(
                    command, cwd=str(backend_root),
                    env=worker_env, stdout=log, stderr=subprocess.STDOUT,
                    timeout=1800, check=False,
                )
            if process.returncode == 0 and result_path.is_file():
                break
            if process.returncode in {-8, -11} and attempt < 3:
                continue
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
            raise RuntimeError(
                f"FLOAT page {page_id} child exited with code {process.returncode}; "
                f"see {log_path}. Recent output: {' | '.join(tail)}"
            )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("error") or result.get("success_pages") != 1 or result.get("total_pages") != 1:
            raise RuntimeError(f"FLOAT page {page_id} did not complete; see {result_path}")
        results.extend(result["results"])
        if progress_callback:
            progress_callback(len(results), len(pages), page_id)
    return {
        "task_id": code,
        "total_pages": len(pages),
        "success_pages": len(results),
        "avatars_dir": str(runtime_root / code / "s4_output" / "avatars"),
        "results": results,
    }
