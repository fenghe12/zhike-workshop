from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_LANGUAGES = {
    "zh-CN": "中文",
    "en-US": "英语",
    "ja-JP": "日语",
    "ko-KR": "韩语",
    "de-DE": "德语",
    "fr-FR": "法语",
    "ru-RU": "俄语",
    "es-ES": "西班牙语",
}


@dataclass(frozen=True)
class Settings:
    data_root: Path
    artifact_root: Path
    gateway_url: str
    gateway_model: str
    gateway_token: str
    host: str
    port: int
    source_root: Path | None = None
    workspace_root: Path | None = None
    default_reference_audio: Path | None = None
    default_reference_image: Path | None = None
    gpu_id: int = 0
    auto_execute: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        package_root = Path(__file__).resolve().parents[1]
        source_root = Path(
            os.environ.get(
                "SMARTCOURSE_SOURCE_ROOT",
                "/mnt/smartcourse/models",
            )
        ).expanduser()
        artifact_root = Path(
            os.environ.get(
                "SMARTCOURSE_ARTIFACT_ROOT",
                "/mnt/smartcourse/data",
            )
        ).expanduser()
        asset_candidates = (
            package_root.parent / "assets",
            package_root.parents[1] / "assets",
        )
        assets_root = next(
            (candidate for candidate in asset_candidates if candidate.is_dir()),
            asset_candidates[0],
        )
        return cls(
            data_root=Path(
                os.environ.get("SMARTCOURSE_DATA_ROOT", package_root / "data")
            ).expanduser(),
            artifact_root=artifact_root,
            gateway_url=os.environ.get(
                "SMARTCOURSE_GATEWAY_URL",
                "https://api.kimi.com/coding/v1/chat/completions",
            ),
            gateway_model=os.environ.get("SMARTCOURSE_GATEWAY_MODEL", "k3"),
            gateway_token=os.environ.get(
                "KIMI_API_KEY", os.environ.get("SMARTCOURSE_GW_TOKEN", "")
            ),
            host=os.environ.get("SMARTCOURSE_HOST", "0.0.0.0"),
            port=int(os.environ.get("SMARTCOURSE_PORT", "8080")),
            source_root=source_root,
            workspace_root=Path(
                os.environ.get(
                    "SMARTCOURSE_WORKSPACE_ROOT", artifact_root / "tasks"
                )
            ).expanduser(),
            default_reference_audio=Path(
                os.environ.get(
                    "SMARTCOURSE_DEFAULT_REFERENCE_AUDIO",
                    assets_root / "audio/speaker-reference-10s.wav",
                )
            ).expanduser(),
            default_reference_image=Path(
                os.environ.get(
                    "SMARTCOURSE_DEFAULT_REFERENCE_IMAGE",
                    assets_root / "images/hdtf-reference.jpg",
                )
            ).expanduser(),
            gpu_id=int(os.environ.get("SMARTCOURSE_GPU_ID", "0")),
            auto_execute=os.environ.get("SMARTCOURSE_AUTO_EXECUTE", "0").lower()
            in {"1", "true", "yes"},
        )
