# 昇腾上的 EasyAnimate V3 与 Wan2.2 S2V 训练

[English](README.md) | 简体中文

2026-10-24 在单张昇腾 910B2、64 GB 设备内存上验证了真实数据读取、模型前向、损失、反向和参数更新。EasyAnimate V3 完成 3 步 AdamW 训练；Wan2.2 S2V 完成两组各 3 步 Adafactor 训练。具体数值及限制见[实测记录](../../docs/training-20261024-video-models.json)。

本次为短程兼容性验证，不代表完整训练已收敛，也不构成训练速度基准。数据来自公开的 [Wan Animate 示例视频](https://github.com/Wan-Video/Wan2.2/blob/main/examples/wan_animate/animate/video.mp4)，包含两段训练视频及一段独立片段作为固定验证输入。每段为 16 帧、256×256，原模型层和条件分支均保留。

## 模型与损失

- EasyAnimateV3-XL-2-InP-512x512：原始 `Transformer3DModel`，1,538,364,704 个参数，保留 sigma 扩散损失中的噪声 MSE 和 learned-variance 变分项。真实视频、修复条件、文本和 CLIP 参考图均经过编码。文本编码器复用现有 Latte 附带的同构 T5-XXL，不将其描述为新下载并逐文件独立确认的 V3 原配文本权重。
- Wan2.2-S2V-14B：原始 `WanModel_S2V`，16,295,755,609 个参数，使用流匹配速度 MSE，保留音频注入、参考图和 FramePack。Motioner 按发布配置保持关闭。初始运动历史由参考帧重复构造，未提供姿态输入。

VAE 和条件编码器仅进行冻结预处理。两个视频骨干的全部参数均获得梯度。S2V 在反向过程中将梯度暂存于 CPU，完整反向结束后，逐个传回 NPU 进行裁剪和优化器更新。参数不会在完整反向完成之前改变。该方式保留单卡完整模型，实测时间包含梯度传输。

## AscendBridge 的使用范围

本次下载的[官方源码](https://gitcode.com/SLAI/SLAI-AscendBridge2)声明版本为 2.5，已新增 `ascend-torch-cpt`，与较早的 2.0 PDF 不同。已实际执行看板初始化、模型注册和下载来源探测，并基于其扩散 CPT 流程适配训练脚本。本次未执行自主多智能体迁移会话。

通用模板需要项目适配：V3 元数据中的旧 PixArt 2D 标识与真实视频模型不一致，损失也需要保留 learned-variance 项。原生 S2V 的前向参数及音频、参考图、运动条件不能由通用接口直接替代。

已处理 V3 梯度检查点接口版本差异、BF16 重复填充、注意力掩码形状、NPU SDPA 和实数旋转位置编码。位置编码替代实现已比较前向输出及输入梯度。必要的时间和输出模块保留 FP32，S2V 主参数使用 BF16，未安装 CUDA 专属扩展。

独立小样本检查中，NPU complex64 乘法及反向、SDPA 反向均通过。因此不将复数操作整体列为缺失算子，原始完整 FP64 位置编码路径尚未进行端到端验证。

## 持久化目录与执行

实测根目录为 `/home/ma-user/work/npu-migration`。恢复已归档运行环境后，将本目录文件置于其下 `recovery/easyanimate-wans2v-training-3h-20261024`。该会话的 `source/` 包含原始 EasyAnimate、AscendBridge 源码快照；Wan 源码和权重分别位于根目录的 `repos/Wan2.2`、`checkpoints/wan2.2-s2v-14b`。V3 权重位于会话内 `models/EasyAnimateV3-XL-2-InP-512x512`。

使用 `run_env.sh` 中记录的持久化 Torch 2.7.1、torch_npu 2.7.1 环境及依赖目录。启动器通过已有的 `persistent-npu-env.sh` 设置持久化临时目录、缓存和日志。不要用工具当前依赖清单覆盖已验证环境。启动前检查数据盘挂载、可写目录、剩余内存、模型文件及实际分配的 NPU，按顺序执行：

```bash
bash run_env.sh python prepare_training_data.py ea
bash run_env.sh python train_compatibility.py ea --steps 3
bash run_env.sh python prepare_training_data.py wan
bash run_env.sh python train_compatibility.py wan --steps 3 --learning-rate 5e-6
```

训练前，在已授权且具有 OBS Python SDK 的本机运行 `prepare_checkpoint_plan.py`，生成对应的 `easyanimatev3-checkpoint.private.json` 或 `wan22s2v-checkpoint.private.json`，再将私有计划传入会话目录。该程序从环境变量读取 OBS 访问凭据，并接受桶、服务地址、对象路径和输出文件参数。私有上传计划及凭据不得提交 Git。完整模型与优化器检查点以 64 MiB 分段写入私有 OBS，再分别检查对象长度和检查点结构，避免额外占用数据盘保存另一份大文件。

云实例启动和停止由独立控制程序管理。按授权设置使用上限，收集完成后停止计算，保留持久盘、原权重和私有备份。原始模型代码及权重遵循各自许可证，本目录不包含权重或私有部署信息。

## 会话用时

预估 156 分钟，58.36 分钟后确认计算已停止。部分准备和修复未单独计时；模型下载 66 秒，两个数据预处理约 210 秒，9 个优化器步骤合计 88.95 秒，三份检查点上传合计 782.40 秒。部分工作并行，不能简单相加。预估为兼容性修复预留了时间，完整阶段预算及已测部分见本次 JSON 记录。

| 阶段 | 预计分钟 | 已测部分分钟 |
| --- | ---: | --- |
| 路径核对 | 3 | 未单独计时 |
| 环境检查 | 5 | 未单独计时 |
| 模型获取 | 25 | 1.10 |
| 数据与条件编码 | 15 | 3.50 |
| 训练方式选择 | 5 | 未单独计时 |
| 训练参数选择 | 3 | 未单独计时 |
| 适配与短程检查 | 35 | 未单独计时 |
| 训练及检查点 | 50 | 14.52 |
| 验证与报告 | 15 | 未单独计时 |
| 实例会话总计 | 156 | 58.36 |
