"""Real pretrained complete Wan2.2 S2V-14B backbone, without CogPortrait modules."""
import argparse
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path
import numpy as np
import torch
from runtime import CACHE_DIR, DATA, OLD, R, prepare_paths, select_device, synchronize, sample_identifier, sample_ids, tensor_summary
from wan_compat import install_adapters

MODEL_ID = 'Wan-AI/Wan2.2-S2V-14B'


def load_model(device):
    prepare_paths()
    sys.path.insert(0, str(R / 'repos/Wan2.2'))
    from wan.modules.s2v.model_s2v import WanModel_S2V
    path = R / 'checkpoints/wan2.2-s2v-14b'
    model, info = WanModel_S2V.from_pretrained(str(path), torch_dtype=torch.bfloat16, low_cpu_mem_usage=True, output_loading_info=True, local_files_only=True)
    assert not info['missing_keys'] and not info['unexpected_keys']
    assert isinstance(model.cond_encoder, torch.nn.Conv3d), 'Native cond_encoder must remain unchanged'
    model.time_embedding.float(); model.time_projection.float(); model.head.float()
    model.to(device).eval().requires_grad_(False)
    compatibility = install_adapters(device)
    model.bridge_device = device
    model.bridge_loading = dict(missing_keys=0, unexpected_keys=0, source='Original WanModel_S2V', weight_path=str(path), layers=len(model.blocks), parameter_count=sum(p.numel() for p in model.parameters()), base_only=True, native_cond_encoder=True, native_framepack_preserved=model.enable_framepack, native_motioner_preserved=model.enable_motioner, compatibility=compatibility)
    return model


def load_sample(index=0):
    identifier = sample_identifier(index)
    original = torch.load(DATA / 'inputs/cogportrait' / (identifier+'.pt'), map_location='cpu', weights_only=False)
    sample = {key: original[key] for key in ('latents','ref_latents','motion_latents','audio_input','embeddings')}
    # No pose video is supplied to the unmodified base model. Do not use cached CogPortrait pose maps.
    sample['cond_states'] = torch.zeros_like(sample['latents'])
    sample['identifier'] = identifier
    assert tuple(sample['latents'].shape) == (16,4,64,64)
    return sample


def predict(model, sample, seed=42, timestep=500):
    device = model.bridge_device
    sigma = timestep / 1000.0
    latent = sample['latents'].to(device).float()
    generator = torch.Generator(device='cpu').manual_seed(seed)
    noise = torch.randn(sample['latents'].shape, generator=generator, dtype=torch.float32).to(device)
    noisy = ((1-sigma)*latent+sigma*noise).to(torch.bfloat16)
    arguments = dict(t=torch.tensor([float(timestep)],device=device), context=[sample['embeddings'].to(device,dtype=torch.bfloat16)], seq_len=int(np.prod(latent.shape[1:])//4), ref_latents=[sample['ref_latents'].to(device,dtype=torch.bfloat16)], motion_latents=[sample['motion_latents'].to(device,dtype=torch.bfloat16)], cond_states=[sample['cond_states'].to(device,dtype=torch.bfloat16)], audio_input=sample['audio_input'].to(device,dtype=torch.bfloat16), motion_frames=[73,19], drop_motion_frames=False)
    context = torch.autocast('npu',dtype=torch.bfloat16) if str(device).startswith('npu') else nullcontext()
    with torch.no_grad(), context:
        return model([noisy], **arguments)[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',action='store_true',help='One real full-backbone forward; no random or reduced model')
    parser.add_argument('--smoke-test',action='store_true',help='Load real weights and execute full NPU backbone')
    parser.add_argument('--use-pretrained',action='store_true',help='Explicit real-weight execution (also default)')
    parser.add_argument('--cpu',action='store_true',help='Explicit CPU reference, never silent fallback')
    parser.add_argument('--sample-index',type=int,default=0)
    args = parser.parse_args()
    prepare_paths(); device = select_device(args.cpu)
    print('[Device]',device,flush=True)
    print('[Scope] Full pretrained S2V backbone latent forward, 512x512 cached HDTF; not full video pipeline',flush=True)
    start=time.perf_counter(); model=load_model(device); synchronize(device)
    load_seconds=time.perf_counter()-start; sample=load_sample(args.sample_index)
    start=time.perf_counter(); output=predict(model,sample); synchronize(device)
    result=dict(model_id=MODEL_ID,device=device,use_pretrained=True,mode='dry_run' if args.dry_run else 'smoke_test' if args.smoke_test else 'pretrained',model_loading=model.bridge_loading,load_seconds=load_seconds,forward_seconds=time.perf_counter()-start,sample_id=sample['identifier'],source_resolution=[512,512],rgb_frames=16,latent_forward_only=True,full_video_pipeline=False,output=tensor_summary(output))
    assert result['output']['finite']
    (Path(__file__).resolve().parent/'outputs/demo-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    print('[Success] Real pretrained complete S2V backbone latent forward completed',flush=True)


if __name__ == '__main__':
    main()
