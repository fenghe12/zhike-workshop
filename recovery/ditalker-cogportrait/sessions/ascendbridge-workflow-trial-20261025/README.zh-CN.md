# AscendBridge 原生Qwen试验 · 2026-10-25

[English](README.md)

本次恢复的运行试验已通过：原生编码客户端使用自托管Qwen3.6-35B-A3B Q8生成方案、调用真实执行工具并核对实际结果。两个完整原始预训练主干均完成50个不同HDTF输入，通过未修改的适配与评测检查器。成功执行未使用Kimi或外部语言模型接口。

| 模型 | 不同输入 | 平均同步前向 | 测量阶段峰值已分配设备内存 |
|---|---:|---:|---:|
| EasyAnimate V3 |50|0.292390秒|7.1964GiB|
| Wan2.2 S2V-14B |50|1.269906秒|32.3737GiB|

硬件为单张昇腾910B2。原始输入512×512、16帧，测量对象为其原生VAE latent的单个去噪时间步，保留完整原始主干。耗时包含输入传输、噪声与条件准备，不包含文件读取、输出统计及模型加载。设备内存为两次预热后50次测量中的峰值。本次未评估完整视频采样、解码、视频质量或匹配条件的CUDA数值对照。

实际使用README标注为2.5的Bridge源码：https://gitcode.com/SLAI/SLAI-AscendBridge2 。原生客户端以单工作进程顺序继续既有适配，实际调用三次Bash工具，完成方案写入、真实模型执行和结果核对。工作工具仅停止本任务Qwen，顺序执行两模型，再恢复Qwen供结果核对。未启动多智能体团队，也未声称从原始CUDA源码重新完成全自动迁移。

历史失败包括Kimi401、CANN进程通信路径过长和原生客户端上下文超限，记录保存在本地与私有OBS。最终修正为Python启动前短持久化TMPDIR、显式重置tempfile.tempdir、64K Qwen上下文及精简任务说明。真实NPU进程通信和矩阵计算检查均通过。

独立环境重建验收未执行：上游verify_environment.py计算文件校验值，与用户当前AGENTS.md要求冲突。原检查器未修改，正式看板仍为in_progress；本次真实运行结果不代表新隔离环境安装已通过。

复现需将adaptations复制到对应Bridge完整源码的framework/adaptations中，准备已有持久化权重、真实HDTF缓存及Python3.11、torch2.7.1+cpu、torch_npu2.7.1、CANN8.3rc1环境。uv.lock由解析器生成。cloud_session.py为可配置的公开控制器模板，将cloud-config.example.json复制为cloud-config.private.json并填写自己的账号及凭据文件路径，保持该配置私有。qwen-task.txt的{{SESSION_ROOT}}由启动器替换。还需要已安装的原生编码客户端和Huawei ModelArts SDK。权重、数据、私钥、真实账号配置及完整日志未公开，保存在私有OBS。实际数值、Qwen方案和核对记录见../../records/ascendbridge-workflow-20261025/。
