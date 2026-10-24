# SenseNova U1.5 and AgentHOI on Ascend

English | [简体中文](README.zh-CN.md)

These launchers reuse the persistent Python 3.11, PyTorch 2.7.1, torch_npu 2.7.1 and CANN installation under `/home/ma-user/work/npu-migration`. Model locations are listed in `models.json`. Weights and credentials are excluded from Git.

Use the official [SenseNova-U1](https://github.com/OpenSenseNova/SenseNova-U1) and [AgentHOI](https://github.com/bone-11/agenthoi) sources. The SenseNova checkpoint is the full **SenseNova-U1.5-8B-MoT** release. AgentHOI uses InternVL3.5-38B, the original Wan2.1-I2V backbone and its trained `t2v/checkpoint-9500` model.

The changes address NPU attention, real-valued rotary multiplication, device placement, dependency imports and Transformers compatibility. They do not remove model layers or shorten official prompts, images, frames or sampling steps. The published AgentHOI F32 checkpoint is stored as BF16, matching the dtype used by official video inference. Single-device CPU offload is required on the available 64 GB device.

For the official SenseNova README text-to-image case, retain the script defaults: 2048 × 2048, 50 steps, CFG 4.0, timestep shift 3.0 and seed 42. For AgentHOI, retain both bundled inputs, 81 frames, 40 steps, the original image resolution, 1024 tokens per agent turn and 12 image tiles. Process counts are set to one as documented for single-device operation.

With OBS credentials configured as described in the main recovery guide:

```bash
python scripts/restore-obs.py --group sensenova-agenthoi --destination /home/ma-user/work/npu-migration
python scripts/restore-obs.py --group extra-runtime --destination /home/ma-user/work/npu-migration
```

The runtime archive contains source, compatibility changes, dependency overlays and launchers. Restore it into the same persistent root. The base interpreter, CANN and original Wan backbone are covered by the earlier recovery archives. Configure all temporary and cache directories on the persistent volume before running either model.

Sampling configuration is separate from validation status. The [initial deployment record](../../docs/deployment-20261023-sensenova-agenthoi.json) documents the earlier model-loading check. In the [October 23 full inference attempt](../../docs/agenthoi-full-20261023.json), both original cases completed the image-description preamble and all four reasoning agents. Case A completed all 40 sampling steps and produced an 81-frame, 624 × 624, 16 FPS video. Case B's video was interrupted at the authorized time limit. Two-case video completion remains unverified. Results and reasoning states were backed up to private OBS, and both notebooks were confirmed stopped.

Apply `patch_video_storage.py --repo /home/ma-user/work/npu-migration/repos/AgentHOI` before starting video inference on NPU. It stores block linear parameters in BF16, matching native AMP, while retaining FP32 time, normalization, modulation and output-head parameters. The actual inference load reported no missing model keys; the 96 unused keys belong to the training-only TRD projectors. The official `832*480` setting specifies maximum area; output dimensions follow the reference image's aspect ratio.

The `agenthoi_runtime_records.py` helper records token progress and completed reasoning turns without changing the prompts, model, image tiling or generation budget. Its saved conversation state can restore completed turns after an interrupted run. Set `AGENTHOI_RUN_RECORDS` to a writable directory on the persistent volume before applying `patch_progress.py`.

For a later video retry, reuse the saved `agent_refined/refined_merged.json` through the official `SKIP_AGENT=1 DATASET_PATH=...` options after checking that both cases contain all four agent outputs. This reuses completed reasoning and retains the original video settings.

[NPU layer profiling](profiling/README.md) provides the October 24 measurement and launcher. Actual Ascend fused attention was verified; the dated report includes all 40 layer timings and distinguishes nested module intervals from device kernel durations.
