"""Generate page-aligned lecture text when an uploaded course has no DOCX script."""

import json
from pathlib import Path

from .narration import validate_spoken_text


def generate_upload_lecture(structure, gateway, source_language, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = structure.get("pages") or []
    if not pages:
        raise ValueError("课件没有可生成讲稿的页面")
    results = []
    source_pdf = Path(structure["source_pdf"]) if structure.get("source_pdf") else None
    for page in pages:
        page_id = page["page_id"]
        existing = str(page.get("script_text") or "").strip()
        if page.get("script_source") == "speaker_notes" and existing:
            results.append({"page_id": page_id, "script_text": existing, "script_source": "speaker_notes"})
            continue
        source = {
            "page_id": page_id,
            "title": page.get("title", ""),
            "key_points": page.get("key_points") or [],
            "formulas": page.get("formulas") or [],
        }
        if source_pdf and source_pdf.is_file():
            import pymupdf
            with pymupdf.open(source_pdf) as document:
                source["pdf_text"] = document[int(page_id) - 1].get_text(sort=True).strip()
        if not source["title"] and not source["key_points"] and not source["formulas"]:
            raise ValueError(f"第 {page_id} 页没有可读取内容，需要教师提供逐页讲稿")
        request = {"sourceLanguage": source_language, "page": source}
        checkpoint = output_dir / f"page-{int(page_id):03d}.json"
        saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.is_file() else {}
        text = saved.get("script_text") if saved.get("request") == request else None
        if text is not None:
            try:
                text = validate_spoken_text(text)
            except ValueError:
                text = None
        if text is None:
            prompt = (
                "Write spoken teaching narration in the stated source language for exactly one slide. "
                "Return JSON with one key: script_text. Explain every substantive point and mathematical "
                "condition in natural speech. Use only the supplied slide content. Do not invent facts, "
                "examples, values, or missing labels. Spell equations and variable names as spoken words: "
                "do not write equals signs, mathematical symbols, TeX, underscores, Markdown or production instructions. "
                "The pdf_text field, when present, helps reconstruct words fragmented by PDF text extraction. "
                "If the slide has insufficient content, return an empty script_text.\n"
                + json.dumps(request, ensure_ascii=False)
            )
            for attempt in range(3):
                answer = gateway.respond_json(prompt, reasoning_effort="medium", max_output_tokens=2500)
                text = answer.get("script_text") if isinstance(answer, dict) else None
                try:
                    text = validate_spoken_text(text)
                    break
                except ValueError as error:
                    rejected = output_dir / f"page-{int(page_id):03d}.rejected-{attempt + 1}.json"
                    rejected.write_text(json.dumps({"request": request, "response": answer,
                                                    "error": str(error)}, ensure_ascii=False), encoding="utf-8")
                    if attempt == 2:
                        raise ValueError(f"第 {page_id} 页讲稿生成失败，请上传逐页 DOCX 讲稿")
                    prompt += ("\nThe previous response failed validation: " + str(error)
                               + ". Rewrite it as complete spoken sentences without formula notation."
                               + "\nPrevious response: " + json.dumps(answer, ensure_ascii=False))
            checkpoint.write_text(
                json.dumps({"request": request, "script_text": text}, ensure_ascii=False),
                encoding="utf-8",
            )
        results.append({"page_id": page_id, "script_text": text, "script_source": "generated_from_slide"})
    return results
