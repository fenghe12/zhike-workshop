# DiTalker 与 CogPortrait 新增部件的昇腾训练记录

[English](README.md) | 简体中文

本目录保存 2026-10-25 实际执行的数据预处理、完整模型训练、检查点及推理适配代码。基础权重冻结，新增部件单独训练。代码按实际使用的持久化会话目录组织，保留跨目录导入关系。

## 实验结果

| 实验 | DiTalker | CogPortrait 范围 |
| --- | --- | --- |
| 50 个 HDTF case、200 步 | 11 组新增模块均获得非零梯度并更新参数。仅残差输出层为零，内部参数正常初始化。 | 新增姿态 Conv3d，实际执行 200 个 AdamW 步骤。 |
| 从 200 步恢复至 220 步 | 恢复权重、优化器、CPU/NPU 随机数及采样器状态，优化器计数增加到 220。 | 同一姿态分支，计数增加到 220。 |
| 重新初始化、50 个 case、100 步、全部新增参数为零 | 557,911,534 个新增参数元素均检查为零。8/11 组模块在全部 100 步中为零梯度。CFG 1 和 CFG 7 均生成近似纯色画面，属于失败实验。 | 332,800 个新增参数元素均为零。姿态分支在 100 步中持续获得非零梯度，生成了可见人物预览。 |

[records](records/) 保存每个模型连续 100 条 loss CSV、逐步 JSONL，以及[完整计数和梯度结果](records/allzero100.json)。50 个真实 HDTF case 各读取两次。训练实际执行完整模型前向、损失、反向与参数更新调用，硬件为单张昇腾 910B1、64 GB。执行优化器调用与所有模块发生有效学习需要分别判断。

CogPortrait 本目录只实现接入完整 Wan2.2 S2V 的新增姿态分支，未实现代理规划与 KTO 偏好训练。预览使用训练集样例，未完成最终质量指标和未见人物泛化评测。DiTalker 的总损失包含 REPA 负余弦项，数值可以小于零。

## 恢复与运行

实际持久化根目录为 `/home/ma-user/work/npu-migration`。运行前检查真实挂载、可写性、剩余空间、模型文件和分配的 NPU。将 `sessions/` 内各个日期目录复制到该根目录的 `recovery/` 中，保留目录名称。

`run_env.sh` 使用已保留的 Torch 2.7.1、torch_npu 2.7.1 和依赖覆盖目录，并加载 `scripts/persistent-npu-env.sh`，使临时目录、编译缓存和日志位于数据卷。它们是已执行配置的启动器，未提供通用依赖安装器。

需要另行恢复 EasyAnimate V3、匹配的 T5、SadTalker/Deep3DFaceRecon、Whisper、CLIP、DINOv2、Wan2.2 源码和权重。路径及对应目录见 [English README](README.md)。50 个 case 的原片、清单和缓存条件保存在原 200 步会话的 `inputs/`；私有 OBS 保留实际数据和环境档案。目录内提供重新生成条件的代码，下载脚本中的原本地代理配置需按实际网络调整。

[DiTalker 原始源码](https://github.com/fenghe12/DiTalker-CVIU)应放入 200 步会话的 `source/DiTalker-CVIU`。在源码根目录应用 `patches/ditalker-npu-training.patch`。该补丁已对保留的 10 月 24 日上游源码检查应用，并将结果与实际运行源码直接逐文件比较。上游修改后需要重新检查适用性。

使用 `prepare_checkpoint_plan.py` 生成私有 OBS 上传计划，凭据从 `OBS_ACCESS_KEY_ID`、`OBS_SECRET_ACCESS_KEY` 环境变量读取。100 步会话需要 `checkpoint-plans/ditalker-100.private.json`、`cogportrait-100.private.json` 和相应的 `*-weights100.private.json`。每次实验创建新的目标对象，不提交这些计划与签名地址。完整检查点包含新增参数、缓冲区、AdamW 状态及随机数和采样器状态，直接写入 OBS，避免在 EVS 增加大型文件副本。

恢复文件并设置单卡限时后执行：

```bash
bash /home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-50hdtf-100steps-allzero-20261025/run_batch.sh
```

启动器先完成两项训练，再进行推理；恢复中断任务时跳过已有完成记录，并明确加载本次第 100 步权重。`run_cfg7_after_cog.sh` 保留追加的 CFG 7 对照，等待 CogPortrait 进程退出后执行。云资源启停和费用限制由调用方控制，收集结果后停止计算，保留持久盘与私有备份。

全部参数为零的 100 步实验与仅残差输出层为零的旧实验分别保留，不能将 DiTalker 的失败生成表述为复现成功。权重、原片、账号凭据和私有签名地址不在本公开目录中。
