"""Isolated NPU operator checks for the migration issue report."""
from pathlib import Path
import argparse
import json
import os
import warnings

import torch
import torch_npu
import torch.nn.functional as F

parser = argparse.ArgumentParser()
parser.add_argument('operator', choices=['replicate-bf16', 'replicate-equivalent', 'complex-rotation', 'sdpa-backward'])
mode = parser.parse_args().operator
h = Path(os.environ['TRAINING_SESSION'])
torch.npu.set_device(0)
result = {'operator': mode, 'device': torch.npu.get_device_name(0)}
try:
    with warnings.catch_warnings(record=True) as messages:
        warnings.simplefilter('always')
        if mode in ['replicate-bf16', 'replicate-equivalent']:
            x = torch.randn(2, 3, 9, device='npu', dtype=torch.bfloat16, requires_grad=True)
            if mode == 'replicate-bf16':
                out = F.pad(x, (2, 0), mode='replicate')
            else:
                out = torch.cat([x[..., :1].expand(2, 3, 2), x], dim=-1)
                expected = F.pad(x.detach().cpu().float(), (2, 0), mode='replicate').to(torch.bfloat16)
                result['forward_matches_cpu'] = bool(torch.equal(out.detach().cpu(), expected))
            out.float().sum().backward()
            if mode == 'replicate-equivalent':
                expected_grad = torch.ones(2, 3, 9)
                expected_grad[..., 0] = 3
                result['input_gradient_matches_cpu'] = bool(torch.equal(x.grad.cpu().float(), expected_grad))
        elif mode == 'complex-rotation':
            x = torch.randn(2, 4, 8, 2, device='npu', requires_grad=True)
            z = torch.view_as_complex(x)
            out = torch.view_as_real(z * z)
            out.square().sum().backward()
        else:
            q, k, v = [torch.randn(1, 2, 64, 128, device='npu', dtype=torch.bfloat16, requires_grad=True) for _ in range(3)]
            out = F.scaled_dot_product_attention(q, k, v)
            out.float().square().mean().backward()
            result['all_qkv_gradients_finite'] = all(bool(torch.isfinite(t.grad).all().cpu()) for t in [q, k, v])
        torch.npu.synchronize()
        result.update(status='passed', output_device=str(out.device))
        result['fallback_warnings'] = [str(m.message) for m in messages if 'fallback' in str(m.message).lower() or 'fall back' in str(m.message).lower()]
except Exception as error:
    result.update(status='failed', error_type=type(error).__name__, error=str(error).splitlines()[0][:500])
(h / 'outputs' / ('operator-' + mode + '.json')).write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
