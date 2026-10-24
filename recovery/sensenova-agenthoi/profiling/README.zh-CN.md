# AgentHOI NPU 逐层性能分析

[English](README.md) | 简体中文

[10 月 24 日实测记录](../../../docs/agenthoi-layer-profile-20261024.json)确认单张昇腾 910B1 实际执行了 `aclnnFlashAttentionScore` 设备内核。正常步骤平均 24.52 秒；40 个 Transformer 层每层平均 606.8 毫秒，包含每步条件、无条件两次前向。

此启动器复用 `/home/ma-user/work/npu-migration` 下的持久化环境及已保存的官方 `case_a` 推理结果。使用前恢复此前完整推理的结果归档，将这些文件放入该根目录下的 `recovery/agenthoi-layer-profile-20261024`，再执行 `bash run_profile.sh`。云实例启动和停止由独立控制程序处理，使用时应设置时长上限并在收集结果后停机。

保留原始 81 帧、40 步、CFG 5、shift 5 和 seed 42，不修改共享模型源码。第 3 步记录整层、自注意力、交叉注意力和前馈网络的设备流时间区间；第 4 步采集实际 CPU/NPU 算子；第 5 步记录位置编码与 SDPA 时间。各层之间不插入设备同步。正常步骤均值排除首步及这些分析步骤。

模块时间包含内部调用，也可能包含主机工作造成的设备等待。位置编码和 SDPA 已包含在注意力时间内，不能重复相加。每类数据仅采样一个预热后的步骤。`analyze_results.py` 可在本地解析收集的 JSON 与性能记录 CSV。

启动器使用较短的持久化临时目录，避免 CANN 创建多进程管理器时超过 Unix 套接字路径长度限制。性能工具目录应优先于通用 CANN `bin` 目录。此次自动导出因通用路径失败，随后使用持久化工具包中的 `tools/profiler/bin/msprof --export=on --output=<PROF_directory>` 成功导出原始记录。应检查实际生成的 `op_summary` CSV，再判断所用注意力后端。
