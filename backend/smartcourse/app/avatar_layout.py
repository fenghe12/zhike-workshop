"""Map the approved avatar rectangle to the rendered slide coordinates."""
import math


def map_avatar_box(box, canvas_width, canvas_height, face_width, face_height):
    source_width = float(box["img_w"])
    source_height = float(box["img_h"])
    x, y = float(box["x_px"]), float(box["y_px"])
    width = float(box.get("width_px", box.get("size_px", 0)))
    height = float(box.get("height_px", box.get("size_px", 0)))
    values = [source_width, source_height, x, y, width, height, canvas_width, canvas_height, face_width, face_height]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("数字人边界框包含无效数值")
    if min(source_width, source_height, width, height, canvas_width, canvas_height, face_width, face_height) <= 0:
        raise ValueError("数字人边界框尺寸必须为正数")
    if x < 0 or y < 0 or x + width > source_width or y + height > source_height:
        raise ValueError("数字人边界框超出页面范围")
    sx, sy = canvas_width / source_width, canvas_height / source_height
    left, top = round(x * sx), round(y * sy)
    right, bottom = round((x + width) * sx), round((y + height) * sy)
    scale = min((right - left) / face_width, (bottom - top) / face_height)
    rendered_width, rendered_height = int(face_width * scale), int(face_height * scale)
    if min(rendered_width, rendered_height) < 1:
        raise ValueError("数字人边界框小于一个像素")
    return (left + (right - left - rendered_width) // 2,
            top + (bottom - top - rendered_height) // 2,
            rendered_width, rendered_height)
