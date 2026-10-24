"""Read checkpoint structure and one updated tensor through private OBS ranges."""
import argparse
import io
import json
import os
from pathlib import Path

import requests
import torch
from torch._subclasses.fake_tensor import FakeTensorMode


class PrivateReader(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.downloaded = 0
        self.session = requests.Session()

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.position
        size = min(size, self.size - self.position)
        if size == 0:
            return b''
        if size > 16 * 1024 * 1024:
            raise RuntimeError('Metadata inspection requested an oversized range')
        start = self.position
        response = self.session.get(self.url, headers={'Range': f'bytes={start}-{start + size - 1}'}, timeout=30)
        if response.status_code != 206 or len(response.content) != size:
            raise RuntimeError('Private checkpoint range read failed')
        self.position += size
        self.downloaded += size
        return response.content

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


def main(model, work_name=None):
    h = Path(os.environ['TRAINING_SESSION'])
    work = h / 'source/SLAI-AscendBridge2/training-ws' / (work_name or ('EasyAnimateV3-cpt' if model == 'easyanimatev3' else 'Wan2.2-S2V-cpt'))
    plan = json.loads((h / (model + '-checkpoint.private.json')).read_text())
    backup = json.loads((work / 'outputs/checkpoint-backup.json').read_text())
    reader = PrivateReader(plan['read_url'], backup['bytes'])
    with FakeTensorMode():
        saved = torch.load(reader, map_location='cpu', weights_only=False)
    result = {'step': saved['step'], 'model_tensors': len(saved['model']),
              'optimizer_states': len(saved['optimizer']['state']),
              'model_parameter_count': saved['configuration']['parameter_count'],
              'model_state_elements': sum(value.numel() for value in saved['model'].values()),
              'metadata_downloaded_bytes': reader.downloaded, 'checkpoint_structure_readable': True}
    name = 'transformer_blocks.0.attn1.to_q.weight' if model == 'easyanimatev3' else 'blocks.0.self_attn.q.weight'
    value = saved['model'][name]
    offset = getattr(value.untyped_storage(), '_checkpoint_offset', None)
    if offset is not None:
        reader.seek(offset + value.storage_offset() * value.element_size())
        recovered = torch.frombuffer(bytearray(reader.read(4096 * value.element_size())), dtype=value.dtype)
        result.update(sample_tensor=name, recovered_tensor_elements=4096,
                      recovered_tensor_finite=bool(torch.isfinite(recovered).all()))
        if model == 'easyanimatev3':
            from safetensors import safe_open
            with safe_open(h / 'models/EasyAnimateV3-XL-2-InP-512x512/transformer/diffusion_pytorch_model.safetensors', framework='pt', device='cpu') as original:
                before = original.get_tensor(name).flatten()[:4096]
            result['recovered_parameter_max_change'] = float((recovered.float() - before.float()).abs().max())
        else:
            from safetensors import safe_open
            root = h.parents[1] / 'checkpoints/wan2.2-s2v-14b'
            index = json.loads((root / 'diffusion_pytorch_model.safetensors.index.json').read_text())
            with safe_open(root / index['weight_map'][name], framework='pt', device='cpu') as original:
                before = original.get_tensor(name).to(value.dtype).flatten()[:4096]
            result['recovered_parameter_max_change'] = float((recovered.float() - before.float()).abs().max())
    (work / 'outputs/checkpoint-inspection.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('model'); parser.add_argument('--work-name')
    args = parser.parse_args(); main(args.model, args.work_name)
