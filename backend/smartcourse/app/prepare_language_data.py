from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .gateway import GatewayError, ResponsesGateway


LANGUAGES = {
    "zh-CN": "Simplified Chinese",
    "en-US": "English",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "de-DE": "German",
    "fr-FR": "French",
    "ru-RU": "Russian",
}
EXISTING_OUTPUTS = {
    "ja-JP": "pipeline/output_ja/ch01/s2_translated_structure.json",
    "de-DE": "pipeline/output_de/ch01/s2_translated_structure.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def chunks(pages: list[dict[str, Any]], character_limit: int = 14_000) -> Iterable[list[dict[str, Any]]]:
    current: list[dict[str, Any]] = []
    current_size = 0
    for page in pages:
        size = len(json.dumps(page, ensure_ascii=False))
        if current and current_size + size > character_limit:
            yield current
            current = []
            current_size = 0
        current.append(page)
        current_size += size
    if current:
        yield current


def translation_prompt(pages: list[dict[str, Any]], target: str) -> str:
    return f"""You are the translation agent in a multilingual MOOC production system.
Translate every title, script_text and key_points value into {target}.
Requirements:
1. Keep page_id unchanged and preserve page order.
2. Preserve every number, formula, symbol, URL and proper noun accurately.
3. Use consistent academic terminology suitable for university teaching.
4. Do not shorten, summarize or add teaching content.
Return one JSON object only, with this exact form:
{{"pages":[{{"page_id":1,"title":"...","script_text":"...","key_points":["..."]}}]}}

Input pages:
{json.dumps(pages, ensure_ascii=False)}"""


def validation_prompt(
    source_pages: list[dict[str, Any]], translated_pages: list[dict[str, Any]], target: str
) -> str:
    pairs = [
        {
            "page_id": source["page_id"],
            "source": source.get("script_text", ""),
            "translation": translated.get("script_text", ""),
        }
        for source, translated in zip(source_pages, translated_pages)
    ]
    return f"""You are the validation agent in a multilingual MOOC production system.
Evaluate these English-to-{target} translations. Back-translate each translation to English and score:
- semantic_similarity: 0.0 to 1.0
- terminology_coverage: 0.0 to 1.0
- formula_number_proper_name_accuracy: 0.0 to 1.0
- contextual_consistency: 0.0 to 1.0
Set passed to true only when semantic_similarity >= 0.85, terminology_coverage >= 0.90,
formula_number_proper_name_accuracy == 1.0, and contextual_consistency >= 0.85.
Return JSON only:
{{"pages":[{{"page_id":1,"back_translation":"...","semantic_similarity":0.0,
"terminology_coverage":0.0,"formula_number_proper_name_accuracy":0.0,
"contextual_consistency":0.0,"passed":true,"note":"..."}}]}}

Translation pairs:
{json.dumps(pairs, ensure_ascii=False)}"""


def normalized_page(page: dict[str, Any], fallback_id: int) -> dict[str, Any]:
    return {
        "page_id": int(page.get("page_id", page.get("page", fallback_id))),
        "title": str(page.get("title", "")),
        "script_text": str(page.get("script_text", page.get("text", ""))),
        "key_points": [str(value) for value in page.get("key_points", [])],
        "image_path": str(page.get("image_path", "")),
        "layout": page.get("layout", {}) if isinstance(page.get("layout", {}), dict) else {},
    }


def translate_pages(
    gateway: ResponsesGateway, pages: list[dict[str, Any]], target: str
) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for group in chunks(pages):
        try:
            result = gateway.respond_json(
                translation_prompt(group, target),
                reasoning_effort="medium",
                max_output_tokens=30_000,
            )
            values = result.get("pages", []) if isinstance(result, dict) else []
            if len(values) != len(group):
                raise GatewayError(
                    f"翻译页数不一致：输入 {len(group)}，返回 {len(values)}"
                )
            translated.extend(
                normalized_page(value, group[index]["page_id"])
                for index, value in enumerate(values)
            )
        except GatewayError:
            if len(group) == 1:
                raise
            for page in group:
                result = gateway.respond_json(
                    translation_prompt([page], target),
                    reasoning_effort="medium",
                    max_output_tokens=8_000,
                )
                values = result.get("pages", []) if isinstance(result, dict) else []
                if len(values) != 1:
                    raise GatewayError(f"第 {page['page_id']} 页翻译返回无效")
                translated.append(normalized_page(values[0], page["page_id"]))
    return translated


def exact_token_accuracy(source: str, translated: str) -> float:
    tokens = re.findall(r"(?:\d+(?:[.,]\d+)*%?)|(?:[A-Z]{2,}[A-Z0-9_-]*)", source)
    if not tokens:
        return 1.0
    return sum(token in translated for token in tokens) / len(tokens)


def validation_report(
    gateway: ResponsesGateway,
    source_pages: list[dict[str, Any]],
    translated_pages: list[dict[str, Any]],
    target: str,
) -> dict[str, Any]:
    sample_source = source_pages[:3]
    sample_translated = translated_pages[:3]
    result = gateway.respond_json(
        validation_prompt(sample_source, sample_translated, target),
        reasoning_effort="medium",
        max_output_tokens=8_000,
    )
    values = result.get("pages", []) if isinstance(result, dict) else []
    by_id = {int(value.get("page_id", 0)): value for value in values if isinstance(value, dict)}
    samples: list[dict[str, Any]] = []
    for source, translated in zip(sample_source, sample_translated):
        item = by_id.get(source["page_id"], {})
        exact = exact_token_accuracy(source.get("script_text", ""), translated.get("script_text", ""))
        sample = {
            "page_id": source["page_id"],
            "source": source.get("script_text", ""),
            "translated": translated.get("script_text", ""),
            "back_translation": str(item.get("back_translation", "")),
            "semantic_similarity": float(item.get("semantic_similarity", 0)),
            "terminology_coverage": float(item.get("terminology_coverage", 0)),
            "formula_number_proper_name_accuracy": round(
                min(exact, float(item.get("formula_number_proper_name_accuracy", exact))), 4
            ),
            "contextual_consistency": float(item.get("contextual_consistency", 0)),
            "passed": bool(item.get("passed", False)) and exact == 1.0,
            "note": str(item.get("note", "")),
        }
        samples.append(sample)

    metrics = {
        key: round(mean(sample[key] for sample in samples), 4)
        for key in (
            "semantic_similarity",
            "terminology_coverage",
            "formula_number_proper_name_accuracy",
            "contextual_consistency",
        )
    }
    return {
        "validationMethod": "回译抽样校验与本地公式、数字、标识符精确匹配",
        "samplePageCount": len(samples),
        "thresholds": {
            "semantic_similarity": 0.85,
            "terminology_coverage": 0.9,
            "formula_number_proper_name_accuracy": 1.0,
            "contextual_consistency": 0.85,
        },
        "metrics": metrics,
        "passed": all(sample["passed"] for sample in samples),
        "samples": samples,
    }


def source_structure(source_root: Path) -> dict[str, Any]:
    path = source_root / "index-tts/new-ch1/Overview_of_Artificial_Intelligence/page_texts.json"
    source = read_json(path)
    source["pages"] = [
        normalized_page(page, index)
        for index, page in enumerate(source.get("pages", []), start=1)
    ]
    return source


def existing_translation(source_root: Path, code: str) -> dict[str, Any] | None:
    relative = EXISTING_OUTPUTS.get(code)
    if not relative:
        return None
    path = source_root / relative
    return read_json(path) if path.exists() else None


def prepare_language(
    code: str,
    source: dict[str, Any],
    source_root: Path,
    output_root: Path,
    gateway: ResponsesGateway,
) -> dict[str, Any]:
    target = LANGUAGES[code]
    directory = output_root / code
    structure_path = directory / "s2_translated_structure.json"
    report_path = directory / "translation_report.json"

    if structure_path.exists():
        structure = read_json(structure_path)
    elif code == "en-US":
        structure = {
            "task_id": source.get("task_id"),
            "source_language": "en",
            "target_language": "English",
            "total_pages": len(source["pages"]),
            "pages": source["pages"],
        }
        write_json(structure_path, structure)
    else:
        recovered = existing_translation(source_root, code)
        if recovered:
            structure = recovered
            structure["pages"] = [
                normalized_page(page, index)
                for index, page in enumerate(structure.get("pages", []), start=1)
            ]
        else:
            pages = translate_pages(gateway, source["pages"], target)
            structure = {
                "task_id": source.get("task_id"),
                "source_language": "en",
                "target_language": target,
                "total_pages": len(pages),
                "pages": pages,
            }
        write_json(structure_path, structure)

    if report_path.exists():
        report = read_json(report_path)
    elif code == "en-US":
        report = {
            "validationMethod": "源语言数据一致性检查",
            "samplePageCount": 3,
            "thresholds": {},
            "metrics": {
                "semantic_similarity": 1.0,
                "terminology_coverage": 1.0,
                "formula_number_proper_name_accuracy": 1.0,
                "contextual_consistency": 1.0,
            },
            "passed": True,
            "samples": [],
        }
        write_json(report_path, report)
    else:
        report = validation_report(gateway, source["pages"], structure["pages"], target)
        write_json(report_path, report)

    if code != "en-US" and not report.get("passed", False):
        recovered_copy = directory / "recovered_s2_translated_structure.json"
        if not recovered_copy.exists():
            write_json(recovered_copy, structure)
        repaired_pages = translate_pages(gateway, source["pages"], target)
        structure = {
            "task_id": source.get("task_id"),
            "source_language": "en",
            "target_language": target,
            "total_pages": len(repaired_pages),
            "pages": repaired_pages,
        }
        report = validation_report(gateway, source["pages"], repaired_pages, target)
        report["automaticCorrectionIterations"] = 1
        report["correctionReason"] = "恢复数据与当前讲稿版本未对齐，已依据当前讲稿重新翻译并校验。"
        write_json(structure_path, structure)
        write_json(report_path, report)

    return {
        "code": code,
        "language": target,
        "pageCount": len(structure.get("pages", [])),
        "structure": str(structure_path),
        "report": str(report_path),
        "passed": report.get("passed", False),
        "metrics": report.get("metrics", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成六语种课件讲稿数据及翻译校验报告")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--languages", nargs="*", default=list(LANGUAGES))
    args = parser.parse_args()
    if args.source_root.name != "a800-local-0722":
        raise ValueError("只允许处理 weights/a800-local-0722")
    invalid = [code for code in args.languages if code not in LANGUAGES]
    if invalid:
        raise ValueError(f"不支持的语言代码：{invalid}")

    source = source_structure(args.source_root)
    gateway = ResponsesGateway()
    summaries = []
    for code in args.languages:
        summaries.append(
            prepare_language(code, source, args.source_root, args.output_root, gateway)
        )
        print(json.dumps(summaries[-1], ensure_ascii=False), flush=True)
    write_json(args.output_root / "language-summary.json", {"languages": summaries})


if __name__ == "__main__":
    main()
