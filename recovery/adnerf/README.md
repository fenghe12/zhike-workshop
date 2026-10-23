# AD-NeRF pretrained reconstruction on Ascend

English | [简体中文](README.zh-CN.md)

This deployment uses the official [AD-NeRF](https://github.com/YudongGuo/AD-NeRF) pretrained Obama head and torso models. It does not train a new identity. The reconstruction case retains 300 frames, 450 × 450 pixels, 25 FPS, 64 coarse samples, 128 importance samples and `render_factor=0`.

Audio is processed by the official DeepSpeech 0.1.0 frozen model and feature extractor. The source audio produces a finite, varying `(7999, 16, 29)` array. MFCC features alone cannot replace that array. The supplied pretrained camera poses are retained. Background preparation uses the official face parser and the original step-4 routine, including all 400 frames selected by its native stride of 20.

`patch_npu.py` updates device placement, a legacy tensor constructor and deprecated NumPy scalar aliases. It also requires head and torso checkpoints to exist and records their loaded training steps. Both official checkpoints belong in `dataset/Obama/logs/Obama_com`, as required by the combined renderer configuration. Model architecture, ray sampling and frame count are retained.

## Restore the validated environment

Use the persistent root `/home/ma-user/work/npu-migration`, after confirming its volume is mounted and writable. The base Python 3.11, PyTorch 2.7.1, torch_npu 2.7.1, CANN and `npu-shims` are part of the existing [recovery instructions](../../docs/RECOVERY.md). Configure private OBS access using that guide, then:

```bash
python scripts/restore-obs.py --group adnerf --destination /home/ma-user/work/npu-migration
cd /home/ma-user/work/npu-migration
tar -xzf adnerf-code-models-and-env.tar.gz
source scripts/persistent-npu-env.sh
bash scripts/python-adnerf-audio recovery/adnerf-official-20261023/extract_audio.py \
  --source repos/AD-NeRF-official-20261023 \
  --audio workspace/adnerf-official-20261023/Obama/aud.wav \
  --graph recovery/adnerf-official-20261023/models/deepspeech-0.1.0.pb \
  --output workspace/adnerf-official-20261023/Obama/aud.npy
python recovery/adnerf-official-20261023/run_native_case.py
```

The audio stage uses CPU TensorFlow; face parsing and NeRF rendering use one Ascend device in sequence. Existing background metadata allows the controller to reuse the prepared background. Rendering takes about 50 minutes on the validated device, in addition to preparation time. The controller combines the full 300-frame result and original audio into a 12-second MP4 and checks frame count, size, frame rate and audio presence.

All environments, caches, compilation files, logs and temporary files use the persistent root through `persistent-npu-env.sh`. Keep that launcher configuration when restoring. Weights and environment binaries remain in private OBS; this public directory contains scripts, configuration and asset locations. `obs-objects.json` lists recovery objects. See the [dated validation record](../../docs/deployment-20261023-adnerf.json) for the actual completed scope.
