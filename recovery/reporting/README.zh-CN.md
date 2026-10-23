# 离线视频预览

[English](README.md) | 简体中文

`embedded_video_previews.py` 为已将 MP4 视频保存为 data URL 的 HTML 添加内嵌 JPEG 预览图。保留原始视频数据，写入实际视频尺寸以防止页面位置变化，并避免打开页面时同时加载全部视频。视频与预览图均保存在同一个 HTML 中。

需要 Python 3、`ffmpeg` 和 `ffprobe`。所有报告章节生成完成后调用此函数，并指定可写的持久化媒体目录：

```python
from pathlib import Path
from embedded_video_previews import add_embedded_video_previews

report = Path("/persistent/reports/results.html")
updated = add_embedded_video_previews(
    report.read_text(), media_directory=report.parent / "offline-video-media"
)
report.write_text(updated)
```

本地迁移报告已检查 25 段原始 H.264/yuv420p 视频及 25 张内嵌预览图。AgentHOI 视频在内置浏览器中实际播放，时间正常推进。该浏览器的地址策略禁止直接打开 `file:` 地址，因此播放验证使用原 localhost 页面，并通过媒体引用检查确认全部内容已内嵌。
