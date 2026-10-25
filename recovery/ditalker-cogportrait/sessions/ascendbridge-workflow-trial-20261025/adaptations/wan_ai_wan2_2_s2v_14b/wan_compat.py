"""Local NPU compatibility only: original full S2V model and all weights retained."""
import numpy as np
import torch
import torch.nn.functional as F
DEVICE = None

def real_rope_apply(x, grid_sizes, freqs, start=None):
    pairs = x.float().unflatten(-1, (-1, 2))
    coefficient = freqs.to(device=x.device, dtype=torch.float32)
    real = pairs[..., 0] * coefficient[..., 0] - pairs[..., 1] * coefficient[..., 1]
    imag = pairs[..., 0] * coefficient[..., 1] + pairs[..., 1] * coefficient[..., 0]
    return torch.stack((real, imag), dim=-1).flatten(-2)


def real_rope_precompute(x, grid_sizes, freqs, start=None):
    assert not isinstance(freqs, list), 'Trainable rotary positions require a separate adapter'
    assert freqs.device.type == 'cpu', 'Constant rotary table must remain on CPU'
    half = x.shape[-1] // 2
    frequencies = freqs.split([half - 2 * (half // 3), half // 3, half // 3], dim=1)
    batches = []
    for index in range(x.shape[0]):
        segments = []
        for group in grid_sizes:
            origin = group[0][index].tolist() if start is None else start[index].tolist()
            end = group[1][index].tolist()
            target = group[2][index].tolist()
            sizes = [int(b - a) for a, b in zip(origin, end)]
            if np.prod(sizes) <= 0:
                continue
            assert target[0] > 0
            coordinates = []
            for axis, (offset, length, scale) in enumerate(zip(origin, sizes, target)):
                if axis == 0 and offset < 0:
                    values = np.linspace(-offset, -scale - offset + 1, length)
                else:
                    values = np.linspace(offset, scale + offset - 1, length)
                coordinates.append(values.astype(int).tolist())
            temporal = frequencies[0][coordinates[0]]
            if origin[0] < 0:
                temporal = temporal.conj().resolve_conj()
            temporal = temporal.reshape(sizes[0], 1, 1, -1).expand(*sizes, -1)
            height = frequencies[1][coordinates[1]].reshape(1, sizes[1], 1, -1).expand(*sizes, -1)
            width = frequencies[2][coordinates[2]].reshape(1, 1, sizes[2], -1).expand(*sizes, -1)
            values = torch.cat([temporal, height, width], dim=-1).reshape(-1, 1, half)
            segments.append(torch.view_as_real(values).float())
        values = torch.cat(segments, dim=0)
        assert values.shape[0] == x.shape[1]
        batches.append(values)
    return torch.stack(batches).to(x.device)


def npu_attention(q, k, v, q_lens=None, k_lens=None, dropout_p=0.0,
                  softmax_scale=None, q_scale=None, causal=False, window_size=(-1, -1),
                  deterministic=False, dtype=torch.bfloat16, version=None):
    assert window_size == (-1, -1), 'Sliding window requires an explicit mask'
    query = q.transpose(1, 2).to(dtype)
    key = k.transpose(1, 2).to(dtype)
    value = v.transpose(1, 2).to(dtype)
    if q_scale is not None:
        query = query * q_scale
    mask = None
    if k_lens is not None:
        lengths_list = k_lens.detach().cpu().tolist()
        if any(length != k.shape[1] for length in lengths_list):
            lengths = k_lens.to(q.device)
            mask = torch.arange(k.shape[1], device=q.device)[None, :] < lengths[:, None]
            # This CANN version requires an explicit query dimension.
            mask = mask[:, None, None, :].expand(-1, 1, q.shape[1], -1).contiguous()
    from runtime import npu_sdpa
    result = npu_sdpa(query, key, value, attn_mask=mask,
                                            dropout_p=dropout_p, is_causal=causal,
                                            scale=softmax_scale)
    return result.transpose(1, 2).to(q.dtype)


def sinusoidal_embedding(dim, position):
    half = dim // 2
    frequency = torch.pow(10000.0, -torch.arange(half, device=position.device).float() / half)
    phase = torch.outer(position.float(), frequency)
    return torch.cat([torch.cos(phase), torch.sin(phase)], dim=-1)


def install_adapters(device):
    global DEVICE
    DEVICE = device
    import wan.modules.attention as attention
    import wan.modules.model as base
    import wan.modules.s2v.model_s2v as s2v
    import wan.modules.s2v.motioner as motioner
    import wan.modules.s2v.s2v_utils as utilities
    import wan.modules.s2v.auxi_blocks as auxiliary
    original = s2v.rope_apply
    cpu_x = torch.randn(1, 7, 2, 16, requires_grad=True)
    phase = torch.randn(1, 7, 2, 8)
    complex_frequency = torch.polar(torch.ones_like(phase), phase)
    cpu_out = original(cpu_x, None, complex_frequency)
    cpu_grad = torch.autograd.grad(cpu_out.square().sum(), cpu_x)[0]
    npu_x = cpu_x.detach().to(DEVICE).requires_grad_(True)
    npu_out = real_rope_apply(npu_x, None, torch.view_as_real(complex_frequency).to(DEVICE))
    npu_grad = torch.autograd.grad(npu_out.square().sum(), npu_x)[0]
    differences = {'forward_max_abs': float((npu_out.cpu() - cpu_out).abs().max()),
                   'input_gradient_max_abs': float((npu_grad.cpu() - cpu_grad).abs().max())}
    assert max(differences.values()) < 1e-5
    for module in [attention, base, s2v, motioner]:
        module.flash_attention = npu_attention
    s2v.rope_apply = real_rope_apply
    for module in [s2v, motioner, utilities]:
        module.rope_precompute = real_rope_precompute
    s2v.sinusoidal_embedding_1d = sinusoidal_embedding
    def causal_convolution(module, x):
        left, right = module.time_causal_padding
        if module.pad_mode == 'replicate' and x.device.type == 'npu':
            pieces = []
            if left:
                pieces.append(x[..., :1].expand(*x.shape[:-1], left))
            pieces.append(x)
            if right:
                pieces.append(x[..., -1:].expand(*x.shape[:-1], right))
            padded = torch.cat(pieces, dim=-1)
        else:
            padded = F.pad(x, module.time_causal_padding, mode=module.pad_mode)
        return module.conv(padded)
    auxiliary.CausalConv1d.forward = causal_convolution
    return differences


