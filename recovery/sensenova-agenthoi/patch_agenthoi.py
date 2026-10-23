from pathlib import Path
ROOT=Path('/home/ma-user/work/npu-migration/repos/AgentHOI')
path=ROOT/'diffusers_lite/wan/modules/attention.py'
text=path.read_text()
anchor='    half_dtypes = (torch.float16, torch.bfloat16)'
addition='''    if q.device.type == 'npu':
        if window_size != (-1, -1):
            raise ValueError('This NPU launcher requires full attention.')
        original_dtype = q.dtype
        output = torch.zeros_like(q)
        for index in range(q.shape[0]):
            q_count = int(q_lens[index]) if q_lens is not None else q.shape[1]
            k_count = int(k_lens[index]) if k_lens is not None else k.shape[1]
            query = q[index:index+1, :q_count].transpose(1, 2).to(dtype)
            key = k[index:index+1, :k_count].transpose(1, 2).to(dtype)
            value = v[index:index+1, :k_count].transpose(1, 2).to(dtype)
            if q_scale is not None:
                query = query * q_scale
            attended = torch.nn.functional.scaled_dot_product_attention(
                query, key, value, dropout_p=dropout_p,
                is_causal=causal, scale=softmax_scale)
            output[index:index+1, :q_count] = attended.transpose(1, 2).to(original_dtype)
        return output

'''
if addition not in text:
    assert anchor in text;text=text.replace(anchor,addition+anchor,1);path.write_text(text)
path=ROOT/'diffusers_lite/agent/agent_refiner.py';text=path.read_text()
text=text.replace('use_flash_attn=True,','use_flash_attn=False,')
text=text.replace("'54GiB'", "'48GiB'")
anchor='        self.model = AutoModel.from_pretrained('
addition="        if device_map == 'auto' and torch.cuda.device_count() == 1:\n            device_map = 'balanced'\n\n"
if addition not in text:
    assert anchor in text;text=text.replace(anchor,addition+anchor,1)
anchor='            device_map=device_map,\n'
replacement='''            device_map=device_map,
            max_memory={0: '48GiB', 'cpu': '120GiB'} if torch.cuda.device_count() == 1 else None,
'''
if replacement not in text:
    assert anchor in text;text=text.replace(anchor,replacement,1)
anchor='        self.tokenizer = AutoTokenizer.from_pretrained('
addition="        if torch.cuda.device_count() == 1:\n            self.model.language_model.config._attn_implementation = 'sdpa'\n\n"
if addition not in text:
    assert anchor in text;text=text.replace(anchor,addition+anchor,1)
path.write_text(text)
path=ROOT/'diffusers_lite/wan/modules/model.py';text=path.read_text()
helper='''def _npu_rope_apply(x, grid_sizes, freqs):
    # Use real arithmetic for the same rotary product on devices without complex kernels.
    sequence, heads, channels = x.size(1), x.size(2), x.size(3) // 2
    frequency_parts = freqs.cpu().split([channels - 2 * (channels // 3), channels // 3, channels // 3], dim=1)
    outputs = []
    for index, (frames, height, width) in enumerate(grid_sizes.tolist()):
        count = frames * height * width
        frequency = torch.cat([
            frequency_parts[0][:frames].view(frames, 1, 1, -1).expand(frames, height, width, -1),
            frequency_parts[1][:height].view(1, height, 1, -1).expand(frames, height, width, -1),
            frequency_parts[2][:width].view(1, 1, width, -1).expand(frames, height, width, -1),
        ], dim=-1).reshape(count, 1, -1)
        cosine = frequency.real.to(device=x.device, dtype=torch.float32)
        sine = frequency.imag.to(device=x.device, dtype=torch.float32)
        pairs = x[index, :count].float().reshape(count, heads, -1, 2)
        real, imaginary = pairs[..., 0], pairs[..., 1]
        rotated = torch.stack([real * cosine - imaginary * sine, real * sine + imaginary * cosine], dim=-1).flatten(2)
        outputs.append(torch.cat([rotated, x[index, count:].float()]))
    return torch.stack(outputs)


'''
anchor='@amp.autocast(enabled=False)\ndef rope_apply(x, grid_sizes, freqs):'
if helper not in text:
    assert anchor in text;text=text.replace(anchor,helper+anchor,1)
branch="\n    if x.device.type == 'npu':\n        return _npu_rope_apply(x, grid_sizes, freqs)\n"
anchor='def rope_apply(x, grid_sizes, freqs):'
if branch not in text:text=text.replace(anchor,anchor+branch,1)
text=text.replace('if self.freqs.device != device:', "if self.freqs.device != device and device.type != 'npu':")
text=text.replace('if self.freqs_t2m.device != device:', "if self.freqs_t2m.device != device and device.type != 'npu':")
path.write_text(text)
path=ROOT/'diffusers_lite/datasets/image2video_dataset.py';text=path.read_text()
if 'except ImportError:\n    VideoReader = None' not in text:
    text=text.replace('from decord import VideoReader','try:\n    from decord import VideoReader\nexcept ImportError:\n    VideoReader = None')
training_imports='''from .data_utils.sparsify_dwpose import get_sparse_pose_of_interest, get_full_pose_of_interest
from .data_utils.visualize_hoi_sam2_json_bboxtracking import (
    parse_sam2_json,
    add_bbox_tracking_to_poses,
    generate_object_mask_video,
)
from .data_utils.visualize_hoi_sam2_json_v2 import (get_masked_object, get_mask_from_rle)
'''
if '        # Training-only video and pose readers.' not in text:
    for line in training_imports.splitlines(keepends=True):
        if line.strip() not in {'from .data_utils.sparsify_dwpose import get_sparse_pose_of_interest, get_full_pose_of_interest'}:continue
        text=text.replace(line,'',1)
    multiline=training_imports.split('\n',1)[1]
    assert multiline in text;text=text.replace(multiline,'',1)
    anchor='    def get_batch_hoi(self, idx):\n'
    imports='        # Training-only video and pose readers.\n'+''.join('        '+line if line.strip() else line for line in training_imports.splitlines(keepends=True))
    assert anchor in text;text=text.replace(anchor,anchor+imports,1)
path.write_text(text)
print('AgentHOI NPU attention, single-device VLM offload and image-input imports configured.',flush=True)
