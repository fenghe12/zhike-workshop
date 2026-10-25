"""Real pretrained EasyAnimate V3 complete-backbone adaptation.

All modes execute original full depth with real weights and genuine 512x512 HDTF
VAE/text/image conditions. This is a latent forward test, not video generation.
"""
import argparse
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path
import torch
from runtime import CACHE_DIR, DATA, OLD, REPAIRED, prepare_paths, select_device, synchronize, sample_identifier, sample_ids, tensor_summary

MODEL_ID = 'alibaba-pai/EasyAnimateV3-XL-2-InP-512x512'


def load_model(device):
    prepare_paths()
    sys.path.insert(0, str(OLD / 'source/EasyAnimate'))
    from easyanimate.models import Transformer3DModel
    from safetensors.torch import load_file
    path = OLD / 'models/EasyAnimateV3-XL-2-InP-512x512/transformer'
    model = Transformer3DModel.from_config(json.loads((path / 'config.json').read_text()))
    state = load_file(str(path / 'diffusion_pytorch_model.safetensors'))
    loading = model.load_state_dict(state, strict=True)
    assert not loading.missing_keys and not loading.unexpected_keys
    del state
    model.eval().requires_grad_(False)
    model.to(device)
    model.bridge_device = device
    model.bridge_loading = dict(missing_keys=0, unexpected_keys=0, source='Original EasyAnimate Transformer3DModel', weight_path=str(path), layers=len(model.transformer_blocks), parameter_count=sum(p.numel() for p in model.parameters()), base_only=True, native_inpainting_required=True)
    return model


def load_sample(index=0):
    identifier = sample_identifier(index)
    sample = torch.load(DATA / 'inputs/ditalker' / (identifier + '.pt'), map_location='cpu', weights_only=False)
    replacement = torch.load(REPAIRED / (identifier + '.pt'), map_location='cpu', weights_only=False)
    assert replacement.get('preprocessing_version') == 'native_mask_unknown_minus_one_v1'
    assert replacement['inpaint_latents'].shape == sample['inpaint_latents'].shape
    sample = {key: sample[key] for key in ('latents', 'embeddings', 'text_mask', 'clip_embeds', 'clip_mask')}
    sample.update(identifier=identifier, inpaint_latents=replacement['inpaint_latents'], preprocessing_version=replacement['preprocessing_version'])
    assert tuple(sample['latents'].shape[-3:]) == (4,64,64)
    return sample


def predict(model, sample, seed=42, timestep=500):
    from easyanimate.utils import gaussian_diffusion as gd
    device = model.bridge_device
    latent = sample['latents'].to(device).float()
    generator = torch.Generator(device='cpu').manual_seed(seed)
    noise = torch.randn(sample['latents'].shape, generator=generator, dtype=torch.float32).to(device)
    # Native linear DDPM schedule; timestep has exactly the same interpretation as training.
    diffusion = gd.GaussianDiffusion(betas=gd.get_named_beta_schedule('linear', 1000), model_mean_type=gd.ModelMeanType.EPSILON, model_var_type=gd.ModelVarType.LEARNED_RANGE, loss_type=gd.LossType.MSE, snr=False, return_startx=False)
    t = torch.tensor([timestep], dtype=torch.long, device=device)
    noisy = diffusion.q_sample(latent, t, noise=noise)
    arguments = dict(timestep=t, encoder_hidden_states=sample['embeddings'].to(device), text_embedding_mask=sample['text_mask'].to(device), added_cond_kwargs={'resolution':None,'aspect_ratio':None}, inpaint_latents=sample['inpaint_latents'].to(device), clip_encoder_hidden_states=sample['clip_embeds'].to(device), clip_attention_mask=sample['clip_mask'].to(device), return_dict=False)
    context = torch.autocast('npu', dtype=torch.bfloat16) if str(device).startswith('npu') else nullcontext()
    with torch.no_grad(), context:
        output = model(noisy, **arguments)[0]
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='One real full-backbone forward; no random or reduced model')
    parser.add_argument('--smoke-test', action='store_true', help='Real weights, preprocessing, NPU forward, output checks')
    parser.add_argument('--use-pretrained', action='store_true', help='Explicit real-weight execution (also the default)')
    parser.add_argument('--cpu', action='store_true', help='Explicit CPU reference; never a silent fallback')
    parser.add_argument('--sample-index', type=int, default=0)
    args = parser.parse_args()
    prepare_paths()
    device = select_device(args.cpu)
    print('[Device]', device, flush=True)
    print('[Scope] Full pretrained backbone latent forward, 512x512 cached HDTF, all layers; not full video pipeline', flush=True)
    start = time.perf_counter(); model = load_model(device); synchronize(device)
    load_seconds = time.perf_counter() - start
    sample = load_sample(args.sample_index)
    start = time.perf_counter(); output = predict(model, sample); synchronize(device)
    result = dict(model_id=MODEL_ID, device=device, use_pretrained=True, mode='dry_run' if args.dry_run else 'smoke_test' if args.smoke_test else 'pretrained', model_loading=model.bridge_loading, load_seconds=load_seconds, forward_seconds=time.perf_counter()-start, sample_id=sample['identifier'], source_resolution=[512,512], rgb_frames=16, latent_forward_only=True, full_video_pipeline=False, output=tensor_summary(output))
    assert result['output']['finite']
    path = Path(__file__).resolve().parent / 'outputs/demo-result.json'
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result), flush=True)
    print('[Success] Real pretrained full-backbone latent forward completed', flush=True)


if __name__ == '__main__':
    main()
