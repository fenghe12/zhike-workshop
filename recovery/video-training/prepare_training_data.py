"""AscendBridge CPT data preparation adapted to the original video models."""
import argparse
import gc
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch
import torch_npu
import torch_npu.contrib.transfer_to_npu
from PIL import Image

H = Path(os.environ['TRAINING_SESSION'])
R = H.parents[1]
BRIDGE = H / 'source/SLAI-AscendBridge2'
SOURCE_VIDEO = R / 'repos/Wan2.2/examples/wan_animate/animate/video.mp4'
CAPTION = 'A person moving and dancing in an indoor scene.'
DEVICE = 'npu:0'
torch.npu.set_device(0)
torch.manual_seed(42)
sys.path.insert(0, str(H / 'source/EasyAnimate'))
sys.path.insert(0, str(R / 'repos/Wan2.2'))
current_stage = 'initializing'
started = time.time()


def status(stage):
    global current_stage
    current_stage = stage
    print(json.dumps({'stage': stage, 'elapsed_seconds': round(time.time() - started)}), flush=True)


def release(*models):
    for model in models:
        if hasattr(model, 'to'):
            model.to('cpu')
    gc.collect()
    torch.npu.empty_cache()


def read_video(start, count=16, size=256):
    command = [str(R / 'toolchains/ffmpeg/bin/ffmpeg'), '-v', 'error', '-ss', str(start),
               '-i', str(SOURCE_VIDEO), '-vf', f'fps=16,scale={size}:{size}',
               '-frames:v', str(count), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    result = subprocess.run(command, capture_output=True, check=True)
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, size, size, 3).copy()
    assert len(frames) == count
    pixels = torch.from_numpy(frames).permute(3, 0, 1, 2).float() / 127.5 - 1
    return frames, pixels


def easyanimate(work):
    from easyanimate.models import AutoencoderKLMagvit
    from transformers import T5EncoderModel, T5Tokenizer, CLIPImageProcessor, CLIPVisionModelWithProjection
    model_dir = H / 'models/EasyAnimateV3-XL-2-InP-512x512'
    samples = []
    status('EasyAnimate V3: encoding real video and inpainting conditions')
    vae = AutoencoderKLMagvit.from_pretrained(str(model_dir), subfolder='vae', torch_dtype=torch.float32)
    vae = vae.to(DEVICE).eval().requires_grad_(False)
    for index, offset in enumerate([0.0, 1.15, 2.3]):
        frames, pixels = read_video(offset)
        pixels = pixels.unsqueeze(0).to(DEVICE)
        mask = torch.ones_like(pixels[:, :1])
        mask[:, :, :1] = 0
        masked_pixels = pixels * (1 - mask)
        with torch.no_grad(), torch.autocast('npu', dtype=torch.bfloat16):
            latent = vae.encode(pixels).latent_dist.sample() * vae.config.scaling_factor
            mask_latent = vae.encode(mask.repeat(1, 3, 1, 1, 1)).latent_dist.sample()
            image_latent = vae.encode(masked_pixels).latent_dist.sample()
            inpaint = torch.cat([mask_latent, image_latent], dim=1) * vae.config.scaling_factor
        samples.append({'latents': latent.cpu(), 'inpaint_latents': inpaint.cpu(),
                        'frame': frames[0], 'split': 'train' if index < 2 else 'held_out',
                        'source_offset_seconds': offset})
        status(f'EasyAnimate V3: VAE sample {index + 1}/3')
    del vae
    gc.collect(); torch.npu.empty_cache()
    status('EasyAnimate V3: encoding captions with existing T5-XXL')
    shared_text = R / 'checkpoints/latte/Latte-1/text_encoder'
    token = T5Tokenizer.from_pretrained(str(model_dir / 'tokenizer'))
    encoder = T5EncoderModel.from_pretrained(str(shared_text), torch_dtype=torch.bfloat16).to(DEVICE).eval()
    inputs = token([CAPTION], padding='max_length', max_length=77, truncation=True, return_tensors='pt').to(DEVICE)
    with torch.no_grad():
        embedding = encoder(**inputs).last_hidden_state.cpu()
    mask = inputs.attention_mask.cpu()
    del encoder, inputs
    gc.collect(); torch.npu.empty_cache()
    status('EasyAnimate V3: encoding reference images')
    image_processor = CLIPImageProcessor.from_pretrained(str(model_dir / 'image_encoder'))
    encoder = CLIPVisionModelWithProjection.from_pretrained(str(model_dir / 'image_encoder'), torch_dtype=torch.float32).to(DEVICE).eval()
    for sample in samples:
        inputs = image_processor(images=Image.fromarray(sample.pop('frame')), return_tensors='pt').to(DEVICE)
        with torch.no_grad(), torch.autocast('npu', dtype=torch.bfloat16):
            sample['clip_embeds'] = encoder(**inputs).image_embeds.cpu()
        sample.update(embeddings=embedding, text_mask=mask, clip_mask=torch.ones(1, 8))
    torch.save({'samples': samples, 'caption': CAPTION, 'source': str(SOURCE_VIDEO),
                'video_shape': [16, 256, 256], 'text_encoder_source': str(shared_text),
                'text_encoder_note': 'Reused existing T5-XXL with matching official architecture; not a newly downloaded duplicate.',
                'paradigm': 'original EasyAnimate V3 sigma diffusion with learned variance'}, work / 'outputs/video_latents.pt')
    del encoder
    status('EasyAnimate V3 data preparation complete')


def wan(work):
    from wan.modules.vae2_1 import Wan2_1_VAE
    from wan.modules.t5 import T5EncoderModel
    from wan.modules.s2v.audio_encoder import AudioEncoder
    model_dir = R / 'checkpoints/wan2.2-s2v-14b'
    samples = []
    status('Wan S2V: encoding target, reference and motion history')
    vae = Wan2_1_VAE(vae_pth=str(model_dir / 'Wan2.1_VAE.pth'), dtype=torch.bfloat16, device=DEVICE)
    for index, offset in enumerate([0.0, 1.15, 2.3]):
        _, pixels = read_video(offset)
        pixels = pixels.to(DEVICE)
        reference = pixels[:, :1]
        history = reference.repeat(1, 73, 1, 1)
        with torch.no_grad():
            all_latent = vae.encode([torch.cat([history, pixels], dim=1)])[0]
            ref_latent = vae.encode([reference])[0]
        assert all_latent.shape[1] == 23
        samples.append({'latents': all_latent[:, 19:].cpu(), 'motion_latents': all_latent[:, :19].cpu(),
                        'ref_latents': ref_latent.cpu(), 'source_offset_seconds': offset,
                        'split': 'train' if index < 2 else 'held_out'})
        status(f'Wan S2V: VAE sample {index + 1}/3')
    del vae
    gc.collect(); torch.npu.empty_cache()
    status('Wan S2V: encoding real text conditions')
    encoder = T5EncoderModel(text_len=512, dtype=torch.bfloat16, device=torch.device(DEVICE),
                            checkpoint_path=str(model_dir / 'models_t5_umt5-xxl-enc-bf16.pth'),
                            tokenizer_path=str(model_dir / 'google/umt5-xxl'))
    with torch.no_grad():
        embedding = encoder([CAPTION], torch.device(DEVICE))[0].cpu()
    del encoder
    gc.collect(); torch.npu.empty_cache()
    status('Wan S2V: encoding matching audio tracks')
    encoder = AudioEncoder(device=DEVICE, model_id=str(model_dir / 'wav2vec2-large-xlsr-53-english'))
    for index, sample in enumerate(samples):
        audio_path = work / f'outputs/sample-{index}.wav'
        subprocess.run([str(R / 'toolchains/ffmpeg/bin/ffmpeg'), '-v', 'error', '-y',
                        '-ss', str(sample['source_offset_seconds']), '-i', str(SOURCE_VIDEO),
                        '-t', '1', '-vn', '-ar', '16000', '-ac', '1', str(audio_path)], check=True)
        with torch.no_grad():
            feature = encoder.extract_audio_feat(str(audio_path), return_all_layers=True)
            bucket, _ = encoder.get_audio_embed_bucket_fps(feature, fps=16, batch_frames=16, m=0)
        sample['audio_input'] = bucket[:16].unsqueeze(0).permute(0, 2, 3, 1).cpu()
        sample['embeddings'] = embedding
        sample['cond_states'] = torch.zeros_like(sample['latents'])
    torch.save({'samples': samples, 'source': str(SOURCE_VIDEO), 'caption': CAPTION,
                'video_shape': [16, 256, 256], 'motion_history_note': '73 reference-frame repetitions provide a static initial history; full frame-packing path retained.',
                'paradigm': 'flow matching, all native S2V conditions retained'}, work / 'outputs/video_latents.pt')
    status('Wan S2V data preparation complete')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('model', choices=['ea', 'wan']); args = parser.parse_args()
    work = BRIDGE / 'training-ws' / ('EasyAnimateV3-cpt' if args.model == 'ea' else 'Wan2.2-S2V-cpt')
    (work / 'outputs').mkdir(parents=True, exist_ok=True); (work / 'logs').mkdir(exist_ok=True)
    def heartbeat():
        while True:
            time.sleep(30)
            print(json.dumps({'stage': current_stage, 'elapsed_seconds': round(time.time() - started)}), flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    (easyanimate if args.model == 'ea' else wan)(work)
