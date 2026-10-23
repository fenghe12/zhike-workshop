# AD-NeRF 昇腾短程训练

[English](README.md) | 简体中文

本目录在[预训练模型重建部署](../README.zh-CN.md)的基础上增加实际梯度更新和检查点续训。使用官方 Obama 视频的全部 8000 个有效帧、7272 个训练相机姿态及原始验证集划分。官方人脸分割模型和 `process_data.py` 第 5 步原始算法生成头部及组合训练图像，复用此前验证过的音频特征、相机姿态和背景。

网络保留 8 层、256 宽度，每次头部训练更新采样 2048 条光线、躯干采样 1024 条光线，使用 64 个粗采样点和 128 个重要性采样点，图像分辨率为 450 × 450，学习率衰减配置保持不变。本次限制训练步数并调整检查点和日志间隔，用于验证限时训练，不代表完整训练收敛。官方默认训练计划包含更多迭代。

`patch_training.py` 适配昇腾设备位置、旧版 NumPy 类型别名和张量调用，加入训练更新记录，并保存 `completed_iterations`，避免续训时重复最后一次迭代的编号。头部音频注意力优化器按保存时使用的名称读取。`training_record.py` 检查损失和梯度是否有限、梯度范数是否非零，以及优化步骤是否实际改变参数。原始损失函数和优化目标保留。

头部从随机初始化开始训练，躯干加载本次训练的头部模型，其自身网络从随机初始化开始。当前早期阶段尚未达到头部默认第 200000 步的音频平滑转换条件。[训练记录](../../../docs/training-20261023-adnerf.json)分别记录实际更新、检查点续训和预览画面范围。

## 恢复并继续训练

使用预训练部署相同的已挂载持久化目录和基础环境。私有凭据和模型二进制文件不进入 Git。

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

继续训练前先设置允许的计算时长和自动停机。该命令恢复最新头部检查点及优化器状态。归档中的本次试验控制程序保留用于查阅，重新使用前需配置新的获准会话截止时间。临时文件、缓存、日志、训练图像和检查点均保存在持久化卷；训练和推理共用一张昇腾卡，顺序执行。
