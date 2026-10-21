from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests


BLOCK_TAGS = {"title", "h1", "h2", "h3", "h4", "p", "li"}
SKIP_TAGS = {"script", "style", "svg", "nav", "footer", "noscript"}


class StructuredTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.active_tag = ""
        self.buffer: list[str] = []
        self.blocks: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        if self.skip_depth == 0 and tag in BLOCK_TAGS:
            self.active_tag = tag
            self.buffer = []

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if self.skip_depth == 0 and tag == self.active_tag:
            text = " ".join("".join(self.buffer).split())
            if len(text) >= 16:
                self.blocks.append({"type": tag, "text": text})
            self.active_tag = ""
            self.buffer = []
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str):
        if self.skip_depth == 0 and self.active_tag:
            self.buffer.append(data)


class OfficialWebCollector:
    def __init__(self, timeout: int = 30, maximum_characters: int = 40000):
        self.timeout = timeout
        self.maximum_characters = maximum_characters

    def collect(self, registry: str | Path, output_dir: str | Path) -> dict:
        registry_value = json.loads(Path(registry).read_text(encoding="utf-8"))
        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        records = []
        for source in registry_value.get("sources", []):
            source_id = str(source["source_id"])
            mode = str(source.get("ingest_mode", "curated"))
            url = str(source.get("url", ""))
            record = {
                "sourceId": source_id,
                "url": url,
                "mode": mode,
                "collectedAt": datetime.now(timezone.utc).isoformat(),
                "status": "skipped",
                "blocks": [],
            }
            if not url or mode == "curated":
                records.append(record)
                continue
            try:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError("URL格式无效")
                response = requests.get(
                    url,
                    timeout=self.timeout,
                    headers={"User-Agent": "SmartCourse-RAG/2026.1 (+course indexing)"},
                )
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1"}:
                    response.encoding = response.apparent_encoding or "utf-8"
                if "html" not in content_type.lower():
                    record["status"] = "unsupported_content_type"
                    record["contentType"] = content_type
                    records.append(record)
                    (root / f"{source_id}.json").write_text(
                        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    continue
                parser = StructuredTextParser()
                parser.feed(response.text)
                unique_blocks = []
                seen = set()
                total = 0
                for block in parser.blocks:
                    text = block["text"]
                    if text in seen:
                        continue
                    if mode == "metadata_only" and block["type"] not in {"title", "h1", "h2", "h3"}:
                        continue
                    if total + len(text) > self.maximum_characters:
                        break
                    seen.add(text)
                    unique_blocks.append(block)
                    total += len(text)
                record["status"] = "ok"
                record["httpStatus"] = response.status_code
                record["contentType"] = content_type
                record["blocks"] = unique_blocks
                record["characterCount"] = total
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = str(exc)[:400]
            records.append(record)
            (root / f"{source_id}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        report = {
            "sourceCount": len(records),
            "successCount": sum(item["status"] == "ok" for item in records),
            "failedCount": sum(item["status"] == "failed" for item in records),
            "records": [{key: value for key, value in item.items() if key != "blocks"} for item in records],
        }
        (root / "collection_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
