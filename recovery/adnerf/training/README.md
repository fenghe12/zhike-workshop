# Short AD-NeRF training trial on Ascend

English | [简体中文](README.zh-CN.md)

This extends the [pretrained reconstruction deployment](../README.md) with real gradient updates and checkpoint continuation. The trial uses the official Obama video, all 8000 valid frames, 7272 training camera poses and the original validation split. The full official face parser produces head and combined training images using the unchanged image-generation routine from `process_data.py` step 5. Previously verified audio features, camera poses and background are reused.

The network retains eight layers of width 256, 2048 head rays and 1024 torso rays per training update, 64 coarse samples, 128 importance samples, 450 × 450 images and the original learning-rate schedule. Trial iteration limits and checkpoint/log intervals are chosen for a bounded training test. They do not establish full convergence. Native defaults use substantially longer training schedules.

`patch_training.py` adapts NPU device placement and legacy NumPy/tensor calls. It adds update records and stores `completed_iterations` in checkpoints so continuation does not repeat the last iteration label. The head audio-attention optimizer key is read using the same name used when saving. `training_record.py` checks finite loss and gradients, a nonzero gradient norm and an actual parameter change during optimizer steps. The original losses and optimization targets are retained.

The head trial starts from random initialization. Torso training loads the newly trained head and starts its own network from random initialization. At this early stage, the head's default audio-smoothing transition at iteration 200000 has not been reached. The [dated training record](../../../docs/training-20261023-adnerf.json) separates actual updates, checkpoint continuation and preview quality.

## Restore and continue

Use the same mounted persistent root and base environment as the pretrained deployment. Private credentials and model binaries are excluded from Git.

```bash
python scripts/restore-obs.py --group adnerf --destination /home/ma-user/work/npu-migration
python scripts/restore-obs.py --group adnerf-training --destination /home/ma-user/work/npu-migration
cd /home/ma-user/work/npu-migration
tar -xzf adnerf-code-models-and-env.tar.gz
tar -xzf adnerf-training-data.tar.gz
tar -xzf adnerf-training-code-and-results.tar.gz
source scripts/persistent-npu-env.sh
export NPU_MIGRATE=1
export PYTHONPATH="$NPU_ROOT/envs/npu-shims:$NPU_ROOT/envs/adnerf-py311:${PYTHONPATH:-}"
export ADNERF_TRAIN_LOG="$NPU_ROOT/recovery/adnerf-training-20261023/head-continued.jsonl"
python recovery/adnerf-training-20261023/launch_native_training.py \
  --repo "$NPU_ROOT/repos/AD-NeRF-training-20261023" --part HeadNeRF -- \
  --config "$NPU_ROOT/recovery/adnerf-training-20261023/HeadNeRF_config.txt" \
  --N_iters 2000 --i_weights 100 --i_print 20
```

Configure the permitted compute duration and automatic stopping before continuing training. The command resumes the latest head checkpoint and its optimizer states. The dated trial controller is archived for reference; it requires a new authorized session deadline before reuse. All temporary files, caches, logs, training images and checkpoints remain on the persistent volume. Training and inference share one Ascend device and execute in sequence.
