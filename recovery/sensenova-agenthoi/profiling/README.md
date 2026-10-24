# AgentHOI NPU layer profiling

English | [简体中文](README.zh-CN.md)

The [October 24 measurement](../../../docs/agenthoi-layer-profile-20261024.json) verified actual `aclnnFlashAttentionScore` device kernels on one Ascend 910B1. Normal steps averaged 24.52 seconds. The 40 Transformer blocks averaged 606.8 ms each per denoising step, including conditional and unconditional forwards.

This dated launcher reuses the existing persistent installation and saved official `case_a` reasoning under `/home/ma-user/work/npu-migration`. Restore the original full-inference result archive before using it. Place these files in `recovery/agenthoi-layer-profile-20261024` beneath that root and run `bash run_profile.sh`. Cloud start/stop controls are separate; set a usage limit and stop compute after collection.

The original 81 frames, 40 steps, CFG 5, shift 5 and seed 42 are preserved. No shared model source is modified. Step 3 records block/self-attention/cross-attention/FFN stream intervals; step 4 captures actual CPU/NPU operators; step 5 records rotary-encoding and SDPA intervals. There is no per-layer device synchronization. First and instrumented steps are excluded from the normal-step average.

Module intervals are inclusive and can contain host-induced idle time. RoPE and SDPA are included within attention; their durations must not be added to parent module durations. Each timing category samples one warmed step. `analyze_results.py` processes collected JSON and profiler CSV files locally.

Use the short persistent temporary directory configured by the launcher. Longer directories can exceed the Unix socket path limit when CANN creates a multiprocessing manager. The launcher selects the toolkit profiler directory before the generic CANN `bin` directory. The recorded run's automatic export failed with the generic path; its raw records were successfully exported using the persistent toolkit `tools/profiler/bin/msprof --export=on --output=<PROF_directory>`. Check the generated `op_summary` CSV before claiming a backend was observed.
