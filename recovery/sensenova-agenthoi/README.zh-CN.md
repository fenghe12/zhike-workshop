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

推理参数与完成状态分别记录。AgentHOI 的 VLM 加载成功不代表完整推理及视频生成已经完成，实际完成情况见[部署记录](../../docs/deployment-20261023-sensenova-agenthoi.json)。

`agenthoi_runtime_records.py` 记录生成进度和已完成的推理轮次，保留原始提示词、模型、图像分块和生成 token 上限。中断后可通过保存的对话状态恢复已完成轮次。使用 `patch_progress.py` 前，将 `AGENTHOI_RUN_RECORDS` 配置为持久化卷上的可写目录。
