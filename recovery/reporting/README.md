# Offline video previews

English | [简体中文](README.zh-CN.md)

`embedded_video_previews.py` adds embedded JPEG previews to an HTML report whose MP4 videos are already stored as data URLs. It preserves the original video bytes, records video dimensions to prevent layout shifts, and avoids loading every video when the page opens. Both the video and its preview remain inside the HTML.

Python 3, `ffmpeg` and `ffprobe` are required. Call the helper after building all report sections, with a writable persistent media directory:

```python
from pathlib import Path
from embedded_video_previews import add_embedded_video_previews

report = Path("/persistent/reports/results.html")
updated = add_embedded_video_previews(
    report.read_text(), media_directory=report.parent / "offline-video-media"
)
report.write_text(updated)
```

The local migration report was checked with 25 unchanged H.264/yuv420p videos and 25 embedded previews. AgentHOI playback advanced normally in the in-app browser. Direct `file:` navigation was blocked by that browser's URL policy; playback was verified through the original localhost page, and media references were checked for self-contained data URLs.
