from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LANGUAGE_ARTIFACTS = {
    "en-US": "pipeline/output/ch01",
    "ja-JP": "pipeline/output_ja/ch01",
    "de-DE": "pipeline/output_de/ch01",
}


@dataclass(frozen=True)
class RestoredPaths:
    root: Path

    @property
    def pipeline(self) -> Path:
        return self.root / "pipeline"

    @property
    def index_tts(self) -> Path:
        return self.root / "index-tts"

    @property
    def float_root(self) -> Path:
        return self.root / "float"

    @property
    def merger(self) -> Path:
        return self.root / "merger"

    @property
    def pptx_translate(self) -> Path:
        return self.root / "pptx-translate"


class RecoveredArtifactProvider:
    def __init__(self, root: Path):
        if root.name != "a800-local-0722":
            raise ValueError("恢复产物根目录必须为 a800-local-0722")
        self.root = root

    def language(self, code: str) -> dict[str, Any]:
        relative = LANGUAGE_ARTIFACTS.get(code)
        if not relative:
            return {"code": code, "status": "language-data-only", "files": {}}
        directory = self.root / relative
        patterns = {
            "translatedStructure": "s2_translated_structure.json",
            "translatedPpt": "*.pptx",
            "timeline": "s3_timeline.json",
            "avatarManifest": "s4_manifest.json",
            "finalVideo": "*final.mp4",
        }
        files = {}
        for key, pattern in patterns.items():
            value = next(iter(sorted(directory.rglob(pattern))), None)
            if value:
                files[key] = str(value)
        return {
            "code": code,
            "status": "completed" if "finalVideo" in files else "partial",
            "files": files,
        }


class LegacyPipelineRunner:
    """在模型依赖可用时调用恢复的 S1—S5 流水线。"""

    def __init__(self, paths: RestoredPaths, python_executable: str = "python3"):
        self.paths = paths
        self.python_executable = python_executable

    def execute(self, config: dict[str, Any], working_directory: Path) -> None:
        working_directory.mkdir(parents=True, exist_ok=True)
        config_path = working_directory / "pipeline-config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        environment = dict(os.environ)
        environment.update(
            {
                "PPTX_TRANSLATE_DIR": str(self.paths.pptx_translate),
                "INDEXTTS_DIR": str(self.paths.index_tts),
                "INDEXTTS_HF_CACHE": str(self.paths.index_tts / "checkpoints/hf_cache"),
                "FLOAT_DIR": str(self.paths.float_root),
                "FLOAT_CHECKPOINTS": str(self.paths.float_root / "checkpoints"),
                "PPT_PNG_BASE": str(self.paths.merger / "new_ppts"),
            }
        )
        subprocess.run(
            [
                self.python_executable,
                str(self.paths.pipeline / "pipeline.py"),
                "--config",
                str(config_path),
            ],
            cwd=str(self.paths.pipeline),
            env=environment,
            check=True,
        )
