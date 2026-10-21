"""
S2 翻译文稿智能体 (TranslateAgent) v2
修复：
1. 中文数量单位残留（亿/万等）
2. 公式数字检查增加语言残留检测
3. page级final_passed判定逻辑修复
"""

import os
# ==================== 统一配置加载 ====================
import yaml as _yaml
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_AGENT_DIR, "config.yaml"), "r") as _cf:
    _CFG = _yaml.safe_load(_cf)

import os
import re
import json
import uuid
import httpx
import asyncio
import hashlib
import random
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set

# -----------------------------
# Config
# -----------------------------
MODEL = os.environ.get("KIMI_MODEL", "k3")
API_URL = os.environ.get("KIMI_API_URL", "https://api.kimi.com/coding/v1/chat/completions")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")
MAX_TOKENS = 8192
ENABLE_THINKING = False

GW_TOKEN = os.environ.get(_CFG['api'].get('gw_token_env', 'SMARTCOURSE_GW_TOKEN'), '')

REQUEST_TIMEOUT_SEC = 90.0
MAX_RETRIES = 5
BACKOFF_BASE_SEC = 1.5
BACKOFF_JITTER_SEC = 0.5
MAX_BACKOFF_SEC = 12.0

SEMANTIC_SIMILARITY_THRESHOLD = 0.85
TERM_COVERAGE_THRESHOLD = 0.80
MAX_VERIFY_ITERATIONS = 3

ST_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
WORKSPACE_ROOT = _CFG['paths']['workspace']

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TranslateAgent")


# -----------------------------
# Gateway API
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
    start = text.find("{")
    if start == -1:
        start = text.find("[")
        if start == -1:
            return text
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
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
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
    return text


def should_retry_exception(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code < 600
    return False


def get_retry_delay(attempt: int) -> float:
    delay = min(BACKOFF_BASE_SEC * (2 ** attempt), MAX_BACKOFF_SEC)
    return delay + random.uniform(0.0, BACKOFF_JITTER_SEC)


async def call_gateway(
    messages: List[Dict[str, str]],
    max_tokens: int = MAX_TOKENS,
    timeout: float = REQUEST_TIMEOUT_SEC,
    client: Optional[httpx.AsyncClient] = None,
    temperature: float = 0.2,
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
            "temperature": temperature,
            "messages": messages,
        }

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
        close_client = True

    try:
        resp = await client.post(API_URL, headers=headers, json=payload)
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


async def call_gateway_with_retry(
    messages: List[Dict[str, str]],
    max_retries: int = MAX_RETRIES,
    client: Optional[httpx.AsyncClient] = None,
    temperature: float = 0.2,
) -> str:
    for attempt in range(max_retries):
        try:
            return await call_gateway(messages, client=client, temperature=temperature)
        except Exception as e:
            logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise
            if should_retry_exception(e):
                delay = get_retry_delay(attempt)
                await asyncio.sleep(delay)
    raise RuntimeError("Unreachable")


# -----------------------------
# Semantic Similarity (local)
# -----------------------------
class SemanticChecker:
    def __init__(self, model_name: str = ST_MODEL_NAME):
        self._model = None
        self._model_name = model_name

    def _load_model(self):
        if self._model is None:
            logger.info(f"Loading sentence-transformers model: {self._model_name}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            logger.info("Model loaded.")

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        self._load_model()
        embeddings = self._model.encode([text_a, text_b], normalize_embeddings=True)
        similarity = float(embeddings[0] @ embeddings[1])
        return similarity


# -----------------------------
# Language detection helpers
# -----------------------------
def contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text or ""))


def contains_japanese_only(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text or ""))


def contains_korean(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7af]", text or ""))


def contains_non_target_chars(text: str, target_language: str) -> List[str]:
    """Check if translation contains characters from non-target language."""
    target_lower = target_language.lower()
    residuals = []

    if "chinese" in target_lower or "zh" in target_lower or "中文" in target_lower:
        return residuals  # target is Chinese, Chinese chars are expected

    # For non-Chinese targets, Chinese chars are residuals
    chinese_chars = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+", text)
    if chinese_chars:
        residuals.extend(chinese_chars)

    if "japanese" not in target_lower and "ja" != target_lower:
        jp_chars = re.findall(r"[\u3040-\u309f\u30a0-\u30ff]+", text)
        if jp_chars:
            residuals.extend(jp_chars)

    if "korean" not in target_lower and "ko" != target_lower:
        kr_chars = re.findall(r"[\uac00-\ud7af]+", text)
        if kr_chars:
            residuals.extend(kr_chars)

    return residuals


# -----------------------------
# LLM-based checkers
# -----------------------------
async def llm_extract_terms(text: str, client: httpx.AsyncClient) -> List[str]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a terminology extraction assistant. "
                "Extract key technical terms, proper nouns, and domain-specific vocabulary from the given text. "
                "Return as a JSON array of strings. No explanation, only JSON. "
                'Example: ["neural network", "backpropagation", "gradient descent"]'
            ),
        },
        {"role": "user", "content": text},
    ]
    raw = await call_gateway_with_retry(messages, client=client)
    try:
        result = extract_first_json_object(raw)
        terms = json.loads(result)
        if isinstance(terms, list):
            return [str(t).strip() for t in terms if str(t).strip()]
    except Exception as e:
        logger.warning(f"Failed to parse terms: {e}, raw={raw[:200]}")
    return []


async def llm_check_formulas_numbers(
    original: str, translated: str, target_language: str, client: httpx.AsyncClient
) -> Tuple[str, str]:
    """
    Check numbers, formulas, AND non-target-language residuals.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a translation quality checker. "
                "Compare the original text and its translation. Check ALL of the following:\n"
                "1. ALL numbers, mathematical formulas, percentages, dates, and numeric identifiers "
                "must be preserved exactly in the translation.\n"
                "2. Chinese number units (亿, 万, 千, 百) must be converted to their English equivalents "
                "(e.g., 1.1亿 → 110 million, 1750亿 → 175 billion, 3万 → 30 thousand). "
                "Keeping Chinese units in a non-Chinese translation is a FAILURE.\n"
                f"3. The translation target language is {target_language}. "
                "If any characters from the source language remain in the translation "
                "(e.g., Chinese characters in an English translation), flag this as a FAILURE.\n"
                "Return JSON: {\"status\": \"passed\" or \"failed\", \"missing_items\": [list], "
                "\"residual_chars\": [list of non-target-language strings found]}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"original": original, "translated": translated, "target_language": target_language},
                ensure_ascii=False,
            ),
        },
    ]
    raw = await call_gateway_with_retry(messages, client=client)
    try:
        result = extract_first_json_object(raw)
        parsed = json.loads(result)
        status = str(parsed.get("status", "failed")).lower()
        missing = parsed.get("missing_items", [])
        residuals = parsed.get("residual_chars", [])

        details = []
        if missing:
            details.append(f"missing: {missing}")
        if residuals:
            details.append(f"residual chars: {residuals}")
            status = "failed"  # force fail if residuals found
        detail = "; ".join(details) if details else "all preserved"
        return status, detail
    except Exception as e:
        logger.warning(f"Formula check parse error: {e}")
        return "failed", f"parse error: {e}"


async def llm_overall_judgment(
    original: str, back_translated: str, client: httpx.AsyncClient
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a translation quality judge. "
                "Compare the original text with its back-translation. "
                "Determine if they convey the same meaning. "
                "Minor wording differences are acceptable as long as core meaning is preserved. "
                'Return JSON: {"judgment": "CONSISTENT" or "INCONSISTENT", "reason": "brief reason"}'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"original": original, "back_translation": back_translated},
                ensure_ascii=False,
            ),
        },
    ]
    raw = await call_gateway_with_retry(messages, client=client)
    try:
        result = extract_first_json_object(raw)
        parsed = json.loads(result)
        return str(parsed.get("judgment", "INCONSISTENT")).upper()
    except Exception:
        return "INCONSISTENT"


async def llm_translate(
    text: str,
    target_language: str,
    client: httpx.AsyncClient,
    context: str = "",
    fix_instructions: str = "",
) -> str:
    system_parts = [
        f"You are a professional translator. Translate the following text to {target_language}.",
        "Maintain the original meaning, technical accuracy, and tone.",
        "Preserve all numbers, formulas, LaTeX expressions, and special identifiers exactly.",
        # --- 关键修复：明确要求翻译中文数量单位 ---
        "IMPORTANT: Translate ALL Chinese number units to their proper equivalents in the target language. "
        "For example: 亿 → hundred million or billion (depending on context), "
        "万 → ten thousand, 千 → thousand, 百 → hundred. "
        "1.1亿 → 110 million, 1750亿 → 175 billion, 3.4亿 → 340 million. "
        "Do NOT keep any Chinese number units (亿/万/千/百) in the translation.",
        # --- 关键修复：明确禁止源语言残留 ---
        f"The output must be entirely in {target_language}. "
        "Do NOT keep any characters from the source language in the output. "
        "Every word, number unit, and description must be in the target language.",
        "Do not add explanations.",
        'Return JSON: {"translated": "<translated text>"}',
    ]
    if context:
        system_parts.insert(1, f"Context: This is from a course about: {context}")
    if fix_instructions:
        system_parts.append(f"CRITICAL FIX REQUIRED: {fix_instructions}")

    messages = [
        {"role": "system", "content": "\n".join(system_parts)},
        {"role": "user", "content": text},
    ]

    raw = await call_gateway_with_retry(messages, client=client)
    try:
        result = extract_first_json_object(raw)
        parsed = json.loads(result)
        translated = str(parsed["translated"])

        # Post-processing: catch any remaining Chinese number units
        translated = post_process_number_units(translated, target_language)

        return translated
    except Exception as e:
        logger.warning(f"Translation parse error: {e}, raw={raw[:300]}")
        if not raw.strip().startswith("{"):
            return raw.strip()
        raise


def post_process_number_units(text: str, target_language: str) -> str:
    """
    Regex-based fallback: replace common Chinese number unit patterns
    that the LLM might miss.
    Only applies when target is not Chinese.
    """
    tl = target_language.lower()
    if "zh" in tl or "chinese" in tl or "中文" in tl:
        return text

    # Pattern: number + 亿 → number * 100 million or billion
    def replace_yi(match):
        num_str = match.group(1)
        try:
            num = float(num_str)
            value = num * 1e8
            if value >= 1e9:
                return f"{value / 1e9:.0f} billion"
            else:
                return f"{value / 1e6:.0f} million"
        except ValueError:
            return match.group(0)

    def replace_wan(match):
        num_str = match.group(1)
        try:
            num = float(num_str)
            value = num * 1e4
            if value >= 1e6:
                return f"{value / 1e6:.1f} million"
            else:
                return f"{value:,.0f}"
        except ValueError:
            return match.group(0)

    # number + 亿
    text = re.sub(r'(\d+\.?\d*)\s*亿', replace_yi, text)
    # number + 万
    text = re.sub(r'(\d+\.?\d*)\s*万', replace_wan, text)
    # standalone units that might remain
    text = text.replace('亿', ' hundred million')
    text = text.replace('万', ' ten thousand')
    text = text.replace('千', ' thousand')
    text = text.replace('百', ' hundred')

    return text


# -----------------------------
# Verification Pipeline
# -----------------------------
class VerificationResult:
    def __init__(self):
        self.semantic_score: float = 0.0
        self.term_coverage: float = 0.0
        self.formula_check: str = "unchecked"
        self.formula_detail: str = ""
        self.llm_judgment: str = "UNCHECKED"
        self.residual_check: str = "unchecked"
        self.passed: bool = False
        self.fix_instructions: str = ""

    def to_dict(self) -> Dict:
        return {
            "semantic_score": round(self.semantic_score, 4),
            "term_coverage": round(self.term_coverage, 4),
            "formula_check": self.formula_check,
            "llm_judgment": self.llm_judgment,
            "residual_check": self.residual_check,
        }


async def verify_translation(
    original_text: str,
    translated_text: str,
    source_language: str,
    target_language: str,
    semantic_checker: SemanticChecker,
    client: httpx.AsyncClient,
) -> VerificationResult:
    result = VerificationResult()

    # Step 0: Quick check for source language residuals (no API call needed)
    residuals = contains_non_target_chars(translated_text, target_language)
    if residuals:
        result.residual_check = f"failed: {residuals[:5]}"
        logger.warning(f"Source language residuals found: {residuals[:5]}")
    else:
        result.residual_check = "passed"

    # Step 1: Back-translate
    back_translated = await llm_translate(translated_text, source_language, client)
    logger.debug(f"Back-translated: {back_translated[:100]}")

    # Step 2: Semantic similarity (local)
    result.semantic_score = semantic_checker.compute_similarity(original_text, back_translated)

    # Step 3-5: LLM checks concurrently
    term_task = asyncio.create_task(_check_term_coverage(original_text, back_translated, client))
    formula_task = asyncio.create_task(
        llm_check_formulas_numbers(original_text, translated_text, target_language, client)
    )
    judgment_task = asyncio.create_task(llm_overall_judgment(original_text, back_translated, client))

    term_coverage = await term_task
    formula_status, formula_detail = await formula_task
    llm_judgment = await judgment_task

    result.term_coverage = term_coverage
    result.formula_check = formula_status
    result.formula_detail = formula_detail
    result.llm_judgment = llm_judgment

    # Determine pass/fail
    checks = {
        "semantic": result.semantic_score >= SEMANTIC_SIMILARITY_THRESHOLD,
        "term": result.term_coverage >= TERM_COVERAGE_THRESHOLD,
        "formula": result.formula_check == "passed",
        "llm": result.llm_judgment == "CONSISTENT",
        "residual": result.residual_check == "passed",
    }

    result.passed = all(checks.values())

    # Build fix instructions
    if not result.passed:
        fix_parts = []
        if not checks["semantic"]:
            fix_parts.append(
                f"Semantic similarity is low ({result.semantic_score:.2f}). "
                "Ensure the translation preserves the original meaning more faithfully."
            )
        if not checks["term"]:
            fix_parts.append(
                f"Term coverage is low ({result.term_coverage:.2f}). "
                "Make sure key technical terms are translated correctly."
            )
        if not checks["formula"]:
            fix_parts.append(
                f"Numbers/formulas issue: {formula_detail}. "
                "Preserve all numbers and formulas exactly. "
                "Convert Chinese number units (亿/万) to English equivalents."
            )
        if not checks["llm"]:
            fix_parts.append("LLM judge found semantic inconsistency. Review and correct.")
        if not checks["residual"]:
            fix_parts.append(
                f"Source language characters remain in translation: {result.residual_check}. "
                f"ALL text must be in {target_language}. Remove all source language characters. "
                "Convert 亿 to billion/million, 万 to thousand, etc."
            )
        result.fix_instructions = " ".join(fix_parts)

    logger.info(
        f"Verification: semantic={result.semantic_score:.3f}, "
        f"terms={result.term_coverage:.3f}, formula={result.formula_check}, "
        f"llm={result.llm_judgment}, residual={result.residual_check}, "
        f"passed={result.passed}"
    )

    return result


async def _check_term_coverage(
    original: str, back_translated: str, client: httpx.AsyncClient
) -> float:
    terms = await llm_extract_terms(original, client)
    if not terms:
        return 1.0

    back_lower = back_translated.lower()
    matched = sum(1 for t in terms if t.lower() in back_lower)
    coverage = matched / len(terms)
    logger.debug(f"Term coverage: {matched}/{len(terms)} = {coverage:.3f}")
    return coverage


# -----------------------------
# TranslateAgent
# -----------------------------
class TranslateAgent:
    def __init__(self, workspace_root: str = WORKSPACE_ROOT):
        self.workspace_root = workspace_root
        self.semantic_checker = SemanticChecker()

    def run(self, task_id: str, source_json: str, target_language: str = "English") -> Dict:
        return asyncio.run(self.arun(task_id, source_json, target_language))

    async def arun(self, task_id: str, source_json: str, target_language: str = "English") -> Dict:
        logger.info(f"=== TranslateAgent START: task={task_id}, target={target_language} ===")

        with open(source_json, "r", encoding="utf-8") as f:
            source_data = json.load(f)

        pages = source_data.get("pages", [])
        if not pages:
            logger.warning("No pages found.")
            return {"error": "No pages found"}

        source_language = self._detect_source_language(pages)
        logger.info(f"Detected source language: {source_language}")

        translated_pages = []
        page_reports = []

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
            for page in pages:
                page_id = page.get("page_id", 0)
                logger.info(f"--- Processing page {page_id} ---")

                translated_page, report = await self._translate_page(
                    page=page,
                    source_language=source_language,
                    target_language=target_language,
                    client=client,
                )
                translated_pages.append(translated_page)
                page_reports.append(report)

        total = len(page_reports)
        passed = sum(1 for r in page_reports if r["final_passed"])
        failed = total - passed

        output = {
            "task_id": task_id,
            "target_language": target_language,
            "pages": translated_pages,
            "translation_report": {
                "total_pages": total,
                "passed_pages": passed,
                "failed_pages": failed,
                "details": page_reports,
            },
        }

        output_dir = os.path.join(self.workspace_root, task_id, "s2_output")
        os.makedirs(output_dir, exist_ok=True)

        output_json_path = os.path.join(output_dir, "translated_structure.json")
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        report_json_path = os.path.join(output_dir, "translation_report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(output["translation_report"], f, indent=2, ensure_ascii=False)

        output["output_json"] = output_json_path
        logger.info(f"=== TranslateAgent DONE: {passed}/{total} pages passed ===")
        logger.info(f"Output: {output_json_path}")

        return output

    async def _translate_page(
        self, page: Dict, source_language: str, target_language: str, client: httpx.AsyncClient,
    ) -> Tuple[Dict, Dict]:
        page_id = page.get("page_id", 0)
        title = page.get("title", "")
        key_points = page.get("key_points", [])
        script_text = page.get("script_text", "")

        context = f"title: {title}"

        # Translate title
        translated_title, title_report = await self._translate_and_verify(
            text=title, source_language=source_language, target_language=target_language,
            client=client, context=context, field_name=f"page{page_id}.title",
        )

        # Translate key_points
        translated_key_points = []
        kp_reports = []
        for i, kp in enumerate(key_points):
            translated_kp, kp_report = await self._translate_and_verify(
                text=kp, source_language=source_language, target_language=target_language,
                client=client, context=context, field_name=f"page{page_id}.key_point[{i}]",
            )
            translated_key_points.append(translated_kp)
            kp_reports.append(kp_report)

        # Translate script_text
        translated_script, script_report = await self._translate_and_verify(
            text=script_text, source_language=source_language, target_language=target_language,
            client=client, context=context, field_name=f"page{page_id}.script_text",
        )

        # --- 修复：page级聚合逻辑 ---
        all_field_reports = [title_report] + kp_reports + [script_report]

        # final_passed: 每个field都passed才算page passed
        final_passed = all(r.get("passed", False) for r in all_field_reports)

        # 聚合指标：取所有field的平均
        n = max(len(all_field_reports), 1)
        avg_semantic = sum(r.get("semantic_score", 0) for r in all_field_reports) / n
        avg_term = sum(r.get("term_coverage", 0) for r in all_field_reports) / n

        # formula: 全passed才算passed
        all_formulas = all(r.get("formula_check", "failed") == "passed" for r in all_field_reports)

        # llm: 全consistent才算consistent
        all_llm = all(r.get("llm_judgment", "INCONSISTENT") == "CONSISTENT" for r in all_field_reports)

        # iterations: 取最大
        max_iter = max((r.get("iterations", 0) for r in all_field_reports), default=0)

        translated_page = {
            "page_id": page_id,
            "title": translated_title,
            "key_points": translated_key_points,
            "script_text": translated_script,
        }

        page_report = {
            "page_id": page_id,
            "semantic_score": round(avg_semantic, 4),
            "term_coverage": round(avg_term, 4),
            "formula_check": "passed" if all_formulas else "failed",
            "llm_judgment": "CONSISTENT" if all_llm else "INCONSISTENT",
            "iterations": max_iter,
            "final_passed": final_passed,
            "field_details": all_field_reports,
        }

        return translated_page, page_report

    async def _translate_and_verify(
        self,
        text: str,
        source_language: str,
        target_language: str,
        client: httpx.AsyncClient,
        context: str = "",
        field_name: str = "",
        max_iterations: int = MAX_VERIFY_ITERATIONS,
    ) -> Tuple[str, Dict]:
        if not text or not text.strip():
            return text, {
                "field": field_name,
                "semantic_score": 1.0,
                "term_coverage": 1.0,
                "formula_check": "passed",
                "llm_judgment": "CONSISTENT",
                "residual_check": "passed",
                "iterations": 0,
                "passed": True,
            }

        fix_instructions = ""
        best_translation = ""
        best_result: Optional[VerificationResult] = None

        for iteration in range(1, max_iterations + 1):
            logger.info(f"[{field_name}] Iteration {iteration}/{max_iterations}")

            # Translate
            translated = await llm_translate(
                text=text, target_language=target_language,
                client=client, context=context, fix_instructions=fix_instructions,
            )

            # Quick residual check before full verification
            residuals = contains_non_target_chars(translated, target_language)
            if residuals:
                logger.warning(f"[{field_name}] Residual chars detected: {residuals[:3]}, will affect verification")

            # Full verify
            vr = await verify_translation(
                original_text=text, translated_text=translated,
                source_language=source_language, target_language=target_language,
                semantic_checker=self.semantic_checker, client=client,
            )

            # Track best
            if best_result is None or vr.semantic_score > best_result.semantic_score:
                # Prefer results without residuals
                if best_result is None or (vr.residual_check == "passed") or (best_result.residual_check != "passed"):
                    best_translation = translated
                    best_result = vr

            if vr.passed:
                logger.info(f"[{field_name}] PASSED at iteration {iteration}")
                return translated, {
                    "field": field_name,
                    **vr.to_dict(),
                    "iterations": iteration,
                    "passed": True,
                }

            fix_instructions = vr.fix_instructions
            logger.warning(f"[{field_name}] Failed iteration {iteration}: {fix_instructions[:200]}")

        # Max iterations reached
        logger.warning(
            f"[{field_name}] Max iterations reached. "
            f"Best: semantic={best_result.semantic_score:.3f}, residual={best_result.residual_check}"
        )

        if best_result.semantic_score < 0.5:
            logger.error(f"[{field_name}] Semantic too low, fallback to original")
            return text, {
                "field": field_name,
                **best_result.to_dict(),
                "iterations": max_iterations,
                "passed": False,
                "fallback": True,
            }

        return best_translation, {
            "field": field_name,
            **best_result.to_dict(),
            "iterations": max_iterations,
            "passed": False,
        }

    def _detect_source_language(self, pages: List[Dict]) -> str:
        sample = ""
        for page in pages[:3]:
            sample += page.get("title", "") + " "
            sample += page.get("script_text", "")[:200] + " "

        total = max(len(sample.strip()), 1)

        cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", sample))
        if cjk / total > 0.3:
            return "Chinese"

        jp = len(re.findall(r"[\u3040-\u309f\u30a0-\u30ff]", sample))
        if jp / total > 0.1:
            return "Japanese"

        kr = len(re.findall(r"[\uac00-\ud7af]", sample))
        if kr / total > 0.1:
            return "Korean"

        return "Chinese"


# -----------------------------
# CLI
# -----------------------------
def main():
    import argparse

    parser = argparse.ArgumentParser(description="S2 Translation Agent v2")
    parser.add_argument("--task-id", type=str, required=True)
    parser.add_argument("--source-json", type=str, required=True)
    parser.add_argument("--target-language", type=str, default="English")
    parser.add_argument("--workspace", type=str, default=WORKSPACE_ROOT)
    args = parser.parse_args()

    agent = TranslateAgent(workspace_root=args.workspace)
    result = agent.run(
        task_id=args.task_id,
        source_json=args.source_json,
        target_language=args.target_language,
    )

    print("\n" + "=" * 60)
    print("Translation Report Summary")
    print("=" * 60)
    report = result.get("translation_report", {})
    print(f"Total pages:  {report.get('total_pages', 0)}")
    print(f"Passed:       {report.get('passed_pages', 0)}")
    print(f"Failed:       {report.get('failed_pages', 0)}")
    print(f"Output:       {result.get('output_json', 'N/A')}")

    for detail in report.get("details", []):
        status = "✅" if detail["final_passed"] else "❌"
        print(
            f"  Page {detail['page_id']}: {status} "
            f"semantic={detail['semantic_score']:.3f} "
            f"terms={detail['term_coverage']:.3f} "
            f"formula={detail['formula_check']} "
            f"llm={detail['llm_judgment']} "
            f"iters={detail['iterations']}"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
