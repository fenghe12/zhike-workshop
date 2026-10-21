"""Check measured speech timestamps before subtitle serialization."""
import math


def validate_timestamps(segments: list[dict], duration: float) -> None:
    if not math.isfinite(duration) or duration <= 0 or not segments:
        raise ValueError("音频时长或字幕时间戳为空或无效")
    previous_end = 0.0
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        if not str(segment.get("text", "")).strip():
            raise ValueError("字幕内容为空")
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("字幕时间戳不是有限数值")
        if start < previous_end or end <= start or end > duration:
            raise ValueError("字幕时间戳重叠、顺序错误或超出音频时长")
        previous_end = end
