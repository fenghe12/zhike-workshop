# DiTalker last-output-zero training correction

English | [简体中文](README.zh-CN.md)

The intended initialization is **zero initialization of the final residual output layers**. The earlier experiment that zeroed every newly added parameter was an implementation misunderstanding and remains historical material only.

This run uses50 genuine HDTF cases,100 actual AdamW updates, batch1,512×512,16 strided source frames, a frozen full EasyAnimateV3 backbone, and all11 added DiTalker groups. Native masked conditions use−1 for unknown RGB pixels. It starts fresh from the released frozen base rather than restoring the previous invalid added parameters.

The85 zero-initialized residual exits are28 ACA output projections,28 SCA output projections,28 ECA output projections and the PoseGuider output convolution. Internal audio/style projections, learned query tokens and LayerNorm scale parameters retain normal initialization. Scale coefficients start at tanh(1); their final linear weights are zero and biases one. The REPA auxiliary projection retains normal initialization because it is a loss readout rather than a residual injection.

An output layer initialized to zero can temporarily block upstream gradients on the first update. Validation records each group's first nonzero-gradient step, active step count, every trainable tensor's gradient coverage, and exact parameter differences from its initial values. A group must have a nonzero gradient and an actual parameter change; printing a loss or merely executing an optimizer call is insufficient. Frozen parameters must have no gradients and their sampled values must remain unchanged.

## Persistent layout and execution

Restore the dated sessions and private prerequisites from the parent README, including the updated DiTalker source patch and the separately versioned50-case masked conditions. `run_env.sh` sets `DITALKER_CONDITIONS_DIR`, persistent temporary/cache/log paths, and the single exposed NPU. It does not enable the historical old-mask override.

Create fresh private `checkpoint-plans/ditalker-100.private.json` and `ditalker-weights100.private.json` using the parent checkpoint-plan helper. The full checkpoint and weights stream directly to private OBS. The complete checkpoint is reopened on CPU; optimizer counters and every added parameter are compared. Generate `metric.private.json` for the already retained pretrained AlexNet metric object. No private plans, model files or source clips belong in Git.

With a separately managed, bounded single-card cloud session:

```bash
bash /home/ma-user/work/npu-migration/recovery/ditalker-gradient-repair-50hdtf-100steps-20261025/run_batch.sh
```

The sequence performs initial fixed-noise evaluation on the same50 cases,100 updates, final fixed-noise evaluation, complete private checkpoint validation, then three previews from two training cases: case1 CFG1 and CFG7, case2 CFG1. Preview resolution is512×512,16 frames at6.25fps,25 sampling steps, seed42. Case1 is the same identity used by the earlier diagnostic report. CPU LPIPS/SSIM/PSNR follows generation and uses fully pretrained AlexNet features plus calibrated LPIPS heads.

The cloud controller, credentials and resource lifecycle files are intentionally absent from this public source package. Stop compute on completion, failure or the agreed deadline. Respect other tasks using the shared card.

`finish_repair.py` uses the saved real results to encode local H.264 previews, compute face detection coverage and build the report fragment. Then `integrate_reports.py` in the operator-audit session updates the existing standalone local report. It embeds both historical100-row loss CSVs, their curves, the original training report, diagnostics and the corrected run's100 loss rows and previews. No external model/media host is required to view the completed page.

The old all-parameter-zero history is preserved separately and must not be treated as the requested last-layer-zero configuration. CogPortrait remains limited to the pose branch; this correction does not add its planner or KTO training. Training-set preview diagnostics do not establish held-out quality or convergence.


## Executed result

The corrected100-step run completed on one Ascend910B2. All11 groups received finite nonzero gradients and changed parameters;908/908 added tensors received a nonzero gradient at least once. Attention residual exits, pose and REPA groups were active from step1. ScaleAdapter, audio projection and the style pipeline were active from step2; these groups had99/100 nonzero-gradient updates. All50 cases were read twice. The full private checkpoint was reopened and every added weight plus optimizer counters were checked.

On the same50 paired fixed-noise training cases, pure denoising MSE changed from0.041943734 to0.042036540 (+0.221%). Thus the zero-gradient problem is resolved, while improved denoising quality or convergence is not established by100 updates.

| Training-case preview | PSNR↑ dB | RGB SSIM↑ | LPIPS↓ | Face detections |
| --- | --- | --- | --- | --- |
| Case1, CFG1 | 23.912 | 0.8179 | 0.1440 | 16/16 |
| Case1, CFG7 | 23.306 | 0.7951 | 0.1731 | 16/16 |
| Case2, CFG1 | 24.787 | 0.8652 | 0.1025 | 16/16 |

[Complete numeric records](../../records/last-output-zero100-20261025/) retain all100 loss rows, per-group gradient activity, parameter changes, initialization audit and fixed-noise losses. The standalone local HTML embeds the corrected DiTalker100 rows, retained CogPortrait100 rows, historical erroneous DiTalker100 rows, all curves, diagnostics and actual previews. No source media or trained weights are published here.

The task's50CNY budget was respected by a conservative runtime estimate of40.56CNY, including connection recovery. The first training/checkpoint/inference run completed, but SSH result collection timed out. Results were subsequently recovered from persistent storage without retraining; all compute was confirmed stopped at17:13 on October25. No new notebook or disk was ultimately created: the preceding course task released the existing card before a fresh independent billing lease began. The public package excludes all cloud lifecycle credentials and controllers.
