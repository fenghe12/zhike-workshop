"""Keep linear weights in the same BF16 dtype used by official AMP inference on NPU."""
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);args=p.parse_args()
path=Path(args.repo)/'diffusers_lite/wan/image2video.py';text=path.read_text()
anchor='        self.model = transformer\n'
addition='''        if hasattr(torch, 'npu') and torch.npu.is_available():
            # AMP uses BF16 for these linear operators. Keep small FP32 time,
            # normalization, modulation and output-head parameters unchanged.
            for module in transformer.blocks.modules():
                if isinstance(module, torch.nn.Linear):
                    module.to(dtype=self.param_dtype)
            dtype_parameters = {}
            for parameter in transformer.parameters():
                key = str(parameter.dtype)
                dtype_parameters[key] = dtype_parameters.get(key, 0) + parameter.numel()
            logging.info(f"NPU video parameter dtypes: {dtype_parameters}")
            logging.info(f"Video checkpoint missing keys: {m}; unexpected keys: {u}")

'''
if addition not in text:
 assert anchor in text;text=text.replace(anchor,addition+anchor,1)
compile(text,str(path),'exec');path.write_text(text)
print('NPU block linear storage now matches BF16 AMP; FP32 time, normalization and output modules retained',flush=True)
