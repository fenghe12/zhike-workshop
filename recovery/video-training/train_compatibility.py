"""Bounded real training derived from the AscendBridge diffusion CPT workflow."""
import argparse
import gc
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path

import torch
import torch_npu
import torch_npu.contrib.transfer_to_npu
from safetensors.torch import load_file
from torch.utils.data import DataLoader

from multipart_checkpoint import CheckpointWriter

H = Path(os.environ['TRAINING_SESSION'])
R = H.parents[1]
BRIDGE = H / 'source/SLAI-AscendBridge2'
DEVICE = 'npu:0'
torch.npu.set_device(0)
torch.manual_seed(42)
sys.path.insert(0, str(H / 'source/EasyAnimate'))
sys.path.insert(0, str(R / 'repos/Wan2.2'))
stage = 'initializing'
started = time.time()
work = None
record = {}


def update(value, **extra):
    global stage
    stage = value
    record.update(stage=value, elapsed_seconds=time.time() - started, **extra)
    (work / 'outputs/status.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'stage': value, 'elapsed_seconds': round(time.time() - started), **extra}), flush=True)


def heartbeat():
    while True:
        time.sleep(30)
        print(json.dumps({'stage': stage, 'elapsed_seconds': round(time.time() - started)}), flush=True)


def easy_model():
    from easyanimate.models import Transformer3DModel
    model_dir = H / 'models/EasyAnimateV3-XL-2-InP-512x512/transformer'
    model = Transformer3DModel.from_config(json.loads((model_dir / 'config.json').read_text()))
    state = load_file(str(model_dir / 'diffusion_pytorch_model.safetensors'))
    assert all(bool(torch.isfinite(value).all()) for value in state.values() if value.is_floating_point())
    result = model.load_state_dict(state, strict=True)
    del state
    # This native V3 implementation exposes the original per-model flag.
    # Newer diffusers calls its legacy setter using an incompatible signature.
    model.gradient_checkpointing = True
    model = model.to(DEVICE)
    return model, {'missing_keys': len(result.missing_keys), 'unexpected_keys': len(result.unexpected_keys)}


def easy_loss(model, sample, seed):
    from easyanimate.utils import gaussian_diffusion as gd
    from easyanimate.utils.respace import SpacedDiffusion, space_timesteps
    diffusion = SpacedDiffusion(use_timesteps=space_timesteps(1000, '1000'),
                               betas=gd.get_named_beta_schedule('linear', 1000),
                               model_mean_type=gd.ModelMeanType.EPSILON,
                               model_var_type=gd.ModelVarType.LEARNED_RANGE,
                               loss_type=gd.LossType.MSE, snr=False, return_startx=False)
    torch.manual_seed(seed)
    latent = sample['latents'].to(DEVICE).float()
    timestep = torch.full((1,), 500, dtype=torch.long, device=DEVICE)
    kwargs = dict(encoder_hidden_states=sample['embeddings'].to(DEVICE),
                  text_embedding_mask=sample['text_mask'].to(DEVICE),
                  added_cond_kwargs={'resolution': None, 'aspect_ratio': None},
                  inpaint_latents=sample['inpaint_latents'].to(DEVICE),
                  clip_encoder_hidden_states=sample['clip_embeds'].to(DEVICE),
                  clip_attention_mask=sample['clip_mask'].to(DEVICE), return_dict=False)
    with torch.autocast('npu', dtype=torch.bfloat16):
        losses = diffusion.training_losses(model, latent, timestep, model_kwargs=kwargs,
                                           noise=torch.randn_like(latent))
    return losses['loss'].mean(), {key: float(value.mean().detach().cpu()) for key, value in losses.items()}


def parameter_samples(model):
    selected = {}
    groups = ['patch', 'attn1.to_q', 'attn2.to_q', 'motion_modules', 'motion_module',
              'proj_out', 'self_attn.q', 'audio_injector', 'frame_packer', 'head.head']
    for group in groups:
        for name, parameter in model.named_parameters():
            if group in name and parameter.ndim > 1 and name not in selected:
                selected[name] = parameter
                break
    return selected


def main(args):
    global work
    name = args.run_name or ('EasyAnimateV3-cpt' if args.model == 'ea' else 'Wan2.2-S2V-cpt')
    work = BRIDGE / 'training-ws' / name
    for directory in ['outputs', 'logs']:
        (work / directory).mkdir(parents=True, exist_ok=True)
    record.update(model=name, requested_steps=args.steps, training_device=DEVICE,
                  hardware=torch.npu.get_device_name(0), reduced_test_video_shape=[16, 256, 256],
                  model_structure_preserved=True, training_quality_claim=False)
    threading.Thread(target=heartbeat, daemon=True).start()
    update('loading cached real data')
    data = torch.load(work / 'outputs/video_latents.pt', weights_only=False)
    train_samples = [sample for sample in data['samples'] if sample['split'] == 'train']
    held_out = [sample for sample in data['samples'] if sample['split'] == 'held_out'][0]
    loader = DataLoader(train_samples, batch_size=None, shuffle=False, num_workers=0)
    update('loading full original model')
    if args.model == 'ea':
        model, loading = easy_model()
        loss_function = easy_loss
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate or 1e-5, weight_decay=0.01, foreach=False)
        optimizer_name = 'AdamW, all original backbone parameters'
    else:
        from wan_training_adapter import make_model, loss_function
        model, loading = make_model(work)
        from transformers import Adafactor
        optimizer = Adafactor(model.parameters(), lr=args.learning_rate or 5e-6, relative_step=False, scale_parameter=False,
                              warmup_init=False, beta1=None, weight_decay=0.0)
        optimizer_name = 'Adafactor without first moment, all original S2V parameters'
    assert all(parameter.requires_grad for parameter in model.parameters())
    count = sum(parameter.numel() for parameter in model.parameters())
    record.update(parameter_count=count, loading=loading, optimizer=optimizer_name,
                  train_samples=len(train_samples), held_out_samples=1,
                  learning_rate=optimizer.param_groups[0]['lr'])
    update('fixed held-out baseline')
    model.eval()
    with torch.no_grad():
        baseline, _ = loss_function(model, held_out, 1234)
    torch.npu.synchronize()
    record['held_out_before'] = float(baseline.cpu())
    del baseline
    model.train()
    monitored = parameter_samples(model)
    cached_gradients = {}
    gradient_norms = {}
    handles = []
    if args.model == 'wan':
        def store_gradient(parameter):
            gradient = parameter.grad.detach()
            if parameter in cached_gradients:
                gradient = gradient + cached_gradients[parameter].to(parameter.device)
            gradient_norms[parameter] = gradient.float().norm(2)
            cached_gradients[parameter] = gradient.cpu()
            parameter.grad = None
        handles = [parameter.register_post_accumulate_grad_hook(store_gradient) for parameter in model.parameters()]
        record['gradient_storage'] = 'CPU tensor storage between backward and update; forward, backward, gradient norm and optimizer arithmetic stay on NPU'
    steps = []
    for index in range(args.steps):
        sample = next(iter(loader)) if index % 2 == 0 else train_samples[1]
        optimizer.zero_grad(set_to_none=True)
        torch.npu.reset_peak_memory_stats()
        torch.npu.synchronize()
        t0 = time.perf_counter()
        update('forward', step=index + 1)
        loss, components = loss_function(model, sample, 42 + index)
        torch.npu.synchronize(); forward_seconds = time.perf_counter() - t0
        assert bool(torch.isfinite(loss).cpu())
        update('backward', step=index + 1)
        t1 = time.perf_counter(); loss.backward(); torch.npu.synchronize()
        backward_seconds = time.perf_counter() - t1
        if args.model == 'wan':
            gradients = list(cached_gradients)
            norm = torch.stack(list(gradient_norms.values())).norm(2)
        else:
            gradients = [parameter for parameter in model.parameters() if parameter.grad is not None]
            norm = torch.nn.utils.clip_grad_norm_(gradients, 1.0, foreach=False)
        assert bool(torch.isfinite(norm).cpu()) and float(norm.cpu()) > 0
        before = {name: parameter.detach().flatten()[:4096].cpu().clone() for name, parameter in monitored.items()}
        update('optimizer update', step=index + 1)
        t2 = time.perf_counter()
        if args.model == 'wan':
            # Preserve the complete backward pass before changing any weight.
            # Bring back one gradient at a time for the original NPU optimizer.
            original_groups = optimizer.param_groups
            coefficient = (1.0 / (norm + 1e-6)).clamp(max=1.0)
            try:
                for parameter in gradients:
                    parameter.grad = cached_gradients.pop(parameter).to(parameter.device)
                    parameter.grad.mul_(coefficient.to(parameter.grad.dtype))
                    optimizer.param_groups = [{**original_groups[0], 'params': [parameter]}]
                    optimizer.step()
                    parameter.grad = None
            finally:
                optimizer.param_groups = original_groups
            gradient_norms.clear()
        else:
            optimizer.step()
        torch.npu.synchronize()
        optimizer_seconds = time.perf_counter() - t2
        changes = {name: float((parameter.detach().flatten()[:4096].cpu().float() - before[name].float()).abs().max())
                   for name, parameter in monitored.items()}
        assert any(value > 0 for value in changes.values()), 'No monitored parameter changed'
        item = {'step': index + 1, 'loss': float(loss.detach().cpu()), 'loss_components': components,
                'forward_seconds': forward_seconds, 'backward_seconds': backward_seconds,
                'optimizer_seconds': optimizer_seconds, 'total_seconds': time.perf_counter() - t0,
                'gradient_norm_before_clip': float(norm.cpu()),
                'parameters_with_gradients': sum(parameter.numel() for parameter in gradients),
                'parameter_tensors_with_gradients': len(gradients),
                'sampled_parameter_max_changes': changes,
                'peak_allocated_bytes': torch.npu.max_memory_allocated(),
                'peak_reserved_bytes': torch.npu.max_memory_reserved()}
        steps.append(item)
        with (work / 'logs/step_loss.jsonl').open('a') as stream:
            stream.write(json.dumps(item) + '\n')
        update('step complete', step=index + 1, last_step=item)
        del loss, gradients, norm
    optimizer.zero_grad(set_to_none=True)
    update('fixed held-out evaluation after training')
    model.eval()
    with torch.no_grad():
        after, _ = loss_function(model, held_out, 1234)
    torch.npu.synchronize()
    record['held_out_after'] = float(after.cpu())
    del after
    update('writing full checkpoint directly to private OBS')
    model_state = {key: value.detach().cpu() for key, value in model.state_dict().items()}
    def cpu_value(value):
        if isinstance(value, torch.Tensor):
            return value.detach().cpu()
        if isinstance(value, dict):
            return {key: cpu_value(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return type(value)(cpu_value(item) for item in value)
        return value
    checkpoint = {'model': model_state, 'optimizer': cpu_value(optimizer.state_dict()),
                  'step': args.steps, 'configuration': record, 'rng_state': torch.get_rng_state()}
    key = 'easyanimatev3' if args.model == 'ea' else 'wan22s2v'
    writer = CheckpointWriter(H / (args.checkpoint_plan or key + '-checkpoint.private.json'), work / 'outputs/checkpoint-backup.json')
    torch.save(checkpoint, writer)
    saved = writer.finish()
    update('complete', completed_steps=len(steps), steps=steps, checkpoint=saved,
           forward_backward_optimizer_verified=True)
    (work / 'outputs/train_summary.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('model', choices=['ea', 'wan'])
    parser.add_argument('--steps', type=int, default=3)
    parser.add_argument('--learning-rate', type=float)
    parser.add_argument('--run-name')
    parser.add_argument('--checkpoint-plan')
    args = parser.parse_args()
    try:
        main(args)
    except Exception as error:
        if work is not None:
            update('failed', error_type=type(error).__name__, error=str(error)[:3000])
            (work / 'logs/failure.txt').write_text(traceback.format_exc())
        raise
