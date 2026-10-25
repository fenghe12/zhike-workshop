# AscendBridge 实际流程试验 · 2026-10-25

[English](README.md)

本次流程未完成。两个适配和评测脚本均通过官方源码检查，但没有有效的50输入NPU指标，完整完成检查仍未通过。没有报告视频质量、CUDA数值精度或模型性能结论。

已下载的SLAI-AscendBridge2源码README标注版本2.5。原生Claude客户端的两份既有Kimi配置均返回401。本次按源码支持的Codex AGENTS入口执行适配与评测角色，不能称为原生Claude自动编排成功。工具源码：https://gitcode.com/SLAI/SLAI-AscendBridge2

验证对象为完整原始预训练EasyAnimate V3和Wan2.2 S2V主干，不包含DiTalker或CogPortrait新增部件。计划使用50个不同HDTF512×512、16帧输入的原生latent，执行单个去噪时间步前向，不包含完整视频采样和解码。本次未完成50输入。

## 实际失败与修正

CANN初始化时Python进程通信报`OSError: AF_UNIX path too long`，随后返回ACL500001，尚未进入有效模型前向。仅更新TMPDIR不能清除Python此前缓存的长路径。现已将启动前临时目录设为已确认持久化数据盘上的短路径，并显式更新`tempfile.tempdir`。本地进程通信复现了旧错误，显式清除缓存后通信通过。最终修正尚未在NPU复测，不能将该问题归为模型算子不支持。

## 文件与运行

将adaptations目录复制到对应Bridge源码目录。run_remote.sh和run_models.py顺序执行两模型，并调用未修改的官方适配、评测检查器。各模型accuracy_run.py使用`--use-pretrained --max-samples 50`读取真实权重，仅加载一次模型，再执行一次真实demo前向、两次预热与50输入评测。实际成功后才会生成指标、trace和小型输出统计文件。

复用的持久化环境为Python3.11、torch2.7.1+cpu、torch_npu2.7.1、CANN8.3rc1、diffusers0.35.2、transformers4.53.1、accelerate1.12.0、safetensors0.4.5。torch版本的cpu后缀不表示模型已使用CPU回退。uv.lock由解析器实际生成；新建隔离环境安装尚未验证。本次未修改原模型环境。

build_trial_report.py保存本次状态，reproduce_tempdir.py仅验证本地进程通信修正。私有云状态、失败日志、模型权重、HDTF数据及整合报告未发布到公开仓库，保存在本地与私有OBS。既有DiTalker/CogPortrait训练记录保持独立。
