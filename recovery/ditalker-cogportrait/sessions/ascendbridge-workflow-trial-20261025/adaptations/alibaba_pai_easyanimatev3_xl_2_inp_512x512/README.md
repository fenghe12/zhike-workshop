# alibaba-pai/EasyAnimateV3-XL-2-InP-512x512: AscendBridge adaptation

This adaptation was prepared through the repository's documented Codex AGENTS workflow with separate adapter and benchmark roles. The installed Claude provider rejected authentication (401), so no successful Claude team automation is claimed.

It uses the actual complete released pretrained backbone, original layers and genuine HDTF 512 x 512 inputs. The test consumes cached VAE/text/image/audio conditions produced previously from 16 source frames. The forward input is 4 x 64 x 64 latent positions. It does not execute text/audio encoders, VAE encode/decode, iterative sampling, or a full video-generation pipeline. DiTalker and CogPortrait trainable additions are excluded.

`--dry-run`, `--smoke-test`, and `--use-pretrained` all load real weights and execute the complete backbone once; none creates a reduced random model. There is no CPU fallback. `--cpu` is an explicit CPU-reference request.

## Runtime

The authorized existing persistent runtime is `/home/ma-user/work/npu-migration/envs/npu-base`, with Python 3.11, torch 2.7.1+cpu, torch_npu 2.7.1, CANN 8.3rc1, diffusers 0.35.2, transformers 4.53.1, accelerate 1.12.0 and safetensors 0.4.5. The `+cpu` torch wheel is the base for the NPU extension and does not imply CPU model execution. Dependencies must not be changed in that environment.

The independent pyproject declares pinned core dependencies and mutually exclusive `ascend` / `cuda` extras. A genuinely generated uv.lock and successful isolated reconstruction are still required for the framework's formal completed gate. Reusing the current environment is a bounded execution exception explicitly requested for this trial; it must not be presented as successful isolated reconstruction.

All new caches, logs and temporary files are adaptation-local, under the persistent EVS volume. Existing model and dataset files are read only. No model is downloaded by this script.

## Run

After selecting the one authorized idle NPU and configuring persistent CANN runtime paths, enter this adaptation directory and use the validated existing environment:

```sh
/home/ma-user/work/npu-migration/envs/npu-base/bin/python demo.py --dry-run > output.txt 2>&1
/home/ma-user/work/npu-migration/envs/npu-base/bin/python demo.py --smoke-test
/home/ma-user/work/npu-migration/envs/npu-base/bin/python accuracy_run.py --use-pretrained
```

For a future independent reconstruction, use `uv sync --locked --extra ascend` in this adaptation only, followed by `uv run --no-sync --extra ascend python demo.py --smoke-test`. That reconstruction is not executed during this budget-limited trial.

## Read-only source and inputs

- EasyAnimate native code and weights: `/home/ma-user/work/npu-migration/recovery/easyanimate-wans2v-training-3h-20261024/source/EasyAnimate` and its `models/EasyAnimateV3-XL-2-InP-512x512/transformer`.
- Wan native source: `/home/ma-user/work/npu-migration/repos/Wan2.2`; pretrained weights: `/home/ma-user/work/npu-migration/checkpoints/wan2.2-s2v-14b`.
- 50-case manifest and latent/encoder caches: `/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-50hdtf-200steps-20261025/inputs`.
- Corrected EasyAnimate native masked-video inputs: `/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-operator-audit-20261025/inputs/di-native-mask` (`native_mask_unknown_minus_one_v1`). Unknown RGB values are -1 before VAE encoding.
- Wan cached pose maps are not used. Native `cond_encoder` remains unchanged; no pose sequence is supplied, so its input is zero, matching the native absent-pose condition.

## Implementation boundary

The attention wrapper preserves dot-product scaling and mask semantics while using `torch_npu.npu_fusion_attention` on NPU. Padding of head channels is zero padding only; sequence positions, layers and parameters remain intact. CPU calls use native PyTorch SDPA.

Wan additionally constructs constant rotary tables on CPU and applies equivalent real-valued rotary arithmetic on NPU. BF16 replicate-padding uses expansion and concatenation. Time/output modules retain native FP32 behavior. These adaptations come from the recorded migration implementation, with fresh mathematical comparison during installation. No site-packages or original source is modified.

## Status

Source preparation and syntax inspection only at creation. NPU inference, full 50-case benchmark, accuracy comparison, profiler and isolated environment validation must be reported separately from this source preparation.


Runtime trial correction: CANN multiprocessing requires a short persistent TMPDIR. The first real attempt failed with AF_UNIX path too long. Use the runtime helper short path under /home/ma-user/work/npu-migration/runtime; all data remain on the confirmed persistent volume.
