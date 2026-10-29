"""Generate page-aligned lecture text when an uploaded course has no DOCX script."""

import json
from pathlib import Path

from .narration import validate_spoken_text
from .gateway import GatewayError
from .narration_style import STYLE_VERSION, DIRECT_TEACHING_RULE, review_teaching_style, style_warning


def generate_upload_lecture(structure, gateway, source_language, output_dir, *, slide_images=None, progress_callback=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = structure.get("pages") or []
    if not pages:
        raise ValueError("课件没有可生成讲稿的页面")
    results = []
    source_pdf = Path(structure["source_pdf"]) if structure.get("source_pdf") else None
    for page in pages:
        page_id = page["page_id"]
        source = {
            "page_id": page_id,
            "title": page.get("title", ""),
            "key_points": page.get("key_points") or [],
            "formulas": page.get("formulas") or [],
        }
        image_path = Path(slide_images[int(page_id) - 1]) if slide_images is not None else None
        if image_path is not None and not image_path.is_file():
            raise ValueError(f"第 {page_id} 页课件画面不存在")
        if source_pdf and source_pdf.is_file():
            import pymupdf
            with pymupdf.open(source_pdf) as document:
                source["pdf_text"] = document[int(page_id) - 1].get_text(sort=True).strip()
        if not source["title"] and not source["key_points"] and not source["formulas"]:
            raise ValueError(f"第 {page_id} 页没有可读取内容，需要教师提供逐页讲稿")
        request = {"sourceLanguage": source_language, "page": source,
                   "slideImage": str(image_path.resolve()) if image_path else None,
                   "narrationStyleVersion": STYLE_VERSION}
        checkpoint = output_dir / f"page-{int(page_id):03d}.json"
        saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else {}
        text = saved.get("script_text") if saved.get("request") == request else None
        if text is not None:
            try:
                text = validate_spoken_text(text)
            except ValueError:
                text = None
        style = review_teaching_style(text)
        if text is not None and not style['passed']:
            if saved.get('narration_style_review', {}).get('continuedAfterRetries'):
                style['continuedAfterRetries'] = True
            else:
                text = None
        if text is None:
            prompt = (
                "Write spoken teaching narration in the stated source language for exactly one slide. "
                "Return JSON with one key: script_text. Explain every substantive point and mathematical "
                "condition in natural speech. Use only the supplied slide content. Do not invent facts, "
                "examples, values, or missing labels. Spell equations and variable names as spoken words: "
                "do not write equals signs, mathematical symbols, TeX, underscores, Markdown or production instructions. "
                "Examine the provided slide image as well as extracted text. Explain informative figures, "
                "diagrams, photographs and visible labels when they contribute to the lesson. "
                "If an image is unclear, do not invent its content. "
                "The pdf_text field, when present, helps reconstruct words fragmented by PDF text extraction. "
                "If the slide has insufficient content, return an empty script_text.\n"
                + DIRECT_TEACHING_RULE + '\n'
                + json.dumps(request, ensure_ascii=False)
            )
            candidate = None
            for attempt in range(4):
                if progress_callback:
                    progress_callback(int(page_id),attempt+1)
                answer = None
                try:
                    options = {'image_paths': [image_path]} if image_path else {}
                    answer = gateway.respond_json(prompt, reasoning_effort="medium", max_output_tokens=2500,
                        json_retries=0, json_record_dir=output_dir/f'page-{int(page_id):03d}.responses'/f'attempt-{attempt+1}', **options)
                    text = answer.get("script_text") if isinstance(answer, dict) else None
                    text = validate_spoken_text(text)
                    candidate = text
                    style = review_teaching_style(text)
                    if not style['passed']:
                        raise ValueError('请直接讲授知识，不要报告幻灯片介绍或展示了什么：'+', '.join(style['matches']))
                    break
                except (GatewayError, ValueError, TypeError) as error:
                    rejected = output_dir / f"page-{int(page_id):03d}.rejected-{attempt + 1}.json"
                    rejected.write_text(json.dumps({"request": request, "response": answer,
                                                    "error": str(error)}, ensure_ascii=False), encoding="utf-8")
                    if attempt == 3:
                        if candidate is None:
                            raise ValueError(f"第 {page_id} 页讲稿生成失败，请上传逐页 DOCX 讲稿")
                        text = candidate
                        style = {**review_teaching_style(text), 'continuedAfterRetries': True}
                        break
                    prompt += ("\nThe previous response failed validation: " + str(error)
                               + ". Rewrite it as complete spoken sentences without formula notation."
                               + "\nPrevious response: " + json.dumps(answer, ensure_ascii=False))
            checkpoint.write_text(
                json.dumps({"request": request, "script_text": text, "narration_style_review": style}, ensure_ascii=False),
                encoding="utf-8",
            )
        result = {"page_id": page_id, "script_text": text, "script_source": "generated_from_slide",
                  "narration_style_review": style}
        if not result['narration_style_review']['passed']:
            result['narration_warning'] = style_warning(page_id)
        results.append(result)
        if progress_callback:
            progress_callback(int(page_id),0)
    return results
