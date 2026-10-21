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

Qwen3.6 主模型、CosyVoice3 和 FlashHeadLite 使用 Ascend 910B。FFmpeg 合成和 Whisper 字幕对齐在本机执行。当前计算资源已停止，数据盘和 OBS 备份保留。

模型权重、Python 环境、生成视频、登录数据和个人参考素材不进入 Git。大文件下载来源和私有 OBS 对象位置保存在 `recovery/models.json`。

## 权利说明

本仓库暂未授予统一的开源许可证。第三方代码和模型遵循各自许可证，原始许可证应随恢复的来源代码保留。公开可读取不等同于授予任意再分发权限。

## 开发检查

```bash
cd backend/smartcourse
python -m unittest tests.test_course_api tests.test_remote_media_status tests.test_translation_policy tests.test_speech_timing tests.test_pptx_translation
cd ../../vue-app
npm run build
```

2026-10-21：上述 20 项后端检查与前端构建通过。新机器仍需按恢复说明准备依赖与模型。
