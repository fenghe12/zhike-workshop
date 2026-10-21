"""
S4 Bounding Box Agent (MLLM Vision-based Layout Decision)
输入: PPT文件
输出: bbox.json (每页数字人位置+尺寸)

流程: LibreOffice导出截图 → MLLM看图决定位置 → 输出bbox
"""

import os
from pathlib import Path
# ==================== 统一配置加载 ====================
import yaml as _yaml
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AGENT_DIR, "config.yaml"), "r") as _cf:
    _CFG = _yaml.safe_load(_cf)

import os
import json
import uuid
import httpx
import asyncio
import base64
import random
import logging
import re
import subprocess
import glob
import shutil
from typing import List, Dict, Any, Optional
from PIL import Image as PILImage
import io

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BBoxAgent")

# -----------------------------
# Config
# -----------------------------
VL_MODEL = os.environ.get("SMARTCOURSE_GATEWAY_MODEL", "azure-gpt-5_2")
VL_API_URL = os.environ.get(
    "SMARTCOURSE_GATEWAY_URL",
    "https://llm-gateway-proxy.inner.chj.cloud/llm-gateway/v1/responses",
)

TEXT_MODEL = "kivy-qwen3_6-plus"
TEXT_API_URL = f"http://api-hub.inner.chj.cloud/llm-gateway/v1/chat/completions/{TEXT_MODEL}"

MAX_TOKENS = 4096
ENABLE_THINKING = False

GW_TOKEN = os.environ.get(_CFG['api'].get('gw_token_env', 'SMARTCOURSE_GW_TOKEN'), '')

REQUEST_TIMEOUT_SEC = 120.0
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 2.0
MAX_BACKOFF_SEC = 15.0

WORKSPACE_ROOT = os.environ.get("SMARTCOURSE_WORKSPACE_ROOT", _CFG['paths']['workspace'])

# Digital human default size (pixels, square, can be scaled down)
AVATAR_SIZE_PX = 512

# Slide export DPI (controls screenshot resolution)
EXPORT_DPI = 150

# Test PPT
TEST_PPTX = ""


# =====================================================
# Gateway API (supports both text and vision models)
# =====================================================
def normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text", "")
                if t:
                    parts.append(str(t))
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"]).strip()
        return json.dumps(content, ensure_ascii=False)
    return str(content).strip()


def extract_first_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    for sc, ec in [("{", "}"), ("[", "]")]:
        start = text.find(sc)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == sc:
                    depth += 1
                elif ch == ec:
                    depth -= 1
                    if depth == 0:
                        return text[start: i + 1]
    return text


def should_retry_exception(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        c = exc.response.status_code
        return c == 429 or 500 <= c < 600
    return False


async def call_vl_api(
    messages: List[Dict],
    client: httpx.AsyncClient,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Call the vision-language model API."""
    if not GW_TOKEN:
        raise ValueError("GW token not found.")

    headers = {
        "Content-Type": "application/json",
        "BCS-APIHub-RequestId": str(uuid.uuid4()),
        "X-CHJ-GWToken": GW_TOKEN,
    }
    content = []
    for message in messages:
        value = message.get("content", "")
        if isinstance(value, str):
            content.append({"type": "input_text", "text": value})
            continue
        for item in value:
            if item.get("type") in {"text", "input_text"}:
                content.append({"type": "input_text", "text": str(item.get("text", ""))})
            elif item.get("type") in {"image_url", "input_image"}:
                image = item.get("image_url", "")
                if isinstance(image, dict):
                    image = image.get("url", "")
                content.append({"type": "input_image", "image_url": str(image)})
    payload = {
        "model": VL_MODEL,
        "input": [{"role": "user", "content": content}],
        "stream": False,
        "reasoning": {"effort": "medium", "summary": "detailed"},
        "max_output_tokens": MAX_TOKENS,
    }

    for attempt in range(max_retries):
        try:
            resp = await client.post(VL_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            texts = []
            for output in data.get("output", []):
                for item in output.get("content", []):
                    if isinstance(item.get("text"), str):
                        texts.append(item["text"])
            if not texts and data.get("choices"):
                texts.append(normalize_message_content(data["choices"][0]))
            if not texts:
                raise ValueError("Responses gateway returned no text")
            return "\n".join(texts)
        except Exception as e:
            logger.warning(f"VL API fail (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise
            if should_retry_exception(e):
                delay = min(BACKOFF_BASE_SEC * (2 ** attempt), MAX_BACKOFF_SEC) + random.uniform(0, 1)
                await asyncio.sleep(delay)

    raise RuntimeError("Unreachable")


# =====================================================
# PPT → Images (LibreOffice)
# =====================================================
def export_pptx_to_images(pptx_path: str, output_dir: str) -> List[str]:
    if Path(pptx_path).suffix.lower()=='.pdf':
        from app.pdf_render import render_pdf_pages
        return render_pdf_pages(pptx_path,output_dir)
    from app.pptx_render import render_pptx
    return render_pptx(pptx_path, output_dir)


def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 150) -> List[str]:
    """Convert PDF pages to PNG images."""
    image_paths = []

    try:
        # Try pdf2image (poppler-based)
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi)
        for i, img in enumerate(images):
            img_path = os.path.join(output_dir, f"slide_{i+1:03d}.png")
            img.save(img_path, "PNG")
            image_paths.append(img_path)
            logger.info(f"  Slide {i+1}: {img.size[0]}x{img.size[1]}px → {img_path}")

    except ImportError:
        logger.warning("pdf2image not available, trying PyMuPDF...")
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img_path = os.path.join(output_dir, f"slide_{i+1:03d}.png")
                pix.save(img_path)
                image_paths.append(img_path)
                logger.info(f"  Slide {i+1}: {pix.width}x{pix.height}px → {img_path}")
            doc.close()

        except ImportError:
            logger.warning("PyMuPDF not available, trying Pillow-based conversion...")
            # Last resort: use LibreOffice to export directly to images
            # This produces one image (first page only in some versions)
            # Not ideal but works as fallback
            raise RuntimeError(
                "No PDF-to-image library found. Install one:\n"
                "  pip install pdf2image   (requires poppler: apt install poppler-utils)\n"
                "  pip install PyMuPDF\n"
            )

    return sorted(image_paths)


def local_decide_position(
    image_path: str,
    occupied: List[tuple[int, int, int, int]],
    avatar_size_px: int,
) -> Dict:
    """Choose a bottom-corner region with minimum overlap against PPT elements."""
    with PILImage.open(image_path) as image:
        img_w, img_h = image.size

    def overlap_area(box, region):
        left = max(box[0], region[0])
        top = max(box[1], region[1])
        right = min(box[2], region[2])
        bottom = min(box[3], region[3])
        return max(0, right - left) * max(0, bottom - top)

    candidates = []
    maximum = min(avatar_size_px, int(img_h * 0.42), int(img_w * 0.28))
    sizes = sorted({maximum, int(maximum * 0.85), int(maximum * 0.70), 200}, reverse=True)
    margin = max(8, round(img_w * 0.006))
    for size in sizes:
        size = max(200, min(size, maximum))
        for side in ("bottom-right", "bottom-left"):
            x = img_w - size - margin if side.endswith("right") else margin
            y = img_h - size - margin
            box = (x, y, x + size, y + size)
            overlap = sum(overlap_area(box, region) for region in occupied)
            overlap_ratio = overlap / max(1, size * size)
            candidates.append((overlap_ratio, -size, 0 if side.endswith("right") else 1, x, y, size, side))
    overlap_ratio, _negative_size, _side_order, x, y, size, side = min(candidates)
    layout_mode = "overlay"
    content_width = img_w
    subtitle_region=(0, img_h*.84, img_w*.74, img_h)
    subtitle_overlap=any(overlap_area(subtitle_region,region)>0 for region in occupied)
    if overlap_ratio > 0 or subtitle_overlap:
        layout_mode = "side_panel"
        content_width = round(img_w * 0.74)
        size = min(round(img_w * 0.22), round(img_h * 0.5))
        x, y = img_w - size - margin, img_h - size - margin
        side = "right-side-panel"
    return {
        "x_px": x,
        "y_px": y,
        "size_px": size,
        "img_w": img_w,
        "img_h": img_h,
        "x_norm": round(x / img_w, 4),
        "y_norm": round(y / img_h, 4),
        "size_w_norm": round(size / img_w, 4),
        "size_h_norm": round(size / img_h, 4),
        "position_description": side,
        "reason": f"本地页面结构分析选择内容重叠率最低的底部区域，重叠率 {overlap_ratio:.4f}",
        "overlap_ratio": round(overlap_ratio, 4),
        "analysis_method": "pptx_geometry",
        "layout_mode": layout_mode,
        "slide_content_width_px": content_width,
        "slide_content_height_px": round(img_h*.84) if layout_mode=='side_panel' else img_h,
    }


# =====================================================
# Image → Base64
# =====================================================
def image_to_base64(image_path: str, max_size: int = 1920) -> str:
    """Load image, resize if too large, return base64 string."""
    img = PILImage.open(image_path).convert("RGB")

    # Resize if too large (save bandwidth)
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), PILImage.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, img.size


# =====================================================
# MLLM Position Decision
# =====================================================
async def mllm_decide_position(
    image_path: str,
    slide_number: int,
    avatar_size_px: int,
    client: httpx.AsyncClient,
) -> Dict:
    b64_image, (img_w, img_h) = image_to_base64(image_path)

    prompt_text = (
        f"This is a screenshot of slide {slide_number} from a MOOC (online course) presentation.\n"
        f"The image resolution is {img_w}×{img_h} pixels.\n\n"
        "CONTEXT: This slide will be used in a MOOC teaching video. "
        "A digital human teacher avatar will be overlaid on the slide, "
        "similar to how a real teacher stands in front of a blackboard or screen.\n\n"
        f"The avatar is a square image, default size {avatar_size_px}×{avatar_size_px} pixels.\n"
        f"It CAN be scaled down proportionally (minimum 200×200 pixels) if space is tight.\n\n"
        "STRICT RULES (in priority order):\n"
        "1. ABSOLUTELY DO NOT cover any text, titles, subtitles, labels, or any readable content. "
        "This is the highest priority. If the avatar overlaps with ANY text, it is a failure.\n"
        "2. DO NOT cover important visual elements: charts, diagrams, images, icons, tables.\n"
        "3. The avatar MUST be at the BOTTOM of the slide. "
        "Think of it like a teacher standing in front of a screen — teachers stand at the bottom, not floating in the air. "
        "The avatar's bottom edge should be near the bottom edge of the slide (within 30 pixels).\n"
        "4. The avatar should be as close to the EDGE as possible (left edge or right edge). "
        "Do not place it in the middle of the slide.\n"
        "5. Prefer BOTTOM-RIGHT corner. If bottom-right has text/content, try BOTTOM-LEFT.\n"
        "6. If both bottom corners have content, scale the avatar DOWN to fit in the remaining gap.\n"
        "7. If absolutely no space at the bottom, use the smallest possible size (200×200) at the bottom-right edge.\n\n"
        "PLACEMENT STRATEGY:\n"
        "- First, identify ALL text regions on the slide (titles, body text, labels, captions).\n"
        "- Then, find the largest empty gap at the bottom edge of the slide.\n"
        "- Place the avatar in that gap, touching the bottom edge.\n"
        "- The avatar's bottom edge Y coordinate should be close to the slide's bottom edge "
        f"(Y should be around {img_h - avatar_size_px} to {img_h - 200} depending on size).\n\n"
        "Return a JSON object:\n"
        "{\n"
        f'  "x": int (left edge in pixels, 0 to {img_w}),\n'
        f'  "y": int (top edge in pixels, avatar bottom should be near {img_h}),\n'
        '  "size": int (avatar size in pixels, 200 to ' + str(avatar_size_px) + '),\n'
        '  "position_description": "e.g. bottom-right corner, touching edge",\n'
        '  "reason": "explain what content you avoided and why this spot is safe"\n'
        "}\n"
        "Return ONLY the JSON object."
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_image}"
                    },
                },
            ],
        }
    ]

    raw = await call_vl_api(messages, client)
    json_str = extract_first_json_object(raw)

    try:
        result = json.loads(json_str)

        x = int(result.get("x", 0))
        y = int(result.get("y", 0))
        size = int(result.get("size", avatar_size_px))

        # Clamp size
        size = max(200, min(size, avatar_size_px))

        # Force bottom alignment: avatar bottom edge must be within 30px of slide bottom
        min_y = img_h - size - 30
        if y < min_y:
            logger.warning(f"Slide {slide_number}: MLLM placed avatar too high (y={y}), forcing to bottom (y={min_y})")
            y = min_y

        # Clamp to edges
        x = max(0, min(x, img_w - size))
        y = max(0, min(y, img_h - size))

        # Prefer touching edge: snap to nearest edge if close
        if x < img_w // 2:
            # Left half → snap to left edge
            if x < 50:
                x = 5
        else:
            # Right half → snap to right edge
            if x > img_w - size - 50:
                x = img_w - size - 5

        # Snap to bottom edge
        if y > img_h - size - 50:
            y = img_h - size - 5

        return {
            "x_px": x,
            "y_px": y,
            "size_px": size,
            "img_w": img_w,
            "img_h": img_h,
            "x_norm": round(x / img_w, 4),
            "y_norm": round(y / img_h, 4),
            "size_w_norm": round(size / img_w, 4),
            "size_h_norm": round(size / img_h, 4),
            "position_description": result.get("position_description", ""),
            "reason": result.get("reason", ""),
        }

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"MLLM parse failed: {e}, using bottom-right fallback")
        size = min(avatar_size_px, img_w // 4, img_h // 3)
        return {
            "x_px": img_w - size - 5,
            "y_px": img_h - size - 5,
            "size_px": size,
            "img_w": img_w,
            "img_h": img_h,
            "x_norm": round((img_w - size - 5) / img_w, 4),
            "y_norm": round((img_h - size - 5) / img_h, 4),
            "size_w_norm": round(size / img_w, 4),
            "size_h_norm": round(size / img_h, 4),
            "position_description": "bottom-right (fallback)",
            "reason": f"parse failed: {e}",
        }

# =====================================================
# BBox Agent
# =====================================================
class BBoxAgent:
    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root

    def run(
        self,
        task_id: str,
        pptx_path: str,
        avatar_size_px: int = AVATAR_SIZE_PX,
    ) -> Dict:
        return asyncio.run(self.arun(task_id, pptx_path, avatar_size_px))

    async def arun(
        self,
        task_id: str,
        pptx_path: str,
        avatar_size_px: int = AVATAR_SIZE_PX,
    ) -> Dict:
        logger.info(f"=== BBoxAgent START: task={task_id} ===")
        logger.info(f"PPT: {pptx_path}")
        logger.info(f"Avatar size: {avatar_size_px}×{avatar_size_px} px (can scale down)")

        output_dir = os.path.join(self.workspace_root, task_id, "s4_output")
        slides_dir = os.path.join(output_dir, "slide_images")
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(slides_dir, exist_ok=True)

        # Step 1: Export PPT to images
        logger.info("Step 1: Exporting PPT slides to images...")
        image_paths = export_pptx_to_images(pptx_path, slides_dir)
        total_slides = len(image_paths)

        if total_slides == 0:
            logger.error("No slides exported!")
            return {"error": "No slides exported"}

        logger.info(f"Exported {total_slides} slides")

        try:
            from ppt_renderer import occupied_regions
        except ImportError:
            from .ppt_renderer import occupied_regions
        is_pdf=Path(pptx_path).suffix.lower()=='.pdf'
        if is_pdf:
            slide_regions=[]
            for image_path in image_paths:
                with PILImage.open(image_path) as image:
                    slide_regions.append([(0,0,image.width,image.height)])
        else:
            slide_regions = occupied_regions(pptx_path, image_width=PILImage.open(image_paths[0]).size[0])

        logger.info("Step 2: Analyzing slide regions for avatar placement...")
        all_bboxes = []

        use_vision_gateway = not is_pdf and os.environ.get("SMARTCOURSE_BBOX_MODE", "geometry") == "vision" and bool(GW_TOKEN) and "api.kimi.com" not in VL_API_URL
        from contextlib import nullcontext
        async with (httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) if use_vision_gateway else nullcontext(None)) as client:
            for i, img_path in enumerate(image_paths):
                slide_num = i + 1
                logger.info(f"  Slide {slide_num}/{total_slides}: analyzing...")

                if use_vision_gateway:
                    try:
                        decision = await mllm_decide_position(
                            image_path=img_path,
                            slide_number=slide_num,
                            avatar_size_px=avatar_size_px,
                            client=client,
                        )
                        decision["analysis_method"] = "vision_gateway"
                    except Exception as exc:
                        logger.warning("Vision analysis unavailable, using PPT geometry: %s", exc)
                        decision = local_decide_position(img_path, slide_regions[i], avatar_size_px)
                else:
                    decision = local_decide_position(img_path, slide_regions[i], avatar_size_px)

                bbox = {
                    "slide_number": slide_num,
                    "slide_image": os.path.abspath(img_path),
                    **decision,
                }
                if is_pdf:
                    bbox.update(analysis_method='pdf_page_preservation',reason='保留完整 PDF 页面，在独立区域显示人物和字幕')
                all_bboxes.append(bbox)

                logger.info(
                    f"  Slide {slide_num}: "
                    f"({decision['x_px']}, {decision['y_px']}) "
                    f"size={decision['size_px']}px "
                    f"| {decision['position_description']}"
                )

        # Step 3: Save output
        logger.info("Step 3: Saving bbox.json...")

        output = {
            "task_id": task_id,
            "pptx_path": os.path.abspath(pptx_path),
            "avatar_default_size_px": avatar_size_px,
            "total_slides": total_slides,
            "bboxes": all_bboxes,
        }

        bbox_path = os.path.join(output_dir, "bbox.json")
        with open(bbox_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        logger.info(f"=== BBoxAgent DONE ===")
        logger.info(f"  Output: {bbox_path}")
        logger.info(f"  Slides: {total_slides}")

        # Summary
        sizes = [b["size_px"] for b in all_bboxes]
        positions = [b["position_description"] for b in all_bboxes]
        logger.info(f"  Avatar sizes: min={min(sizes)}px, max={max(sizes)}px")
        for i, b in enumerate(all_bboxes):
            logger.info(
                f"    Slide {b['slide_number']}: "
                f"pos=({b['x_px']},{b['y_px']}) "
                f"size={b['size_px']}px "
                f"norm=({b['x_norm']:.3f},{b['y_norm']:.3f}) "
                f"| {b['position_description']}"
            )

        return {
            "task_id": task_id,
            "bbox_path": bbox_path,
            "total_slides": total_slides,
        }


# =====================================================
# Visualization (optional: draw bbox on slides)
# =====================================================
def visualize_bboxes(bbox_json_path: str, output_dir: str) -> List[str]:
    """Draw avatar bounding boxes on slide images for verification."""
    from PIL import ImageDraw, ImageFont

    with open(bbox_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    viz_dir = os.path.join(output_dir, "bbox_viz")
    os.makedirs(viz_dir, exist_ok=True)

    viz_paths = []
    for bbox in data["bboxes"]:
        slide_img_path = bbox["slide_image"]
        if not os.path.exists(slide_img_path):
            continue

        img = PILImage.open(slide_img_path).convert("RGB")
        draw = ImageDraw.Draw(img)

        x, y = bbox["x_px"], bbox["y_px"]
        size = bbox["size_px"]

        # Draw red rectangle for avatar position
        draw.rectangle(
            [x, y, x + size, y + size],
            outline="red",
            width=3,
        )

        # Draw label
        label = f"Avatar {size}x{size}"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except Exception:
            font = ImageFont.load_default()

        draw.text((x + 5, y + 5), label, fill="red", font=font)

        # Draw cross at center
        cx, cy = x + size // 2, y + size // 2
        draw.line([(cx - 10, cy), (cx + 10, cy)], fill="red", width=2)
        draw.line([(cx, cy - 10), (cx, cy + 10)], fill="red", width=2)

        # Save
        viz_path = os.path.join(viz_dir, f"slide_{bbox['slide_number']:03d}_bbox.png")
        img.save(viz_path)
        viz_paths.append(viz_path)

    logger.info(f"Visualization saved: {viz_dir} ({len(viz_paths)} images)")
    return viz_paths


# =====================================================
# CLI
# =====================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="S4 BBox Agent (MLLM Vision-based)")

    parser.add_argument("--task-id", type=str, help="Task ID")
    parser.add_argument("--pptx", type=str, help="Path to PPTX file")
    parser.add_argument("--avatar-size", type=int, default=AVATAR_SIZE_PX,
                        help=f"Avatar size in pixels (default: {AVATAR_SIZE_PX})")
    parser.add_argument("--workspace", type=str, default=WORKSPACE_ROOT)
    parser.add_argument("--visualize", action="store_true",
                        help="Generate visualization images with bbox drawn on slides")

    # Test with built-in PPT
    parser.add_argument("--test", action="store_true",
                        help=f"Run test with {TEST_PPTX}")

    args = parser.parse_args()

    if args.test:
        task_id = "bbox_test"
        pptx_path = TEST_PPTX

        if not os.path.exists(pptx_path):
            print(f"Test PPT not found: {pptx_path}")
            print("Please provide --pptx path instead.")
            return

        print("\n" + "=" * 60)
        print(f"🧪 Running BBox test on: {pptx_path}")
        print("=" * 60)

        agent = BBoxAgent(workspace_root=args.workspace)
        result = agent.run(
            task_id=task_id,
            pptx_path=pptx_path,
            avatar_size_px=args.avatar_size,
        )

        print("\n" + "=" * 60)
        print("🧪 BBox Test Complete")
        print("=" * 60)
        print(f"  Task ID:      {result['task_id']}")
        print(f"  Total slides: {result['total_slides']}")
        print(f"  Output:       {result['bbox_path']}")
        print("=" * 60)

        # Print bbox details
        if os.path.exists(result["bbox_path"]):
            print("\n📄 BBox Results:")
            print("-" * 60)
            with open(result["bbox_path"], "r", encoding="utf-8") as f:
                data = json.load(f)
                for b in data["bboxes"]:
                    print(
                        f"  Slide {b['slide_number']:2d}: "
                        f"({b['x_px']:4d}, {b['y_px']:4d}) "
                        f"size={b['size_px']}px "
                        f"norm=({b['x_norm']:.3f}, {b['y_norm']:.3f}) "
                        f"| {b['position_description']}"
                    )
            print("-" * 60)

        # Visualize if requested
        if args.visualize:
            print("\n🎨 Generating visualization...")
            viz_paths = visualize_bboxes(
                result["bbox_path"],
                os.path.join(args.workspace, task_id, "s4_output"),
            )
            print(f"  {len(viz_paths)} visualization images saved")

        return

    # Normal run
    if not args.task_id or not args.pptx:
        parser.error("--task-id and --pptx required (or use --test)")

    agent = BBoxAgent(workspace_root=args.workspace)
    result = agent.run(
        task_id=args.task_id,
        pptx_path=args.pptx,
        avatar_size_px=args.avatar_size,
    )

    print("\n" + "=" * 60)
    print("S4 BBox Agent Complete")
    print("=" * 60)
    print(f"  Task ID:      {result['task_id']}")
    print(f"  Total slides: {result['total_slides']}")
    print(f"  Output:       {result['bbox_path']}")
    print("=" * 60)

    if args.visualize:
        viz_paths = visualize_bboxes(
            result["bbox_path"],
            os.path.join(args.workspace, args.task_id, "s4_output"),
        )
        print(f"  Visualization: {len(viz_paths)} images")


if __name__ == "__main__":
    main()
