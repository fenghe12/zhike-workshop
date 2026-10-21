# 持久化恢复

[English](RECOVERY.md) | 简体中文 · [项目首页](../README.zh-CN.md)

## 本地应用

1. 克隆仓库，复制 `.env.example` 为 `.env`，将运行目录设置到可写的持久化磁盘。
2. 安装 Python 3.13、Node.js、FFmpeg 和 LibreOffice。执行 `bash scripts/setup-local.sh`。
3. 设置参考音频、参考照片、Whisper small 模型及 CJK 字体路径。参考素材由使用者提供，公开仓库不含个人素材。
4. 执行 `bash scripts/start-local.sh`，浏览器访问 `http://127.0.0.1:18770`。应用数据、产物和日志均保存在运行目录。

## 华为云 Ascend 910B

当前验证组合为 PyTorch 2.7.1 / torch_npu 2.7.1、Python 3.11、CANN 8.3 RC1、ARM64。云镜像：`pytorch_2.7.1-cann_8.3.rc1-py_3.11-hce_2.0.2509-aarch64-snt9b`。

先确认 `/home/ma-user/work` 的 EVS 实际挂载且可写，再在其下恢复 `npu-migration` 和 `smartcourse`。模型、Python 环境、CANN、缓存、临时目录、编译目录和日志均放在该卷。

私有 OBS 中已有原始代码存档、模型和可工作的 CANN 运行档案。对象位置见 `recovery/models.json`。桶名称及访问凭据由使用者通过本机环境提供，公开仓库不保存访问凭据。

使用 `scripts/restore-obs.py` 下载 `--group code` 或 `--group qwen`。代码档案中还保留其他 baseline 的源代码，目录清单见 `recovery/catalogs`。该清单代表已恢复的来源，不表示每个 baseline 已完成当前硬件推理。

原始代码档案恢复至 `npu-migration` 后，将 `recovery/npu-overlay` 覆盖至相同目录结构。原始第三方许可证必须保留。最新 NPU 兼容文件也已单独保存在此仓库中。

CosyVoice 和 FlashHead 使用独立依赖目录。CosyVoice 的 transformers 必须为 4.51.3、tokenizers 为 0.21.1；FlashHead 使用 4.57.3 / 0.22.1。详细已用版本见 `recovery/environment-versions.json`。不要将旧合并依赖表直接用于两个模型。

Qwen 主模型使用 NPU，视觉投影模块使用 CPU。`recovery/huawei/start_qwen36_npu.sh` 为已验证的启动参数。CANN 8.3 需要移除未使用的 recurrent gated delta rule 头文件引用，设置 OPP 的数据链接，并预加载对应 ARM64 `liboptiling.so`。保留的源代码修改及构建脚本位于 `recovery/huawei`。

Notebook 每次启动后 SSH 端口可能变化。将最新地址填写至运行目录的 `remote-state.json`，结构见 `config/remote-state.example.json`。只在平台确实显示运行时填写 RUNNING。

建立 SSH 转发，将云端 7812 转发到本机 17813，使用 `.env` 中的本地 Qwen 地址。远端 CosyVoice / FlashHead 路径由 `.env` 配置。应用使用逻辑设备 npu:0，物理卡分配由本次 Notebook 环境决定。

## 费用与数据

停止 Notebook 计算后，保留的 EVS 和 OBS 仍可能计费。2026-10-21 验收结束时 CPU 与 NPU 均已停止。仓库脚本不会自动创建、启动或删除云资源。

GitHub 保存代码和恢复配方，私有 OBS 保存大模型、运行档案和生成产物。重新租用同一镜像后仍需安装或恢复依赖；当前没有在全新空白实例上再次完成整套恢复验收。

恢复下载示例（先 source scripts/persistent-env.sh，安装 requirements/recovery.txt）：

```bash
python scripts/restore-obs.py --group code --destination /path/to/persistent/archives
python scripts/restore-obs.py --group course-models --destination /home/ma-user/work/npu-migration
python scripts/restore-obs.py --group qwen --destination /home/ma-user/work/npu-migration
python scripts/configure-npu.py
```

下载工具只下载文件。解压前使用 tar -tzf 查看目录结构，将原始代码恢复到对应目录，先解压原始档案，再解压较新的运行档案。环境目录未包含在原始代码备份中，需要从匹配镜像复制到 EVS，并安装已记录的依赖。
