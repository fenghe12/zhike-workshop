# EasyAnimate V3 and Wan2.2 S2V training on Ascend

English | [简体中文](README.zh-CN.md)

The October 24, 2026 trial exercised data loading, original-model forward passes, losses, backward passes, and actual parameter updates on one Ascend 910B2 with 64 GB. EasyAnimate V3 completed three AdamW steps; Wan2.2 S2V completed two separate three-step Adafactor trials. See the [measured record](../../docs/training-20261024-video-models.json) for final values and limitations.

This is a small compatibility trial, not a converged reproduction or a training speed benchmark. Each run uses two training clips and one separate clip from the public [Wan Animate example video](https://github.com/Wan-Video/Wan2.2/blob/main/examples/wan_animate/animate/video.mp4). The diagnostic clips contain 16 frames at 256 × 256. Original model layers and conditional branches remain present.

## Models and losses

- [EasyAnimateV3-XL-2-InP-512x512](https://huggingface.co/alibaba-pai/EasyAnimateV3-XL-2-InP-512x512): native `Transformer3DModel`, 1,538,364,704 parameters, original sigma diffusion objective with epsilon MSE and the learned-variance variational term. VAE, inpainting, caption and CLIP reference conditions are cached from real inputs. The existing Latte T5-XXL encoder was reused with the matching architecture; this is explicitly not a newly downloaded, independently verified copy of every original V3 text-encoder file.
- [Wan2.2-S2V-14B](https://huggingface.co/Wan-AI/Wan2.2-S2V-14B): native `WanModel_S2V`, 16,295,755,609 parameters, flow-matching velocity MSE, original audio injector, reference-image path and enabled FramePack path. Motioner stays disabled, matching the released configuration. Initial motion history repeats the reference frame; pose conditioning is absent, matching a no-pose input.

VAE and condition encoders are frozen during preprocessing. All parameters of each loaded video backbone receive gradients. For S2V, gradients are stored on CPU after accumulation and transferred back one at a time for NPU clipping and optimizer arithmetic. No weight changes occur until the complete backward pass finishes. This preserves the full single-device model while reducing device memory use; these times include gradient transfers.

## AscendBridge use and required adaptations

The fetched [AscendBridge source](https://gitcode.com/SLAI/SLAI-AscendBridge2) declares version 2.5 and includes `ascend-torch-cpt`, unlike the older 2.0 PDFs. Its actual board initialization, model registration and source-availability probe were executed. Training follows its diffusion CPT workflow with project-specific adapters. An autonomous multi-agent migration session was not executed.

The generic template cannot be used unchanged: V3's metadata advertises an older PixArt 2D pipeline while the real model is a custom video Transformer; V3 requires its learned-variance objective. Native S2V has a different forward signature and additional conditions. The adapters retain those paths.

Observed adjustments include the legacy V3 gradient-checkpoint setter, NPU BF16 replicate padding implemented with differentiable expansion/concatenation, explicit supported attention-mask shapes, NPU SDPA, and real-valued rotary multiplication. The rotary replacement was compared with the native complex implementation for both output and input gradient. Time/output modules remain FP32 where required; S2V uses BF16 backbone weights. No CUDA-only extension is installed.

Separate small checks passed for NPU complex64 multiplication/backward and SDPA backward. Complex operations as a whole are therefore not classified as missing; the original full FP64 rotary route was not validated end to end.

## Dated persistent layout and execution

The tested persistent root is `/home/ma-user/work/npu-migration`. Restore the archived runtime before using these files. Place them in `recovery/easyanimate-wans2v-training-3h-20261024` under that root. Its `source/` directory contains original `EasyAnimate` and `SLAI-AscendBridge2` snapshots. Existing Wan source and weights live in `repos/Wan2.2` and `checkpoints/wan2.2-s2v-14b`; V3 files live in the session's `models/EasyAnimateV3-XL-2-InP-512x512`.

Use the recorded persistent Torch 2.7.1 / torch_npu 2.7.1 environment and explicit dependency overlays in `run_env.sh`. It sets persistent temporary, cache and log paths through the existing `persistent-npu-env.sh`. Do not synchronize the framework's current dependency list over this working runtime. Verify the data-volume mount, writable paths, available memory, model files and allocated NPU before launch. Execute the following sequentially:

```bash
bash run_env.sh python prepare_training_data.py ea
bash run_env.sh python train_compatibility.py ea --steps 3
bash run_env.sh python prepare_training_data.py wan
bash run_env.sh python train_compatibility.py wan --steps 3 --learning-rate 5e-6
```

Before training, use `prepare_checkpoint_plan.py` on the authorized local client with the OBS Python SDK to create `easyanimatev3-checkpoint.private.json` or `wan22s2v-checkpoint.private.json`, then transfer the private plan into the session directory. It reads `OBS_ACCESS_KEY_ID` and `OBS_SECRET_ACCESS_KEY` from the environment and accepts bucket, endpoint, object and output arguments. Never commit plans or credentials. Model/optimizer checkpoints stream directly into private OBS in 64 MiB parts; object sizes and checkpoint structure are checked separately. This avoids requiring another large local data-volume copy.

Cloud start/stop controls are deliberately separate from model scripts. Apply the authorized usage limit and stop compute after collection. Preserve persistent volumes, original weights and private backups.

Original model code and weights remain subject to their upstream licenses. This folder contains the task-specific training and recovery adapters, not the model weights or private deployment details.

## Session timing

The estimate was 156 minutes; compute was confirmed stopped after 58.36 minutes. Preparation and repair were not individually timed. Model download took 66 seconds; video/condition preprocessing took about 210 seconds; the nine optimizer steps took 88.95 seconds in total; the three checkpoint uploads took 782.40 seconds. Some work overlapped. The estimate reserved additional compatibility-repair time. Full phase estimates and measured subsets are included in the dated JSON record.

| Phase | Estimate (min) | Measured subset (min) |
| --- | ---: | --- |
| Path verification | 3 | Not separately timed |
| Environment inspection | 5 | Not separately timed |
| Model acquisition | 25 | 1.10 |
| Data and condition encoding | 15 | 3.50 |
| Training strategy | 5 | Not separately timed |
| Training settings | 3 | Not separately timed |
| Adaptation and short checks | 35 | Not separately timed |
| Training and checkpoints | 50 | 14.52 |
| Verification and report | 15 | Not separately timed |
| Session total | 156 | 58.36 |
