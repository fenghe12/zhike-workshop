# Operator and learning audit, October 25, 2026

English | [简体中文](README.zh-CN.md)

The original all-zero 100-step checkpoints are preserved. This audit isolates a DiTalker input bug, ineffective learning, and actual Ascend operator restrictions. It does not replace the all-zero experiment with another initialization.

## Measured findings

- **Masked-video preprocessing caused the blank DiTalker preview.** The released inpaint pipeline uses −1 for unknown RGB pixels. Our old cache used 0. With the same step100 weights, seed42, CFG1 and 25 sampling steps, correcting only this condition restored a visible portrait. FP32 decoding of the old generated latents retained the failure, excluding VAE precision as its direct cause in this control.
- **The all-zero added branches still do not learn effectively.** Eight of eleven DiTalker groups had zero gradients throughout 100 steps. Only 30 output-bias tensors, containing 33,028 elements of 557,911,534 added elements, became nonzero. The exact ScaleAdapter dimensions were used in a gated-module control: CPU and NPU both stayed at zero active gradient tensors for three all-zero updates. Normal internal initialization with a zero residual output gave 2, 6 and 71 active tensors on both devices. That control is explicitly not a complete DiTalker training run.
- **Total loss is misleading without decomposition.** On the same 50 training cases and paired noise, with native masked conditions, pure DiTalker denoising MSE changed from 0.041943734 to 0.041973696, a 0.071% increase. Total loss fell mainly because of the negative cosine REPA term. Separate noise MSE, weighted eye MSE, REPA and VB fields are now logged; the legacy `mse` field is retained as a combined objective for compatibility.
- **CogPortrait pose learning is measurable but limited.** On 50 training cases at fixed sigma0.5, flow-matching loss changed from 0.047362410 to 0.046846089, a 1.09% reduction; 48/50 cases improved. A full-backbone backward/update replay verified finite nonzero weight and bias gradients and actual parameter changes. Agent planning and KTO remain absent.

| Actual restriction on Torch2.7.1 / torch_npu2.7.1 / CANN8.3rc1 | Result and handling |
| --- | --- |
| `aclnnReplicationPad1d`, BF16 input | Fails with 161002. Expand-and-concatenate replacement exactly matched CPU output and input gradient. |
| `aclnnTransformBiasRescaleQkv`, BF16 QKV with FP32 bias in eval MHA fastpath | Fails with 161002. Disabling this eval fastpath allows the general MHA path while preserving FP32 trainable parameters. |
| Production `torch_npu.npu_fusion_attention` | Forward/backward executed. Small control: output relative L2 difference about0.31%, Q/K/V gradient differences about0.35–0.40%, including BF16 conversion. |

The two errors are datatype/path restrictions in the tested stack, not a statement that all Ascend hardware lacks these operations. No new custom CANN operator was needed for the tested alternatives.

## Single-preview quality, not a benchmark

| Output | PSNR dB ↑ | RGB SSIM ↑ | LPIPS AlexNet ↓ | Face detections |
| --- | --- | --- | --- | --- |
| DiTalker100, old mask, CFG1 | 7.951 | 0.5695 | 0.7638 | 1/16 |
| DiTalker100, corrected mask, CFG1 | 23.819 | 0.8048 | 0.1495 | 16/16 |
| Initial all-zero additions, corrected mask | 23.848 | 0.8030 | 0.1503 | 16/16 |
| CogPortrait pose100 | 22.968 | 0.7889 | 0.1589 | 64/64 |

One training-set identity only. DiTalker uses source frames0,4,…,60 at6.25fps; CogPortrait uses64 consecutive frames at25fps. No generated-frame interpolation. SSIM uses an11×11 Gaussian window, sigma1.5, RGB mean, population moments and valid borders. LPIPSv0.1 AlexNet uses pretrained feature weights and calibrated heads. Face detection is independent MediaPipe FaceMesh detection per frame, confidence0.5, with no missing-frame interpolation. Methods with different frame rates are not ranked against one another.

FID/FVD and SyncNet scores are not reported. The original `calculate_lse_d.py` was a mislabeled 2D mouth-landmark calculation. The source patch now rejects that false name and exposes the geometric calculation as `calculate_mouth_landmark_distance.py`. It is not an audio-visual synchronization score.

## Reproduce or resume

Restore the session layout and private prerequisites described in the parent README. Apply the updated source patch. The corrected preprocessing generator writes `preprocessing_version=native_mask_unknown_minus_one_v1`; it refuses to silently reuse an old cache. Existing historical caches remain unchanged.

`fixed_di_audit.py` saves50 separately versioned conditions under this session's `inputs/di-native-mask/`. To train or infer with the corrected conditions while retaining the original target latents and encoders, set:

```bash
export DITALKER_CONDITIONS_DIR=/home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-operator-audit-20261025/inputs/di-native-mask
```

If that private folder has not been restored, regenerate conditions in a fresh persistent session. Historical comparisons deliberately set `DITALKER_ALLOW_RECORDED_MASK_CACHE=1`; ordinary training/inference rejects unversioned old masked conditions. This flag does not change initialization.

Create read-only private plans with `prepare_audit_reads.py`, supplying the existing DiTalker/CogPortrait step100 export object names, pretrained AlexNet object, bucket and endpoint. Credentials come from `OBS_ACCESS_KEY_ID` and `OBS_SECRET_ACCESS_KEY`. Keep generated plans outside Git. No model weights, face images, source clips, signed URLs, or cloud keys are public here.

Run sequentially on one NPU using the persistent `run_env.sh`: `operator_checks.py`, `full_di_audit.py`, `full_cog_audit.py`, then `fixed_di_audit.py`. `lpips_metrics.py` uses CPU only and can run alongside the NPU audit after preview arrays exist. The LPIPS code streams its already backed-up pretrained AlexNet weights into memory because the retained EVS was nearly full. It does not create an ephemeral model file or use random feature weights for scoring. `local_metrics.py` is the local Mac image/landmark evaluator and requires the retained MediaPipe overlay and ffmpeg.

This audit ran one Ascend910B1 and stopped compute at11:06; both CPU and NPU notebooks were confirmed stopped. Cloud lifecycle controllers and private credentials are excluded from the public package. Supply an independent bounded stop guard before another cloud run. Final source synchronization to the stopped cloud checkout was not confirmed; restore the corrected GitHub/OBS source before a new run.

## Records and remaining requirements

Machine-readable outputs are in [records/operator-audit-20261025](../../records/operator-audit-20261025/). The28-layer timing CSV is a single warm DiTalker training forward, not AgentHOI profiling: about0.592s across blocks,19.74ms median; no full per-layer backward timing is claimed. The historical100 loss rows and checkpoints remain separate.

The teacher's requirement that all added parts learn is not satisfied by strict DiTalker all-zero initialization. Making the deep branches learn requires a separately identified initialization change. CogPortrait still needs its planner and KTO components. AscendBridge CLI initialization/model registration and native adapter trials were performed earlier; complete autonomous migration and benchmark evaluation were not executed and are not claimed here.
