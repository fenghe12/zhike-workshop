# AscendBridge native Qwen trial — 2026-10-25

[简体中文](README.zh-CN.md)

The resumed runtime trial passed: **the native coding client used self-hosted Qwen3.6-35B-A3B Q8, wrote its plan, invoked the real execution tool, and reviewed actual results. Both original pretrained backbones completed50 distinct HDTF inputs and passed the unmodified adaptation and benchmark checkers.** No Kimi or external language-model API was used in the successful run.

| Model | Inputs | Mean synchronized forward | Peak allocated device memory |
|---|---:|---:|---:|
| EasyAnimateV3-XL-2-InP-512x512 |50|0.292390s|7.1964GiB|
| Wan2.2-S2V-14B |50|1.269906s|32.3737GiB|

Hardware: one Ascend910B2. Original source inputs are512×512,16 frames; the measured workload is one denoising timestep on native VAE latents, through all original backbone layers. Timing includes input transfer, noise and conditioning, excludes disk reads, output summaries and model loading. Memory is the peak allocation during the50 measured forwards after two warmups. This is not complete video sampling/decoding or a video quality benchmark. There is no matching CUDA reference.

## What actually executed

The Bridge source README identifies version2.5: https://gitcode.com/SLAI/SLAI-AscendBridge2 . The native coding client ran a bounded single-worker continuation using its existing adapters and diffusion benchmark contract. It made three real Bash tool calls: write plan, execute both models, write the review. The helper unloaded only this task Qwen before model execution and reloaded it before returning the results. No multiagent team or from-scratch autonomous migration is claimed.

Historical failures are retained privately: invalid Kimi authentication, a CANN multiprocessing AF_UNIX path-length failure, and an overlong native-client context. The final launcher uses a short persistent TMPDIR before Python starts and explicitly resets tempfile.tempdir; actual NPU process communication and matrix multiplication passed. The successful Qwen service used64K context with a bounded brief.

Formal environment rebuild validation remains **unexecuted** because upstream verify_environment.py computes file digests, prohibited by the user's workspace instructions. Official checkers were not altered. The formal board remains in_progress; runtime results do not imply that a new isolated installation passed.

## Reproduction files

Copy these adaptations into a matching full Bridge source checkout at framework/adaptations/. The scripts expect existing persistent model weights, genuine HDTF caches, and the documented persistent Python3.11 / torch2.7.1+cpu / torch_npu2.7.1 / CANN8.3rc1 environment. Generated uv locks are present; a fresh isolated installation has not been validated.

cloud_session.py is the public account-configurable controller template. Copy cloud-config.example.json to cloud-config.private.json, provide your own account and credential-file paths, and retain it privately. No real account identifiers, credentials, model weights, HDTF media, or private keys are supplied. qwen-task.txt uses {{SESSION_ROOT}} paths substituted by the launcher. Native model files must already exist at the configured persistent paths. The recorded task reuses already prepared adapters, rather than generating adapters from original CUDA source anew.

run_qwen.sh / qwen_service.py manage only the task-specific local Qwen service; native_qwen_workflow.py drives the native coding client; qwen_worker_tool.py sequentially changes the active model; run_remote.sh / run_models.py execute the actual model tasks. The native coding client must be installed. cloud_session.py requires Huawei ModelArts SDK packages and requests; its live account configuration stays private. Actual records and the Qwen plan/review are in ../../records/ascendbridge-workflow-20261025/ . Full traces and logs are backed up privately.
