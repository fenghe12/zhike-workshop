# 华为云程序更新与性能优化

适用于已有的 `/srv/smartcourse` 网页 ECS 和按需恢复的 Ascend 计算环境。应用源码与网页前端可以打包到私有 OBS；OBS 中存在更新包不代表正在运行的网页已经部署。原网页 ECS 关机时，只能核实云资源状态和备份内容，不能完成线上接口或 NPU 推理检查。

## 本次代码调整

- 课程工作区提供课程记忆、账号教学偏好、反馈修订、协作审阅、版本发布、学习记录、模板批量创建和 SCORM 1.2 导出。模板复制仅处理参考声音和讲者照片，另行保留素材授权记录。
- `SMARTCOURSE_PPT_GENERATOR=deeppresenter-native` 使用 DeepPresenter-9B 权重生成逐页课程内容与讲稿，再由本项目输出 PPTX。它属于本项目的模型适配入口，不代表官方 PPTAgent 工具调用流程已经完整部署。模型进程由任务启动，并在生成后停止；源课件材料为可选输入。
- 本地 Qwen Chat Completions 接口的 JSON 请求启用结构化输出，保留原有局部重试。已有 PPT 重新打包后，逐段输入完全相同的翻译记录仍可复用；文字发生变化的批次重新翻译。
- 语音工作进程通过 `SMARTCOURSE_SESSION_TMP` 使用数据卷上的短临时目录，避免 Python 多进程创建的 Unix socket 路径超过系统长度限制。运行包装脚本之后仍重新设置该目录。
- FlashHead 原始生成文件须为 25 FPS，检查发生在视频规范化之前。旧缓存不包含生成帧率时重新生成；恢复环境时同步将模型配置的 `tgt_fps` 设为 25，避免把 20 FPS 的原始视频转换为 25 FPS 后当作生成验收通过。
- 修订目标语种的课件文字时，若修改内容未出现在译文讲稿和实际朗读讲稿中，则保留语音与数字人，仅重新合成视频。仅更新目标页面的文字对象，保留其余 PPT 内容，同步更新附带讲稿的可下载 PPT，并继承已确认的课程记忆；修改涉及朗读内容时仍从语音阶段处理。
- 远端语音会话传输 `app/speech_pacing.py` 及其导入依赖，并在会话专属的持久化目录配置 Python 模块、临时文件和缓存。模型仍由原来的每任务语音会话复用，不在用户之间共享参考声音。
- 字幕按每条文本生成一张透明图像，由 FFmpeg 依据原字幕时间叠加。保留字体、换行、圆角背景、人物避让区域、视频帧率和帧数。避免完整视频逐帧经过 Python 图像转换，以及生成额外的整段静音视频。
- `SMARTCOURSE_CAPTION_RENDERER=ffmpeg` 为新实现；`python` 保留原实现以供对照。失败时保留原视频和本任务日志，不接受帧数或帧率发生变化的结果。
- 云端 CPU 后端依赖加入语种检测和离线 IP 地域客户端；模型环境仍独立管理，不将后端依赖安装到 CosyVoice 或 FlashHead 环境。
- 更新包同时包含此前的管理后台、评分反馈、使用统计、视觉讲稿、JSON 重试及逐页恢复修改。

## 生成更新包

在工作区已有的持久化 Node 环境构建前端，然后运行：

```bash
python3 -B deploy/huawei/build_release.py --output '/已确认的持久化目录/smartcourse-web-update.tar.gz'
```

归档包含 `source/`、`www/` 和 `release.json`。不会包含生产账号、会话、课程文件、模型权重、SMTP 配置或 SSH 密钥。清单仅记录路径及文件长度。

## 现有 ECS 的部署顺序

1. 确认已授权的网页启动时限，检查 `/srv/smartcourse` 的实际挂载、可写性和剩余空间；将 `TMPDIR`、`TEMP`、`TMP` 设为 `/srv/smartcourse/tmp`，缓存设为 `/srv/smartcourse/cache`。不启动已经释放的 Notebook。
2. 读取 `/srv/smartcourse/config/app.env` 的现有目录配置，确认没有排队或执行中的课程。备份当前 `source/`、`www/`、应用状态、使用记录、管理名单及 Nginx 配置；SQLite 使用其备份接口。账号与课件不纳入新代码包。
3. 解包到 `/srv/smartcourse/releases/` 下的新目录，只使用其中的 `source/` 和 `www/` 更新程序和静态网页。保留 `/srv/smartcourse/config`、`runtime`、`assets`、`tls`、原 SSH 配置及模型连接状态。只停止和重新启动本应用的服务。
4. 在 `/srv/smartcourse/envs/api` 中更新 `backend/smartcourse/requirements-cpu.txt` 的 CPU 依赖。保留独立语音环境的 Transformers 4.51.3 与数字人环境的 4.57.3，不混合安装。
5. 准备 `/srv/smartcourse/runtime/adapter/service.json`，内容为 `{"base_url":"http://127.0.0.1:18771"}`，所属用户为 `smartcourse`，权限为 600。安装同目录的 `smartcourse-ui-adapter.service`。
6. 将已有 HTTPS 站点中 `/api/` 的 404 配置替换为 `nginx-api-location.conf` 的代理段。保留 `/v1/` 与 `/artifacts/` 的后端鉴权；不可把课程目录改为公开静态目录。将首页重定向调整为 `index.html`，原 `mobile.html` 继续保留。执行 Nginx 配置检查再重新加载。
7. 启动应用所属服务，检查网页、上传预览、注册登录、原课程播放、匿名文件访问拒绝及已授权管理账号。现有管理员名单继续使用；新增管理员通过 `python -m app.admin_access --account '已注册账号'` 设置。
8. 模型计算关闭时，应显示计算未就绪，不把网页健康检查当成推理验收。部署检查结束后，依照本次网页时限关闭 ECS。

## 后续云端优化顺序

| 项目 | 当前安排 | 云端验证要求 |
|---|---|---|
| CPU 字幕合成 | 新图像复用与 FFmpeg 叠加已实现 | 对同一输入比较耗时、峰值内存、帧数、音视频时长及八语种显示 |
| 语音会话 | 每次课程执行只建立一个任务专属会话 | 检查模型加载次数、英语语速检测和参考声音隔离 |
| 生成并发 | 优先使用 3 个课程工作进程，单卡语音和数字人共享一个计算名额 | 根据实际设备内存评估；不因网页并发数提高而同时执行多个数字人进程 |
| S3 与 S4 重叠 | 保留可配置能力，默认不开启 | 在指定模型、分辨率和卡容量下采样内存后再启用；此前 64 GB 测量不适用于 32 GB 卡 |
| 断点恢复 | 复用任务自有且输入一致的课件、音频和数字人结果 | 检查中断后只处理缺失或变化的页面 |
| 闲置计算 | 保留原生到时停止、预算检查和空闲停止 | 新建算力前确认预算和停止时间，不重新启用已结束的旧租期 |
| 持久化恢复 | 最新源码与独有结果保存于私有 OBS | 停机不自动终止保留盘费用；是否释放存储需单独授权，保留已有备份 |

字幕对照采用同一 20 秒实际课程片段；本机结果不代表华为云上的完整课程加速比。该实现使用 FFmpeg 的 [concat 解复用](https://ffmpeg.org/ffmpeg-formats.html#concat-1)与 [overlay 滤镜](https://ffmpeg.org/ffmpeg-filters.html#overlay)。ModelArts 停止与存储计费关系参见[华为云计费说明](https://support.huaweicloud.com/price-modelarts/price-modelarts-0010.html)。
