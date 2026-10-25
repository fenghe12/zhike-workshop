# DiTalker and CogPortrait added-component training on Ascend

English | [简体中文](README.zh-CN.md)

This folder preserves the executed preprocessing, full-model training, checkpoint, and inference adapters from October 25, 2026. Original backbone weights remain frozen. Runtime source is organized by the actual persistent session directory so that the cross-session imports remain reproducible.

## Correct initialization and current result

Zero initialization means the final residual output layers, with normal internal parameters. The earlier all-parameter-zero run was an implementation misunderstanding. The [corrected50-case/100-step run](sessions/ditalker-gradient-repair-50hdtf-100steps-20261025/README.md) verified nonzero gradients and parameter updates in all11 groups, with908/908 added tensors receiving gradients. Pure fixed-noise MSE increased0.221%, so this validates gradient flow rather than convergence. The unified local report retains both models' complete loss files and all historical diagnostics.

## Recorded experiments

| Experiment | DiTalker | CogPortrait scope |
| --- | --- | --- |
| 50 HDTF cases, 200 steps | Eleven added groups received nonzero gradients and changed parameters. Residual outputs started at zero; internal parameters used normal initialization. | Added pose Conv3d, 200 actual AdamW steps. |
| Restore step 200, continue to 220 | Restored weights, AdamW state, CPU/NPU random state, and sampler state; optimizer counters advanced to 220. | Same pose branch, counters advanced to 220. |
| Fresh 50 HDTF cases, 100 steps, every added parameter zero | All 557,911,534 added parameter elements were checked as zero before training. Eight of eleven groups received zero gradients throughout. The original masked-pixel cache caused nearly uniform frames. A later same-weight input correction restored portraits; eight dead gradient groups still prevent effective all-component learning. | All 332,800 added parameter elements started at zero. The pose branch received nonzero gradients in all 100 updates and produced a visible portrait preview. |

The strict all-zero experiment has [100 CSV loss rows per model](records/), full per-step JSONL records, and a [machine-readable result](records/allzero100.json). Each of the 50 real HDTF cases was read twice. Loss computation, backward propagation, and optimizer calls occurred on one Ascend 910B1 with 64 GB. An optimizer call does not imply effective learning in every module.

CogPortrait here means the added pose-conditioned branch attached to the complete Wan2.2 S2V backbone. Agent planning and KTO preference training are not implemented by this package. Preview inputs are training cases. Single-preview diagnostic quality metrics and paired 50-case training losses are now available in the [operator audit](sessions/ditalker-cogportrait-operator-audit-20261025/README.md); full benchmark and unseen-person generalization were not evaluated. DiTalker's objective includes a negative cosine REPA term and can be negative.

## October 25 operator and preprocessing correction

See the [measured audit, corrected input convention, and restoration steps](sessions/ditalker-cogportrait-operator-audit-20261025/README.md). New training/inference validates the cache version or explicitly supplied repaired conditions. Historical caches and original loss records remain unchanged. The source patch also separates loss components and corrects a mislabeled landmark metric.

## Restore the tested layout

Use the persistent root `/home/ma-user/work/npu-migration`. Verify its actual mount, write access, space, model files, and NPU allocation before execution. Copy the **contents** of `sessions/` into its `recovery/` directory. The dated directory names are part of the recorded layout.

The adapters require the retained Torch 2.7.1 / torch_npu 2.7.1 runtime and dependency overlays referenced by each `run_env.sh`. Those launchers source `scripts/persistent-npu-env.sh` to keep temporary directories, compilation caches, and logs on the data volume. They are recorded launchers, not a generic dependency installer.

Restore or acquire these prerequisites separately:

- EasyAnimate V3 source and `EasyAnimateV3-XL-2-InP-512x512` under `recovery/easyanimate-wans2v-training-3h-20261024/`.
- Matching Latte T5, SadTalker/Deep3DFaceRecon, Whisper, CLIP and DINOv2 resources referenced by preprocessing.
- Wan2.2 source in `repos/Wan2.2` and released S2V weights in `checkpoints/wan2.2-s2v-14b`.
- [DiTalker source](https://github.com/fenghe12/DiTalker-CVIU) in the 200-step session's `source/DiTalker-CVIU`. Apply `patches/ditalker-npu-training.patch` from that source root. The patch was checked against the upstream snapshot retained on October 24, and the resulting files were compared directly with the corrected local runtime source. The audit separately records NPU runs and code-only cache/metric checks. Check patch applicability if upstream changes.
- The 50-case manifest, source clips, and cached conditions in that same session's `inputs/`. Private OBS retains the executed data and runtime archives. Preprocessing scripts are included for rebuilding conditions; dataset helpers contain the original local proxy setting, which may need adjustment.

Source and model acquisition remains subject to the original repositories' terms. No model weights, source videos, access credentials, or signed object URLs are included here.

## Private checkpoint plans

`prepare_checkpoint_plan.py` uses `OBS_ACCESS_KEY_ID` and `OBS_SECRET_ACCESS_KEY` from the calling environment. Create new private destinations before each experiment. Keep its generated plans outside version control.

For the fresh 100-step run, create `checkpoint-plans/{ditalker,cogportrait}-100.private.json` and the corresponding `*-weights100.private.json` in the 100-step session. The full checkpoint includes added parameters, added buffers, AdamW state and random/sampler state. Checkpoints stream to OBS without another multi-gigabyte EVS copy. Uploaded lengths and a complete CPU checkpoint reload were checked separately.

The 200-step, continuation, and preview scripts use their own dated plan names. Regenerate expired read URLs before reuse. Private plans and cloud lifecycle credentials are intentionally separate from this public source.

## Execute sequentially

After restoring the required files and authorizing a bounded cloud session, the 100-step launcher is:

```bash
bash /home/ma-user/work/npu-migration/recovery/ditalker-gradient-repair-50hdtf-100steps-20261025/run_batch.sh
```

It performs both training runs before inference, skips already completed runs when recovering an interrupted session, and loads the new step-100 export explicitly. `run_cfg7_after_cog.sh` preserves the additional CFG 7 comparison after CogPortrait exits. Cloud start/stop and billing controls remain the caller's responsibility; stop compute after collection and retain the persistent volume and private backups.

The included configuration records the strict all-zero experiment. Do not describe the corrected DiTalker preview as effective training of every added component. In the earlier residual-output-zero experiment, internal parameters were not all zero; that experiment must remain distinct.


## AscendBridge native Qwen trial · 2026-10-25

[Native self-hosted Qwen trial](sessions/ascendbridge-workflow-trial-20261025/README.md): both complete pretrained backbones passed50 distinct real inputs and the unmodified source/runtime checkers. EasyAnimate0.292390s, Wan S2V1.269906s per single denoising forward. Native client tool execution and final review completed. Formal isolated environment rebuild is unverified; full video and CUDA comparisons are untested.
