
import os
# ==================== 统一配置加载 ====================
import yaml as _yaml
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AGENT_DIR, 'config.yaml'), 'r') as _cf:
    _CFG = _yaml.safe_load(_cf)

import os
import re
import json
import uuid
import httpx
import asyncio
import hashlib
import argparse
import cProfile
import random
import zipfile
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Iterator, Tuple, Optional, Set

from pptx import Presentation
from pptx.util import Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE
from lxml import etree

# -----------------------------
# Config
# -----------------------------
LOG_FILE = os.path.join(_AGENT_DIR, "translation_log.txt")
SUPPORTED_EXTENSIONS = (".pptx",)
CACHE_VERSION = "v5"

MODEL = os.environ.get("KIMI_MODEL", "k3")
API_URL = os.environ.get("KIMI_API_URL", "https://api.kimi.com/coding/v1/chat/completions")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
MAX_TOKENS = 8192
ENABLE_THINKING = False

GW_TOKEN = os.environ.get(_CFG['api'].get('gw_token_env', 'SMARTCOURSE_GW_TOKEN'), '')

MIN_FONT_SIZE_PT = 8.0
DEFAULT_BATCH_SIZE = 8
DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_MAX_RETRIES = 5
REQUEST_TIMEOUT_SEC = 90.0
SINGLE_REQUEST_TIMEOUT_SEC = 60.0
BACKOFF_BASE_SEC = 1.5
BACKOFF_JITTER_SEC = 0.5
MAX_BACKOFF_SEC = 12.0

# XML namespace for DrawingML text elements
A_NAMESPACE = "http://schemas.openxmlformats.org/drawingml/2006/main"
A_T_TAG = f"{{{A_NAMESPACE}}}t"

TextEntry = Dict[str, Any]
ShapePath = Tuple[int, ...]


# -----------------------------
# Logging & Cache
# -----------------------------
def log_message(message: str, level: str = "INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    print(log_entry, end="")
    with open(LOG_FILE, "a", encoding="utf-8") as logfile:
        logfile.write(log_entry)


def get_cache_filename(presentation_path: str, target_language: str) -> str:
    base_name = os.path.splitext(os.path.basename(presentation_path))[0]
    path_hash = hashlib.sha256(presentation_path.encode("utf-8")).hexdigest()[:8]
    model_tag = MODEL.replace("/", "_").replace("-", "_")
    lang_tag = target_language.replace("/", "_").replace("-", "_")
    return f"translation_cache_{CACHE_VERSION}_{base_name}_{lang_tag}_{model_tag}_{path_hash}.json"


def load_cache(cache_file: str) -> Dict[str, str]:
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        log_message(f"Failed to load cache {cache_file}: {e}", level="WARNING")
    return {}


def save_cache(cache: Dict[str, str], cache_file: str) -> None:
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4, ensure_ascii=False)


def generate_prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# -----------------------------
# Text utilities
# -----------------------------
def normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        parts.append(text)
                elif "text" in item:
                    parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"]).strip()
        return json.dumps(content, ensure_ascii=False)
    return str(content).strip()


def extract_first_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        fenced = re.sub(r"^```(?:json)?\s*", "", text)
        fenced = re.sub(r"\s*```$", "", fenced)
        text = fenced.strip()
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
    return text


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text or ""))


def target_language_is_chinese(target_language: str) -> bool:
    lang = (target_language or "").strip().lower()
    return lang.startswith("zh") or "chinese" in lang or "中文" in lang


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def looks_like_untranslated(original_text: str, translated_text: str, target_language: str) -> bool:
    if not original_text.strip():
        return False
    if target_language_is_chinese(target_language):
        return False
    original_norm = normalized_text(original_text)
    translated_norm = normalized_text(translated_text)
    if not translated_norm:
        return True
    if contains_cjk(original_norm) and original_norm == translated_norm:
        return True
    return False


def should_retry_exception(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600
    return False


def get_retry_delay(attempt_index: int) -> float:
    delay = min(BACKOFF_BASE_SEC * (2 ** attempt_index), MAX_BACKOFF_SEC)
    return delay + random.uniform(0.0, BACKOFF_JITTER_SEC)


async def sleep_before_retry(attempt_index: int, reason: str, scope: str) -> None:
    delay = get_retry_delay(attempt_index)
    log_message(f"Retrying {scope} after {delay:.1f}s because of {reason}", level="WARNING")
    await asyncio.sleep(delay)


# -----------------------------
# XML-level text scanning (catches SmartArt, diagrams, everything)
# -----------------------------
def scan_pptx_xml_texts(pptx_path: str) -> List[str]:
    """
    Open .pptx as ZIP, scan ALL XML parts for <a:t> text elements.
    This catches SmartArt, diagrams, charts, masters, layouts, everything.
    """
    all_texts: List[str] = []
    seen: Set[str] = set()

    try:
        with zipfile.ZipFile(pptx_path, "r") as zf:
            for name in zf.namelist():
                # Only process XML files, skip .rels and non-XML
                if not name.endswith(".xml"):
                    continue
                # Skip relationship files
                if "/_rels/" in name or name.endswith(".rels"):
                    continue

                try:
                    data = zf.read(name)
                    root = etree.fromstring(data)

                    for t_elem in root.iter(A_T_TAG):
                        text = t_elem.text
                        if text and text.strip() and text not in seen:
                            seen.add(text)
                            all_texts.append(text)
                except Exception:
                    pass
    except Exception as e:
        log_message(f"Error scanning ZIP XML: {e}", level="ERROR")

    return all_texts


def apply_xml_level_translations(input_pptx: str, output_pptx: str, cache: Dict[str, str]) -> int:
    """
    Open .pptx as ZIP, find ALL <a:t> elements in ALL XML parts,
    replace with cached translations, write to output.
    This is the catch-all pass that handles SmartArt, diagrams, etc.
    """
    replacements = 0
    temp_path = output_pptx + ".xmlpass.tmp"

    try:
        with zipfile.ZipFile(input_pptx, "r") as zin:
            with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    raw_data = zin.read(item.filename)

                    if item.filename.endswith(".xml") and "/_rels/" not in item.filename:
                        try:
                            parser = etree.XMLParser(
                                remove_blank_text=False,
                                strip_cdata=False,
                            )
                            root = etree.fromstring(raw_data, parser)
                            modified = False

                            for t_elem in root.iter(A_T_TAG):
                                text = t_elem.text
                                if text and text.strip():
                                    h = generate_prompt_hash(text)
                                    translated = cache.get(h)
                                    if translated and translated != text:
                                        t_elem.text = translated
                                        modified = True
                                        replacements += 1

                            if modified:
                                raw_data = etree.tostring(
                                    root,
                                    xml_declaration=True,
                                    encoding="UTF-8",
                                    standalone=True,
                                )
                        except etree.XMLSyntaxError:
                            pass
                        except Exception as e:
                            log_message(
                                f"XML pass error on {item.filename}: {e}",
                                level="WARNING",
                            )

                    zout.writestr(item, raw_data)

        # Replace output with the XML-patched version
        if os.path.exists(output_pptx):
            os.remove(output_pptx)
        os.rename(temp_path, output_pptx)

    except Exception as e:
        log_message(f"XML-level translation failed: {e}", level="ERROR")
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    return replacements


# -----------------------------
# python-pptx level extraction (for font adjustment on regular shapes)
# -----------------------------
def is_group_shape(shape: Any) -> bool:
    return hasattr(shape, "shapes")


def is_image_shape(shape: Any) -> bool:
    try:
        if hasattr(shape, "shape_type"):
            if shape.shape_type in (MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.LINKED_PICTURE):
                return True
        if hasattr(shape, "image") and not getattr(shape, "has_text_frame", False):
            return True
    except Exception:
        pass
    return False


def iter_shapes(shape_container: Any, path_prefix: ShapePath = ()) -> Iterator[Tuple[ShapePath, Any]]:
    for idx, shape in enumerate(shape_container):
        current_path = path_prefix + (idx,)
        yield current_path, shape
        if is_group_shape(shape):
            yield from iter_shapes(shape.shapes, current_path)


def get_shape_by_path(shapes_container: Any, shape_path: ShapePath) -> Any:
    container = shapes_container
    shape = None
    for depth, idx in enumerate(shape_path):
        shape = container[idx]
        if depth < len(shape_path) - 1:
            container = shape.shapes
    return shape


def extract_runs_from_text_frame(
    text_frame: Any,
    source_type: str,
    source_idx: int,
    source_number: int,
    shape_path: ShapePath,
    shape_type: str,
    location_prefix: Dict[str, Any],
) -> List[TextEntry]:
    entries: List[TextEntry] = []
    for para_idx, paragraph in enumerate(text_frame.paragraphs):
        if paragraph.runs:
            for run_idx, run in enumerate(paragraph.runs):
                if run.text and run.text.strip():
                    loc = {**location_prefix, "kind": "text_run", "para_idx": para_idx, "run_idx": run_idx}
                    entries.append({
                        "source_type": source_type,
                        "source_idx": source_idx,
                        "source_number": source_number,
                        "shape_path": list(shape_path),
                        "shape_type": shape_type,
                        "text": run.text,
                        "location": loc,
                    })
        elif paragraph.text and paragraph.text.strip():
            loc = {**location_prefix, "kind": "text_paragraph", "para_idx": para_idx}
            entries.append({
                "source_type": source_type,
                "source_idx": source_idx,
                "source_number": source_number,
                "shape_path": list(shape_path),
                "shape_type": shape_type,
                "text": paragraph.text,
                "location": loc,
            })
    return entries


def extract_table_text(
    table: Any, source_type: str, source_idx: int, source_number: int, shape_path: ShapePath,
) -> List[TextEntry]:
    entries: List[TextEntry] = []
    for row_idx, row in enumerate(table.rows):
        for col_idx, cell in enumerate(row.cells):
            for para_idx, paragraph in enumerate(cell.text_frame.paragraphs):
                if paragraph.runs:
                    for run_idx, run in enumerate(paragraph.runs):
                        if run.text and run.text.strip():
                            entries.append({
                                "source_type": source_type,
                                "source_idx": source_idx,
                                "source_number": source_number,
                                "shape_path": list(shape_path),
                                "shape_type": "TABLE",
                                "text": run.text,
                                "location": {
                                    "kind": "table_run",
                                    "row_idx": row_idx, "col_idx": col_idx,
                                    "para_idx": para_idx, "run_idx": run_idx,
                                },
                            })
                elif paragraph.text and paragraph.text.strip():
                    entries.append({
                        "source_type": source_type,
                        "source_idx": source_idx,
                        "source_number": source_number,
                        "shape_path": list(shape_path),
                        "shape_type": "TABLE",
                        "text": paragraph.text,
                        "location": {
                            "kind": "table_paragraph",
                            "row_idx": row_idx, "col_idx": col_idx,
                            "para_idx": para_idx,
                        },
                    })
    return entries


def extract_from_shape_container(
    shapes_container: Any,
    source_type: str,
    source_idx: int,
    source_number: int,
    title_shape: Any = None,
) -> List[TextEntry]:
    entries: List[TextEntry] = []
    for shape_path, shape in iter_shapes(shapes_container):
        if is_image_shape(shape):
            continue

        if getattr(shape, "has_text_frame", False):
            shape_type = "BODY"
            try:
                if title_shape is not None and shape == title_shape:
                    shape_type = "TITLE"
            except Exception:
                pass

            try:
                if hasattr(shape, "placeholder_format") and shape.placeholder_format is not None:
                    from pptx.enum.shapes import PP_PLACEHOLDER
                    ph_type = shape.placeholder_format.type
                    if ph_type == PP_PLACEHOLDER.FOOTER:
                        shape_type = "FOOTER"
                    elif ph_type == PP_PLACEHOLDER.DATE:
                        shape_type = "DATE"
                    elif ph_type == PP_PLACEHOLDER.SLIDE_NUMBER:
                        continue
                    elif ph_type in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
                        shape_type = "TITLE"
                    elif ph_type == PP_PLACEHOLDER.SUBTITLE:
                        shape_type = "SUBTITLE"
            except Exception:
                pass

            sub = extract_runs_from_text_frame(
                shape.text_frame, source_type, source_idx, source_number,
                shape_path, shape_type, {}
            )
            entries.extend(sub)

        if getattr(shape, "has_table", False):
            sub = extract_table_text(shape.table, source_type, source_idx, source_number, shape_path)
            entries.extend(sub)

        if getattr(shape, "has_chart", False):
            try:
                chart = shape.chart
                if chart.has_title and chart.chart_title.has_text_frame:
                    sub = extract_runs_from_text_frame(
                        chart.chart_title.text_frame, source_type, source_idx, source_number,
                        shape_path, "CHART_TITLE", {"chart_part": "title"}
                    )
                    entries.extend(sub)

                for axis_name in ("category_axis", "value_axis"):
                    try:
                        axis = getattr(chart, axis_name, None)
                        if axis and axis.has_title and axis.axis_title.has_text_frame:
                            sub = extract_runs_from_text_frame(
                                axis.axis_title.text_frame, source_type, source_idx, source_number,
                                shape_path, "CHART_AXIS", {"chart_part": axis_name}
                            )
                            entries.extend(sub)
                    except Exception:
                        pass
            except Exception as e:
                log_message(f"Chart extraction error: {e}", level="WARNING")

    return entries


def extract_pptx_level_entries(prs: Presentation) -> List[TextEntry]:
    """Extract text via python-pptx API (regular shapes, tables, charts, masters, layouts)"""
    all_entries: List[TextEntry] = []

    for slide_idx, slide in enumerate(prs.slides):
        title_shape = getattr(slide.shapes, "title", None)
        entries = extract_from_shape_container(slide.shapes, "slide", slide_idx, slide_idx + 1, title_shape)
        all_entries.extend(entries)

    master_seen: Set[str] = set()
    for master_idx, master in enumerate(prs.slide_masters):
        title_shape = getattr(master.shapes, "title", None)
        entries = extract_from_shape_container(master.shapes, "master", master_idx, master_idx + 1, title_shape)
        for e in entries:
            key = e["text"].strip()
            if key and key not in master_seen:
                master_seen.add(key)
                all_entries.append(e)

    layout_seen: Set[str] = set(master_seen)
    for layout_idx, layout in enumerate(prs.slide_layouts):
        title_shape = getattr(layout.shapes, "title", None)
        entries = extract_from_shape_container(layout.shapes, "layout", layout_idx, layout_idx + 1, title_shape)
        for e in entries:
            key = e["text"].strip()
            if key and key not in layout_seen:
                layout_seen.add(key)
                all_entries.append(e)

    return all_entries


# -----------------------------
# Apply translations (python-pptx level, with font adjustment)
# -----------------------------
def adjust_font_size(run: Any, original_text: str, translated_text: str) -> None:
    if not original_text:
        return
    original_len = len(original_text.strip())
    translated_len = len(translated_text.strip())
    if original_len <= 0 or translated_len <= original_len:
        return
    current_size = run.font.size
    if current_size is None:
        return
    ratio = translated_len / original_len
    try:
        current_pt = float(current_size.pt)
    except Exception:
        return
    new_pt = max(current_pt / ratio, MIN_FONT_SIZE_PT)
    if new_pt < current_pt:
        run.font.size = Pt(new_pt)


def get_shapes_container(prs: Presentation, entry: TextEntry) -> Any:
    source_type = entry["source_type"]
    source_idx = entry["source_idx"]
    if source_type == "slide":
        return prs.slides[source_idx].shapes
    elif source_type == "master":
        return prs.slide_masters[source_idx].shapes
    elif source_type == "layout":
        return prs.slide_layouts[source_idx].shapes
    raise ValueError(f"Unknown source_type: {source_type}")


def apply_pptx_level_translations(prs: Presentation, text_entries: List[TextEntry], cache: Dict[str, str]) -> int:
    """Apply translations via python-pptx API (supports font adjustment)"""
    applied = 0
    for entry in text_entries:
        prompt_hash = generate_prompt_hash(entry["text"])
        translated_text = cache.get(prompt_hash, entry["text"])
        if translated_text == entry["text"]:
            continue

        try:
            shapes_container = get_shapes_container(prs, entry)
            shape = get_shape_by_path(shapes_container, tuple(entry["shape_path"]))
            location = entry["location"]
            kind = location["kind"]
            shape_type = entry.get("shape_type", "")

            if shape_type in ("CHART_TITLE", "CHART_AXIS"):
                chart = shape.chart
                chart_part = location.get("chart_part", "")
                if chart_part == "title":
                    tf = chart.chart_title.text_frame
                elif chart_part == "category_axis":
                    tf = chart.category_axis.axis_title.text_frame
                elif chart_part == "value_axis":
                    tf = chart.value_axis.axis_title.text_frame
                else:
                    continue
                para = tf.paragraphs[location["para_idx"]]
                if kind == "text_run" and para.runs:
                    para.runs[location["run_idx"]].text = translated_text
                elif para.runs:
                    para.runs[0].text = translated_text
                else:
                    para.text = translated_text

            elif kind == "text_run":
                run = shape.text_frame.paragraphs[location["para_idx"]].runs[location["run_idx"]]
                original = run.text
                run.text = translated_text
                adjust_font_size(run, original, translated_text)

            elif kind == "text_paragraph":
                para = shape.text_frame.paragraphs[location["para_idx"]]
                if para.runs:
                    para.runs[0].text = translated_text
                else:
                    para.text = translated_text

            elif kind == "table_run":
                cell = shape.table.rows[location["row_idx"]].cells[location["col_idx"]]
                run = cell.text_frame.paragraphs[location["para_idx"]].runs[location["run_idx"]]
                original = run.text
                run.text = translated_text
                adjust_font_size(run, original, translated_text)

            elif kind == "table_paragraph":
                cell = shape.table.rows[location["row_idx"]].cells[location["col_idx"]]
                para = cell.text_frame.paragraphs[location["para_idx"]]
                if para.runs:
                    para.runs[0].text = translated_text
                else:
                    para.text = translated_text

            applied += 1

        except Exception as e:
            log_message(
                f"Error applying: source={entry['source_type']}, idx={entry['source_idx']}, "
                f"path={entry['shape_path']}: {e}",
                level="ERROR",
            )

    return applied


# -----------------------------
# Gateway API
# -----------------------------
async def call_gateway(
    messages: List[Dict[str, Any]],
    max_tokens: int = MAX_TOKENS,
    timeout: float = REQUEST_TIMEOUT_SEC,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    if KIMI_API_KEY:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {KIMI_API_KEY}",
        }
        payload = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "temperature": 1,
            "messages": messages,
        }
    else:
        if not GW_TOKEN:
            raise ValueError("KIMI_API_KEY or GW token not found.")
        headers = {
            "Content-Type": "application/json",
            "BCS-APIHub-RequestId": str(uuid.uuid4()),
            "X-CHJ-GWToken": GW_TOKEN,
        }
        payload = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "enable_thinking": ENABLE_THINKING,
            "messages": messages,
        }

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
        close_client = True

    try:
        resp = await client.post(API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            log_message(f"Gateway failed, status={resp.status_code}, body={resp.text[:1000]}", level="ERROR")
        resp.raise_for_status()
        data = resp.json()
    finally:
        if close_client:
            await client.aclose()

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise ValueError(f"Unexpected response: {json.dumps(data, ensure_ascii=False)[:2000]}") from e

    return normalize_message_content(content)


async def translate_text_with_gateway(
    prompt: str,
    target_language: str,
    cache: Dict[str, str],
    max_retries: int = DEFAULT_MAX_RETRIES,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    prompt_hash = generate_prompt_hash(prompt)
    if prompt_hash in cache:
        return cache[prompt_hash]

    system_instruction = (
        f"You are a helpful assistant that translates text to {target_language}. "
        "Maintain the original meaning as closely as possible. "
        f"Adjust the tone for professional presentations in {target_language}. "
        "Return only JSON, no explanation. "
        "Do not translate emails, phone numbers, code, URLs, file paths, or non-linguistic identifiers. "
        'Return as: {"translated": "<translated text>"}'
    )
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(max_retries):
        try:
            raw = await call_gateway(messages=messages, max_tokens=4096, timeout=SINGLE_REQUEST_TIMEOUT_SEC, client=client)
            result = extract_first_json_object(raw)
            parsed = json.loads(result)
            translated_text = str(parsed["translated"])
            cache[prompt_hash] = translated_text
            return translated_text
        except Exception as e:
            log_message(f"Single translate error (attempt {attempt + 1}/{max_retries}): {e}", level="ERROR")
            if attempt == max_retries - 1:
                break
            if should_retry_exception(e):
                await sleep_before_retry(attempt, type(e).__name__, "single item")
    return prompt


async def translate_batch(
    prompt_data: Dict[str, Any],
    cache: Dict[str, str],
    max_retries: int,
    batch_num: int,
    total_batches: int,
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> Set[str]:
    target_language = prompt_data["target_language"]
    requested_hashes = set(prompt_data["texts"].keys())

    system_instruction = (
        f"You are a helpful assistant that translates multiple texts to {target_language}. "
        "Maintain the original meaning as closely as possible. "
        f"Adjust the tone for professional presentations in {target_language}. "
        "Return only JSON. Every input hash must appear exactly once in the output. "
        "Do not translate emails, phone numbers, code, URLs, file paths, or non-linguistic identifiers. "
        'Return as: {"translations": {"<sha256 hash>": "<translated text>"}}'
    )
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": json.dumps(prompt_data, ensure_ascii=False)},
    ]

    async with semaphore:
        for attempt in range(max_retries):
            try:
                raw = await call_gateway(messages=messages, max_tokens=4096, timeout=REQUEST_TIMEOUT_SEC, client=client)
                result = extract_first_json_object(raw)
                parsed = json.loads(result)
                translations = parsed.get("translations", {})
                if not isinstance(translations, dict):
                    raise ValueError(f"Invalid translations: {type(translations)}")

                translated_hashes: Set[str] = set()
                suspicious_hashes: Set[str] = set()
                for hash_, translated_text in translations.items():
                    if hash_ not in requested_hashes:
                        continue
                    translated_text = str(translated_text)
                    cache[hash_] = translated_text
                    translated_hashes.add(hash_)
                    original_text = prompt_data["texts"][hash_]
                    if looks_like_untranslated(original_text, translated_text, target_language):
                        suspicious_hashes.add(hash_)

                missing = requested_hashes - translated_hashes
                log_message(
                    f"Batch {batch_num}/{total_batches}: {len(translated_hashes)}/{len(requested_hashes)} ok, "
                    f"suspicious={len(suspicious_hashes)}, missing={len(missing)}",
                    level="INFO",
                )
                return missing | suspicious_hashes

            except Exception as e:
                log_message(f"Batch {batch_num} error (attempt {attempt + 1}/{max_retries}): {e}", level="ERROR")
                if attempt == max_retries - 1:
                    return set(requested_hashes)
                if should_retry_exception(e):
                    await sleep_before_retry(attempt, type(e).__name__, f"batch {batch_num}")

    return set(requested_hashes)


async def fallback_translate_hashes(
    hash_to_text: Dict[str, str],
    target_language: str,
    cache: Dict[str, str],
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    if not hash_to_text:
        return
    log_message(f"Fallback: translating {len(hash_to_text)} texts one by one", level="WARNING")
    for hash_, text in hash_to_text.items():
        async with semaphore:
            translated = await translate_text_with_gateway(
                prompt=text, target_language=target_language,
                cache=cache, max_retries=max_retries, client=client,
            )
            cache[hash_] = translated


def find_unresolved_hashes(hash_to_text: Dict[str, str], target_language: str, cache: Dict[str, str]) -> Dict[str, str]:
    unresolved: Dict[str, str] = {}
    for hash_, original_text in hash_to_text.items():
        translated_text = cache.get(hash_)
        if translated_text is None:
            unresolved[hash_] = original_text
            continue
        if looks_like_untranslated(original_text, translated_text, target_language):
            unresolved[hash_] = original_text
    return unresolved


async def batch_translate_all(
    hash_to_text: Dict[str, str],
    target_language: str,
    cache: Dict[str, str],
    max_retries: int = DEFAULT_MAX_RETRIES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> None:
    """Translate all texts in hash_to_text that are not in cache."""
    # Filter out already cached
    to_translate = {h: t for h, t in hash_to_text.items() if h not in cache}
    if not to_translate:
        log_message("All translations found in cache.", level="INFO")
        return

    items = list(to_translate.items())
    total_batches = (len(items) + batch_size - 1) // batch_size
    log_message(f"Translating {len(items)} unique texts in {total_batches} batches (concurrency={max_concurrency})", level="INFO")

    semaphore = asyncio.Semaphore(max_concurrency)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
        tasks = []
        for batch_num, i in enumerate(range(0, len(items), batch_size), 1):
            batch = items[i: i + batch_size]
            payload = {h: t for h, t in batch}
            prompt_data = {
                "texts": payload,
                "target_language": target_language,
                "instructions": "Translate each text, maintaining original meaning and formatting.",
            }
            tasks.append(
                translate_batch(prompt_data, cache, max_retries, batch_num, total_batches, semaphore, client)
            )

        unresolved_sets = await asyncio.gather(*tasks)
        unresolved_hashes: Set[str] = set()
        for item in unresolved_sets:
            unresolved_hashes.update(item)

        second_pass = find_unresolved_hashes(to_translate, target_language, cache)
        unresolved_hashes.update(second_pass.keys())

        if unresolved_hashes:
            fallback_payload = {h: to_translate[h] for h in unresolved_hashes if h in to_translate}
            await fallback_translate_hashes(
                fallback_payload, target_language, cache,
                asyncio.Semaphore(1), client, max_retries,
            )

    final_unresolved = find_unresolved_hashes(to_translate, target_language, cache)
    translated_count = len(to_translate) - len(final_unresolved)
    log_message(f"Coverage: {translated_count}/{len(to_translate)} resolved, {len(final_unresolved)} unresolved", level="INFO")

    if final_unresolved:
        for idx, text in enumerate(list(final_unresolved.values())[:10], 1):
            log_message(f"Unresolved sample {idx}: {text[:120]}", level="WARNING")


# -----------------------------
# Main pipeline
# -----------------------------
async def translate_presentation(
    presentation_path: str,
    target_language: str,
    output_path: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> None:
    if not presentation_path.lower().endswith(SUPPORTED_EXTENSIONS):
        log_message(f"Unsupported format: {presentation_path}. Skipping.", level="WARNING")
        return

    if os.path.abspath(presentation_path) == os.path.abspath(output_path):
        log_message("Input and output paths are the same. Not allowed.", level="ERROR")
        return

    try:
        # ===== PHASE 1: Extract ALL texts =====
        log_message("Phase 1: Extracting all text...", level="INFO")

        # 1a. python-pptx level (regular shapes, tables, charts, masters, layouts)
        prs = Presentation(presentation_path)
        pptx_entries = extract_pptx_level_entries(prs)
        log_message(f"  python-pptx level: {len(pptx_entries)} entries", level="INFO")

        # 1b. XML level (SmartArt, diagrams, anything missed by python-pptx)
        xml_texts = scan_pptx_xml_texts(presentation_path)
        log_message(f"  XML level: {len(xml_texts)} unique texts", level="INFO")

        # Build unified hash→text map
        hash_to_text: Dict[str, str] = {}
        for entry in pptx_entries:
            h = generate_prompt_hash(entry["text"])
            if h not in hash_to_text:
                hash_to_text[h] = entry["text"]
        for text in xml_texts:
            h = generate_prompt_hash(text)
            if h not in hash_to_text:
                hash_to_text[h] = text

        log_message(f"  Total unique texts to translate: {len(hash_to_text)}", level="INFO")

        if not hash_to_text:
            log_message(f"No text found in {presentation_path}.", level="WARNING")
            return

        # ===== PHASE 2: Translate =====
        log_message("Phase 2: Translating...", level="INFO")
        cache_file = get_cache_filename(presentation_path, target_language)
        cache = load_cache(cache_file)

        await batch_translate_all(
            hash_to_text, target_language, cache,
            batch_size=batch_size, max_concurrency=max_concurrency,
        )
        save_cache(cache, cache_file)

        # ===== PHASE 3: Apply via python-pptx (regular shapes with font adjustment) =====
        log_message("Phase 3: Applying translations (python-pptx level)...", level="INFO")
        prs2 = Presentation(presentation_path)
        applied_pptx = apply_pptx_level_translations(prs2, pptx_entries, cache)
        log_message(f"  python-pptx applied: {applied_pptx}", level="INFO")

        # Save intermediate result
        intermediate_path = output_path + ".intermediate.tmp"
        prs2.save(intermediate_path)

        # ===== PHASE 4: Apply via XML (SmartArt, diagrams, catch-all) =====
        log_message("Phase 4: Applying translations (XML level, catches SmartArt/diagrams)...", level="INFO")
        applied_xml = apply_xml_level_translations(intermediate_path, output_path, cache)
        log_message(f"  XML level applied: {applied_xml}", level="INFO")

        # Clean up intermediate
        if os.path.exists(intermediate_path):
            os.remove(intermediate_path)

        log_message(f"Translated presentation saved to: {output_path}", level="SUCCESS")
        log_message(
            f"Summary: {applied_pptx} via python-pptx + {applied_xml} via XML = "
            f"{applied_pptx + applied_xml} total replacements",
            level="SUCCESS",
        )

    except Exception as e:
        log_message(f"Error during translation: {e}", level="ERROR")
        import traceback
        traceback.print_exc()
        # Clean up intermediate file on error
        intermediate_path = output_path + ".intermediate.tmp"
        if os.path.exists(intermediate_path):
            os.remove(intermediate_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate PowerPoint presentations (all text including SmartArt, excluding images and notes)."
    )
    parser.add_argument("input_path", nargs="?", type=str, help="Input .pptx file or directory.")
    parser.add_argument("-o", "--output", type=str, help="Output file or directory path.")
    parser.add_argument("-l", "--language", type=str, required=True, help="Target language (e.g., en, zh-CN, ja, ko).")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-concurrency", type=int, default=DEFAULT_MAX_CONCURRENCY)
    parser.add_argument("-p", "--profile", action="store_true", help="Enable profiling.")
    args = parser.parse_args()

    input_path = args.input_path
    output_path = args.output
    target_language = args.language
    batch_size = max(1, args.batch_size)
    max_concurrency = max(1, args.max_concurrency)

    if not input_path:
        log_message("No input specified. Processing all .pptx in current directory.", level="INFO")
        for filename in os.listdir("."):
            if filename.lower().endswith(SUPPORTED_EXTENSIONS):
                out = filename.replace(".pptx", f"_translated_{target_language}.pptx")
                asyncio.run(translate_presentation(filename, target_language, out, batch_size, max_concurrency))
        return

    if os.path.isfile(input_path):
        if not output_path:
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_translated_{target_language}{ext}"
        if args.profile:
            cProfile.run(
                f"asyncio.run(translate_presentation({input_path!r}, {target_language!r}, {output_path!r}, {batch_size}, {max_concurrency}))",
                sort="tottime",
            )
        else:
            asyncio.run(translate_presentation(input_path, target_language, output_path, batch_size, max_concurrency))

    elif os.path.isdir(input_path):
        if not output_path:
            output_path = input_path
        elif not os.path.isdir(output_path):
            log_message("If input is directory, output must also be directory.", level="ERROR")
            return
        for filename in os.listdir(input_path):
            if filename.lower().endswith(SUPPORTED_EXTENSIONS):
                full_in = os.path.join(input_path, filename)
                base, ext = os.path.splitext(filename)
                full_out = os.path.join(output_path, f"{base}_translated_{target_language}{ext}")
                if args.profile:
                    cProfile.run(
                        f"asyncio.run(translate_presentation({full_in!r}, {target_language!r}, {full_out!r}, {batch_size}, {max_concurrency}))",
                        sort="tottime",
                    )
                else:
                    asyncio.run(translate_presentation(full_in, target_language, full_out, batch_size, max_concurrency))
    else:
        log_message(f"Invalid input path: {input_path}", level="ERROR")


if __name__ == "__main__":
    main()
