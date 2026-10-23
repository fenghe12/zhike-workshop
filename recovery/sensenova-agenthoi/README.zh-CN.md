# 昇腾上的 SenseNova U1.5 与 AgentHOI

[English](README.md) | 简体中文

启动器复用 `/home/ma-user/work/npu-migration` 下的持久化 Python 3.11、PyTorch 2.7.1、torch_npu 2.7.1 和 CANN。模型目录见 `models.json`；权重和凭据不进入 Git。

源代码分别来自官方 [SenseNova-U1](https://github.com/OpenSenseNova/SenseNova-U1) 和 [AgentHOI](https://github.com/bone-11/agenthoi)。SenseNova 使用正式版 **SenseNova-U1.5-8B-MoT**。AgentHOI 使用 InternVL3.5-38B、原始 Wan2.1-I2V 基础模型及训练后的 `t2v/checkpoint-9500`。

修改涉及 NPU 注意力、使用实数运算实现相同的旋转位置编码、设备位置、依赖导入和 Transformers 兼容性。不删除模型层，不缩短官方提示词，不减少输入图像、视频帧数或采样步数。AgentHOI 发布的 FP32 权重转存为 BF16，与官方视频推理使用的精度一致。现有 64 GB 单卡需要将部分模型卸载至 CPU。

SenseNova 官方 README 文生图案例保留默认参数：2048 × 2048、50 步、CFG 4.0、timestep shift 3.0、seed 42。AgentHOI 保留两个官方输入、81 帧、40 步、原图像分辨率、每次推理最多 1024 个 token 和 12 个图像块。按照官方单卡使用说明，将工作进程数设置为 1。

按主恢复说明配置 OBS 访问凭据后，可下载模型和运行环境档案：

```bash
python scripts/restore-obs.py --group sensenova-agenthoi --destination /home/ma-user/work/npu-migration
python scripts/restore-obs.py --group extra-runtime --destination /home/ma-user/work/npu-migration
```

运行环境档案包含源码、兼容修改、依赖目录和启动器，应解压至相同的持久化根目录。基础解释器、CANN 和原始 Wan 模型保存在此前的恢复档案中。启动前将临时目录和全部缓存设置在持久化数据卷上。

推理参数与完成状态分别记录。[初始部署记录](../../docs/deployment-20261023-sensenova-agenthoi.json)保存此前的模型加载情况。[10 月 23 日完整推理尝试](../../docs/agenthoi-full-20261023.json)中，两例原始输入均完成图像描述及全部四个推理阶段。case_a 完成 40 步采样，生成 81 帧、624 × 624、16 FPS 的视频。case_b 视频因达到获准使用时间而中断，尚未完成两例视频生成。结果和推理状态已备份至私有 OBS，两台实例均已确认停止。

NPU 视频推理启动前，执行 `patch_video_storage.py --repo /home/ma-user/work/npu-migration/repos/AgentHOI`。该修改将计算块内的线性层参数保存为与原生 AMP 一致的 BF16，时间、归一化、调制及输出头的小型参数仍为 FP32。实际加载没有缺失推理模型权重；96 个未使用的键来自仅用于训练的 TRD 投影器。官方 `832*480` 设置指定最大面积，输出尺寸由参考图像的宽高比决定。

`agenthoi_runtime_records.py` 记录生成进度和已完成的推理轮次，保留原始提示词、模型、图像分块和生成 token 上限。中断后可通过保存的对话状态恢复已完成轮次。使用 `patch_progress.py` 前，将 `AGENTHOI_RUN_RECORDS` 配置为持久化卷上的可写目录。

后续重试视频生成时，先检查保存的 `agent_refined/refined_merged.json` 中两例均包含全部四个阶段的输出，再通过官方 `SKIP_AGENT=1 DATASET_PATH=...` 参数复用已完成的推理，保留原始视频生成配置。
