from pathlib import Path
import argparse,re
parser=argparse.ArgumentParser();parser.add_argument('--repo',required=True);args=parser.parse_args()
repo=Path(args.repo)
for name in ['run_nerf.py','run_nerf_helpers.py']:
    path=repo/'NeRFs/TorsoNeRF'/name;text=path.read_text()
    text=text.replace("torch.device('cuda', 0)","torch.device('npu', 0)")
    text=text.replace("torch.set_default_tensor_type('torch.cuda.FloatTensor')", "torch.set_default_device('npu:0')")
    text=text.replace('torch.Tensor([1e10], device=z_vals.device)','torch.tensor([1e10], device=z_vals.device, dtype=z_vals.dtype)')
    text=re.sub(r'\bnp\.float\b','np.float64',text)
    text=re.sub(r'\bnp\.int\b','np.int64',text)
    if name=='run_nerf.py':
        anchor="    print('Found ckpts', ckpts)"
        addition="\n    if args.with_test == 1 and not ckpts:\n        raise FileNotFoundError('Official rendering requires both pretrained head and body checkpoints: ' + ext)\n"
        if addition not in text:
            assert anchor in text;text=text.replace(anchor,anchor+addition,1)
        anchor="        start = ckpt['global_step']"
        addition="\n        print('Loaded pretrained component', ext, 'at step', start, flush=True)"
        if addition not in text:
            assert anchor in text;text=text.replace(anchor,anchor+addition,1)
    path.write_text(text)
    compile(text,str(path),'exec')
print('NPU devices, legacy tensor constructor and mandatory pretrained model loading configured.',flush=True)
