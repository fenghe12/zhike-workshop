# -*- coding: utf-8 -*-
"""昇腾「零改动」迁移注入器。

放在 PYTHONPATH 首位时，Python 启动会自动加载本模块（sitecustomize 机制），
仅当环境变量 NPU_MIGRATE=1 时生效：
把 torch.cuda.* / Tensor.cuda() / Module.cuda() 全部重定向到 NPU，
从而让原始 GPU 代码仓库不改一行即可在昇腾 910B 上跑。

用法：
  cd <repo> && NPU_MIGRATE=1 PYTHONPATH=<本目录>:<torch_npu目录> python xxx.py
"""
import os
import sys

if os.environ.get("NPU_MIGRATE", "0") == "1":
    try:
        import argparse

        import torch  # noqa: F401
        import torch_npu  # noqa: F401
        import torch_npu.contrib.transfer_to_npu  # noqa: F401  核心：cuda→npu 重定向

        # 老 checkpoint 里常嵌 argparse.Namespace / numpy 标量，
        # torch>=2.6 默认 weights_only=True 会拒绝，这里加白名单
        try:
            import numpy as _np

            torch.serialization.add_safe_globals(
                [argparse.Namespace, _np.core.multiarray._reconstruct]
            )
            for _t in (_np.float64, _np.float32, _np.int64, _np.int32, _np.ndarray):
                torch.serialization.add_safe_globals([_t])
        except Exception:
            pass

        # 迁移场景信任本地权重：恢复 torch.load 默认 weights_only=False
        # （torch 2.6 起默认 True，会拒载含任意 Python 对象的老 checkpoint）
        try:
            _orig_load = torch.load

            def _load_compat(*args, **kwargs):
                kwargs.setdefault("weights_only", False)
                return _orig_load(*args, **kwargs)

            torch.load = _load_compat
        except Exception:
            pass

        # 老 NeRF 代码的 set_default_tensor_type('torch.cuda.FloatTensor')
        # 在 torch 2.x + torch_npu 下不可用，桥接为 set_default_device('npu')
        try:
            _orig_sdtt = torch.set_default_tensor_type

            def _sdtt_compat(t=None):
                if t is None or (isinstance(t, str) and "cuda" in t):
                    torch.npu.set_device(0)
                    torch.set_default_device("npu")
                    return
                return _orig_sdtt(t)

            torch.set_default_tensor_type = _sdtt_compat
        except Exception:
            pass

        _log = os.environ.get("NPU_MIGRATE_LOG")
        if _log:
            with open(_log, "a", encoding="utf-8") as fh:
                fh.write(
                    "[npu-migrate] pid=%s cuda_available=%s devices=%s 已重定向到 NPU\n"
                    % (os.getpid(), torch.cuda.is_available(), torch.cuda.device_count())
                )

        # hf_hub 旧 API shim（供 diffusers 0.24 等老库引用被删的 cached_download）
        try:
            import hf_hub_compat  # noqa: F401
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[npu-migrate] 注入失败: %s\n" % exc)

try:
    import numpy as _np
    for _name, _value in [("float", float), ("int", int), ("bool", bool), ("complex", complex), ("object", object)]:
        if _name not in _np.__dict__: setattr(_np, _name, _value)
except Exception:
    pass
