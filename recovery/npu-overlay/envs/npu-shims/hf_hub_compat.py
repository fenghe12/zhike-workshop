# -*- coding: utf-8 -*-
"""huggingface_hub 兼容 shim：为旧版 diffusers(0.24) 补回被删的 cached_download 等 API。

新版 huggingface_hub (>=0.26) 移除了 cached_download / hf_hub_download 旧签名，
diffusers 0.24 的 dynamic_modules_utils 仍引用它。本模块在 import 时把旧 API
以新实现桥接回去，仅在 npu-migration 的 PYTHONPATH 中生效。
"""
import os

try:
    import huggingface_hub as _hub
except Exception:  # noqa: BLE001
    _hub = None

if _hub is not None and not hasattr(_hub, "cached_download"):
    import warnings

    def cached_download(url, library_name=None, library_version=None, legacy_cache_dir=None,
                        user_agent=None, force_download=False, force_filename=None,
                        proxies=None, etag_timeout=10, resume_download=False,
                        use_auth_token=None, local_files_only=False, cache_dir=None):
        """桥接旧 cached_download 到 hf_hub_download。"""
        from huggingface_hub import hf_hub_download

        cache_dir = cache_dir or legacy_cache_dir or os.path.expanduser(
            os.getenv("HF_HOME", os.path.join(os.getenv("XDG_CACHE_HOME", "~/.cache"), "huggingface")))
        import hashlib
        repo_id = "repo_" + hashlib.sha1(url.encode()).hexdigest()[:12]
        filename = force_filename or os.path.basename(url.split("?")[0])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                return hf_hub_download(repo_id=repo_id, filename=filename,
                                       cache_dir=cache_dir, force_download=force_download,
                                       local_files_only=local_files_only)
            except Exception:
                # 离线场景：直接按 URL 语义回源下载到缓存
                import urllib.request
                os.makedirs(cache_dir, exist_ok=True)
                dst = os.path.join(cache_dir, filename)
                if not (os.path.exists(dst) and not force_download):
                    tmp = dst + ".part"
                    urllib.request.urlretrieve(url, tmp)
                    os.replace(tmp, dst)
                return dst

    _hub.cached_download = cached_download

    # 旧版 diffusers 还会引用这些符号
    if not hasattr(_hub, "HfFolder"):
        class HfFolder:  # noqa: D401
            @staticmethod
            def get_token():
                return os.getenv("HF_TOKEN")

            @staticmethod
            def save(token):
                os.environ["HF_TOKEN"] = token

        _hub.HfFolder = HfFolder
    if not hasattr(_hub, "Repository"):
        class Repository:  # noqa: D101
            def __init__(self, *a, **k):
                raise NotImplementedError("Repository 已废弃，本环境不支持")

        _hub.Repository = Repository
