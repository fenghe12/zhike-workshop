# 智课工坊 · Smartcourse

[English](README.md) | 简体中文

课程生成与多语言数字人视频系统，包含 Vue 工作台、Python 后端、微信小程序源码、Ascend NPU 兼容修改和恢复工具。

主要流程：课件与讲稿 → 翻译 → 语音 → 带时间信息的字幕 → 数字人 → 课程视频。课程资料、任务状态、结果下载和知识库功能也在源码中。

## 启动

```bash
git clone https://github.com/fenghe12/zhike-workshop.git
cd zhike-workshop
cp .env.example .env
# 编辑 .env，将运行目录和模型路径指向持久化磁盘
bash scripts/setup-local.sh
bash scripts/start-local.sh
```

工作台地址为 `http://127.0.0.1:18770`。完整生成需要配置模型和媒体服务。安装与恢复步骤见 [恢复说明](docs/RECOVERY.zh-CN.md)。

## 目录

| 位置 | 内容 |
| --- | --- |
| `backend/smartcourse` | 后端 API、五阶段课程处理、翻译、语音、字幕、视频和相关测试 |
| `vue-app` | Vue 3 / TypeScript 工作台及锁定的 npm 依赖 |
| `pages`、`services`、`utils` | 微信小程序源码 |
| `ui-adapter` | 课件预览与前后端适配 |
| `scripts` | 持久化环境、安装、启动和模型/OBS 下载工具 |
| `recovery` | 模型目录、依赖版本、NPU 兼容文件、构建和启动脚本 |

## 当前验证状态

2026-10-21 已完成中文、英语、日语、韩语、德语、法语六种单页短课的实际生成，检查了翻译标题、数值、字幕覆盖、字幕时间和视频音轨。结果记录见 [验收记录](docs/acceptance-20261021.json)。完整长课程尚未在此次验收中复测。

2026-10-22 已使用原课件完成 12 页日语开篇课节，包括课件翻译、配音、86 条带时间信息的字幕、数字人视频及最终合成。视频时长 10 分 4.8 秒，分辨率为 1920 × 1080，详见[课程验证记录](docs/acceptance-20261022.json)。本次范围为开篇课节，尚未覆盖整章或整学期课程。

Qwen3.6 主模型、CosyVoice3 和 FlashHeadLite 使用 Ascend 910B。FFmpeg 合成和 Whisper 字幕对齐在本机执行。当前计算资源已停止，数据盘和 OBS 备份保留。

2026-10-22 至 23 日，Qwen3.6 生成了一份 8 页中文课件，经内容审阅后，将同一份源课件翻译为英语、日语、韩语、德语、法语和俄语。已检查算例、AND 真值表、阈值等号条件、中文残留、缺字、正文完整显示和逐页排版。具体修改和测试范围见[生成与翻译记录](docs/acceptance-20261022-generation-translation.json)。本次使用可编辑的标题与正文模板，未测试音视频生成及网页交互。

模型权重、Python 环境、生成视频、登录数据和个人参考素材不进入 Git。大文件下载来源和私有 OBS 对象位置保存在 `recovery/models.json`。

另有 [SenseNova U1.5 与 AgentHOI 恢复工具](recovery/sensenova-agenthoi/README.zh-CN.md)，保留官方推理案例及默认采样参数，包含昇腾单卡兼容修改和独立的 OBS 模型、运行环境备份位置。

[离线报告视频预览工具](recovery/reporting/README.zh-CN.md)将视频与预览图内嵌到同一个 HTML，并保留原始视频数据。

[AD-NeRF 恢复工具](recovery/adnerf/README.zh-CN.md)使用官方 Obama 预训练模型、原始 DeepSpeech 音频特征和 300 帧重建配置，在单张昇腾卡上执行。

[视频训练适配文件](recovery/video-training/README.zh-CN.md)记录了昇腾单卡上的 EasyAnimate V3 与 Wan2.2 S2V 短程训练，包含反向传播、实际参数更新、原有条件分支及私有检查点恢复。

[DiTalker/CogPortrait适配代码与记录](recovery/ditalker-cogportrait/README.zh-CN.md)现已加入[正确的最后输出层零初始化50例100步训练](recovery/ditalker-cogportrait/sessions/ditalker-gradient-repair-50hdtf-100steps-20261025/README.zh-CN.md)：11/11组均有非零梯度并实际更新，908/908个新增张量曾获得非零梯度。此前全部参数置零属于理解错误，历史记录保留。统一离线HTML合并完整loss、曲线、诊断和真实预览。CogPortrait仍限于姿态分支。

[高教社配置归档](integrations/hep/README.zh-CN.md)保留已有智能体提示词与旧插件参数约定，不修改高教社平台，也不重新部署云端入口。

10 月 25 日源码更新还包括账号隔离、持久化的 3 至 5 工作进程任务队列与媒体资源互斥、课件备注与字体处理、字幕分行，以及韩语和日语语音修正。教师听感和教学内容验收待进行，已实测范围见对应日期的恢复记录。

## 权利说明

本仓库暂未授予统一的开源许可证。第三方代码和模型遵循各自许可证，原始许可证应随恢复的来源代码保留。公开可读取不等同于授予任意再分发权限。

## 开发检查

```bash
cd backend/smartcourse
python -m unittest tests.test_app tests.test_pptx_notes tests.test_pptx_translation tests.test_translation_policy tests.test_speech_chunks tests.test_subtitle_validation
cd ../../vue-app
npm run build
```

2026-10-25：上述 55 项后端检查及前端生产构建通过。DiTalker 源码补丁已实际应用并与执行源码直接逐文件比较。新机器仍需按恢复说明准备依赖与模型。
