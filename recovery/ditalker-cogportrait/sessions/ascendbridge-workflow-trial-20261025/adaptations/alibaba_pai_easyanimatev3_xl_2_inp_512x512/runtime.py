"""Persistent input and attention helpers; no model layers or weights are replaced."""
import json
import math
import os
import tempfile
from pathlib import Path
import torch
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / 'models'
R = Path(os.environ.get('NPU_MIGRATION_ROOT', '/home/ma-user/work/npu-migration'))
OLD = R / 'recovery/easyanimate-wans2v-training-3h-20261024'
DATA = R / 'recovery/ditalker-cogportrait-50hdtf-200steps-20261025'
REPAIRED = R / 'recovery/ditalker-cogportrait-operator-audit-20261025/inputs/di-native-mask'
_original_sdpa = F.scaled_dot_product_attention
attention_calls = 0


def prepare_paths():
    short_tmp = R / 'runtime' / 'b25ea'
    for path in (CACHE_DIR, short_tmp, HERE / 'logs', HERE / 'outputs', HERE / 'torch-cache', HERE / 'compiler-cache'):
        path.mkdir(parents=True, exist_ok=True)
    for name in ('HF_HOME', 'TRANSFORMERS_CACHE', 'HF_HUB_CACHE'):
        os.environ[name] = str(CACHE_DIR)
    for name in ('TMPDIR', 'TEMP', 'TMP'):
        os.environ[name] = str(short_tmp)
    tempfile.tempdir = str(short_tmp)
    os.environ['TORCH_HOME'] = str(HERE / 'torch-cache')
    os.environ['TORCHINDUCTOR_CACHE_DIR'] = str(HERE / 'compiler-cache')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'


def select_device(cpu=False):
    if cpu:
        return 'cpu'
    try:
        import torch_npu
        import torch_npu.contrib.transfer_to_npu
    except ImportError as exc:
        raise RuntimeError('Ascend torch_npu is required; CPU fallback is disabled') from exc
    if not torch.npu.is_available():
        raise RuntimeError('Ascend NPU unavailable; CPU fallback is disabled')
    torch.set_num_threads(8)
    torch.npu.set_device(0)
    torch.backends.mha.set_fastpath_enabled(False)
    F.scaled_dot_product_attention = npu_sdpa
    return 'npu:0'


def synchronize(device):
    if str(device).startswith('npu'):
        torch.npu.synchronize()


def sample_ids():
    rows = json.loads((DATA / 'inputs/training-manifest.json').read_text())
    if len(rows) != 50:
        raise RuntimeError('The real HDTF manifest must contain exactly 50 cases')
    return [row['id'] for row in rows]


def sample_identifier(index):
    identifiers = sample_ids()
    if isinstance(index, str) and index in identifiers:
        return index
    return identifiers[int(index)]


def npu_sdpa(q, k, v, attn_mask=None, dropout_p=0., is_causal=False, scale=None, enable_gqa=False):
    global attention_calls
    if q.device.type != 'npu':
        return _original_sdpa(q, k, v, attn_mask=attn_mask, dropout_p=dropout_p, is_causal=is_causal, scale=scale, enable_gqa=enable_gqa)
    import torch_npu
    dim, vdim = q.shape[-1], v.shape[-1]
    target = math.ceil(max(dim, vdim) / 16) * 16
    if enable_gqa:
        k = k.repeat_interleave(q.shape[1] // k.shape[1], dim=1)
        v = v.repeat_interleave(q.shape[1] // v.shape[1], dim=1)
    mask = attn_mask
    if mask is not None:
        if mask.dtype == torch.bool:
            mask = ~mask
        else:
            if bool((mask > 0).any()):
                raise RuntimeError('Positive additive attention biases require another implementation')
            mask = mask < 0
        if mask.ndim == 2:
            mask = mask[None, None]
        elif mask.ndim == 3:
            mask = mask[:, None]
        if mask.shape[-2] == 1 and q.shape[-2] != 1:
            mask = mask.expand(*mask.shape[:-2], q.shape[-2], mask.shape[-1])
        mask = mask.to(q.device).contiguous()
    if is_causal:
        causal = torch.ones(q.shape[-2], k.shape[-2], device=q.device, dtype=torch.bool).triu(1)
        mask = causal if mask is None else mask | causal
    q = F.pad(q, (0, target-dim)).bfloat16().contiguous()
    k = F.pad(k, (0, target-dim)).bfloat16().contiguous()
    v = F.pad(v, (0, target-vdim)).bfloat16().contiguous()
    out = torch_npu.npu_fusion_attention(q, k, v, head_num=q.shape[1], input_layout='BNSD', atten_mask=mask, scale=scale if scale is not None else dim ** -.5, keep_prob=1-dropout_p)[0]
    attention_calls += 1
    return out[..., :vdim]


def tensor_summary(value):
    value = value.detach().float().cpu()
    return dict(shape=list(value.shape), finite=bool(torch.isfinite(value).all()), mean=float(value.mean()), std=float(value.std()), minimum=float(value.min()), maximum=float(value.max()), selected_values=value.flatten()[::max(1,value.numel()//32)][:32].tolist())
