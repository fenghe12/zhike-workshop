# DiTalker 与 CogPortrait 新增部件的昇腾训练记录

[English](README.md) | 简体中文

本目录保存 2026-10-25 实际执行的数据预处理、完整模型训练、检查点及推理适配代码。基础权重冻结，新增部件单独训练。代码按实际使用的持久化会话目录组织，保留跨目录导入关系。

## 实验结果

| 实验 | DiTalker | CogPortrait 范围 |
| --- | --- | --- |
| 50 个 HDTF case、200 步 | 11 组新增模块均获得非零梯度并更新参数。仅残差输出层为零，内部参数正常初始化。 | 新增姿态 Conv3d，实际执行 200 个 AdamW 步骤。 |
| 从 200 步恢复至 220 步 | 恢复权重、优化器、CPU/NPU 随机数及采样器状态，优化器计数增加到 220。 | 同一姿态分支，计数增加到 220。 |
| 重新初始化、50 个 case、100 步、全部新增参数为零 | 557,911,534 个新增参数元素均检查为零。8/11 组模块在全部 100 步中为零梯度。旧遮罩缓存导致CFG1、CFG7近似纯色；后续同权重修正输入已恢复人脸，但8组零梯度仍未满足全部部件有效学习。 | 332,800 个新增参数元素均为零。姿态分支在 100 步中持续获得非零梯度，生成了可见人物预览。 |

[records](records/) 保存每个模型连续 100 条 loss CSV、逐步 JSONL，以及[完整计数和梯度结果](records/allzero100.json)。50 个真实 HDTF case 各读取两次。训练实际执行完整模型前向、损失、反向与参数更新调用，硬件为单张昇腾 910B1、64 GB。执行优化器调用与所有模块发生有效学习需要分别判断。

CogPortrait 本目录只实现接入完整 Wan2.2 S2V 的新增姿态分支，未实现代理规划与 KTO 偏好训练。预览使用训练集样例。现已增加单例质量诊断和50例固定噪声训练检查，完整测试集和未见人物泛化仍未评估。DiTalker 的总损失包含 REPA 负余弦项，数值可以小于零。

## 恢复与运行

实际持久化根目录为 `/home/ma-user/work/npu-migration`。运行前检查真实挂载、可写性、剩余空间、模型文件和分配的 NPU。将 `sessions/` 内各个日期目录复制到该根目录的 `recovery/` 中，保留目录名称。

`run_env.sh` 使用已保留的 Torch 2.7.1、torch_npu 2.7.1 和依赖覆盖目录，并加载 `scripts/persistent-npu-env.sh`，使临时目录、编译缓存和日志位于数据卷。它们是已执行配置的启动器，未提供通用依赖安装器。

需要另行恢复 EasyAnimate V3、匹配的 T5、SadTalker/Deep3DFaceRecon、Whisper、CLIP、DINOv2、Wan2.2 源码和权重。路径及对应目录见 [English README](README.md)。50 个 case 的原片、清单和缓存条件保存在原 200 步会话的 `inputs/`；私有 OBS 保留实际数据和环境档案。目录内提供重新生成条件的代码，下载脚本中的原本地代理配置需按实际网络调整。

[DiTalker 原始源码](https://github.com/fenghe12/DiTalker-CVIU)应放入 200 步会话的 `source/DiTalker-CVIU`。在源码根目录应用 `patches/ditalker-npu-training.patch`。该补丁已对保留的 10 月 24 日上游源码检查应用，并将结果与修正后的本地运行源码直接逐文件比较；NPU诊断与缓存检查分别记录。上游修改后需要重新检查适用性。

使用 `prepare_checkpoint_plan.py` 生成私有 OBS 上传计划，凭据从 `OBS_ACCESS_KEY_ID`、`OBS_SECRET_ACCESS_KEY` 环境变量读取。100 步会话需要 `checkpoint-plans/ditalker-100.private.json`、`cogportrait-100.private.json` 和相应的 `*-weights100.private.json`。每次实验创建新的目标对象，不提交这些计划与签名地址。完整检查点包含新增参数、缓冲区、AdamW 状态及随机数和采样器状态，直接写入 OBS，避免在 EVS 增加大型文件副本。

恢复文件并设置单卡限时后执行：

```bash
bash /home/ma-user/work/npu-migration/recovery/ditalker-cogportrait-50hdtf-100steps-allzero-20261025/run_batch.sh
```

启动器先完成两项训练，再进行推理；恢复中断任务时跳过已有完成记录，并明确加载本次第 100 步权重。`run_cfg7_after_cog.sh` 保留追加的 CFG 7 对照，等待 CogPortrait 进程退出后执行。云资源启停和费用限制由调用方控制，收集结果后停止计算，保留持久盘与私有备份。

全部参数为零的 100 步实验与仅残差输出层为零的旧实验分别保留，不能将修正后的DiTalker预览表述为全部新增模块训练成功。权重、原片、账号凭据和私有签名地址不在本公开目录中。

## 2026-10-25 算子与预处理更正

[完整检查与修正条件恢复步骤](sessions/ditalker-cogportrait-operator-audit-20261025/README.zh-CN.md)记录实际算子限制、CPU/NPU梯度对照、50例分项loss与单例质量指标。新训练和推理检查缓存版本，旧缓存用于历史对照时须显式设置选项。原100条loss与检查点保留。

## 用户明确的初始化含义与当前结果

零初始化指新增残差分支最后输出层为零，内部参数保留正常初始化。此前全部参数为零属于实现理解错误。[本次50例100步修复](sessions/ditalker-gradient-repair-50hdtf-100steps-20261025/README.zh-CN.md)已验证11/11组的非零梯度与参数更新，908/908个新增张量曾获得非零梯度。纯固定噪声MSE略升0.221%，当前完成梯度传播验证，未作收敛结论。统一HTML内嵌两模型完整loss、曲线、诊断、历史记录和新预览。


## AscendBridge workflow trial · 2026-10-25

[实际流程试验](sessions/ascendbridge-workflow-trial-20261025/README.zh-CN.md)：适配与评测源码检查通过；真实NPU试验在CANN进程通信初始化处失败，没有有效50输入指标。原生客户端认证也未通过。短临时路径及Python缓存修正已通过本地通信验证，仍需NPU复测。
