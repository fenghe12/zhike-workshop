"""Validate uploads and keep every upload in an independent directory."""
from __future__ import annotations

import io
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def save_upload(root: Path, filename: str, kind: str, content: bytes) -> dict:
    allowed = {
        "ppt": {".pptx", ".pdf"},
        "script": {".docx"},
        "audio": {".wav", ".mp3", ".m4a", ".flac", ".ogg"},
        "image": {".png", ".jpg", ".jpeg", ".webp"},
    }
    if kind not in allowed:
        raise ValueError("不支持的素材类型")
    if not filename or filename in {".", ".."} or any(c in filename for c in ("/", "\\", "\x00")):
        raise ValueError("文件名无效")
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed[kind]:
        raise ValueError("文件扩展名与素材类型不匹配")
    if not content:
        raise ValueError("不能上传空文件")
    limit = 280 * 1024 * 1024 if kind == 'ppt' else 20 * 1024 * 1024
    if len(content) > limit:
        raise ValueError(f'文件超过允许大小：{limit // (1024 * 1024)} MB')
    if kind=='ppt' and suffix=='.pdf':
        from .pdf_validation import pdf_page_count
        pdf_page_count(content=content)
    elif kind in {"ppt", "script"}:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as package:
                main = "ppt/presentation.xml" if kind == "ppt" else "word/document.xml"
                if not {"[Content_Types].xml", main}.issubset(package.namelist()):
                    raise ValueError("文件不包含有效的 Office 文档结构")
                if kind == 'script':
                    if package.getinfo(main).file_size > 10 * 1024 * 1024:
                        raise ValueError('讲稿正文超过允许大小')
                    document = ET.fromstring(package.read(main))
                    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
                    if document.tag != '{' + ns + '}document':
                        raise ValueError('DOCX 正文结构无效')
                    if not any((node.text or '').strip() for node in document.iter('{' + ns + '}t')):
                        raise ValueError('DOCX 讲稿没有正文')
        except zipfile.BadZipFile as exc:
            raise ValueError("文件不是有效的 Office 文档") from exc
        except ET.ParseError as exc:
            raise ValueError('DOCX 正文损坏，无法读取') from exc
    if kind == "image":
        signatures = {
            ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": content.startswith(b"\xff\xd8\xff"),
            ".jpeg": content.startswith(b"\xff\xd8\xff"),
            ".webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        }
        if not signatures[suffix]:
            raise ValueError("图片内容与扩展名不匹配")
        try:
            from PIL import Image
            with Image.open(io.BytesIO(content)) as picture:
                picture.verify()
        except Exception as exc:
            raise ValueError('图片文件损坏或无法读取，请重新选择。') from exc
    if kind == "audio":
        signatures = {
            ".wav": content.startswith(b"RIFF") and content[8:12] == b"WAVE",
            ".mp3": content.startswith(b"ID3") or (len(content) > 1 and content[0] == 255 and content[1] & 224 == 224),
            ".m4a": content[4:8] == b"ftyp",
            ".flac": content.startswith(b"fLaC"),
            ".ogg": content.startswith(b"OggS"),
        }
        if not signatures[suffix]:
            raise ValueError("音频内容与扩展名不匹配")
    upload_id = uuid.uuid4().hex
    directory = root / "uploads" / kind / upload_id
    directory.mkdir(parents=True, exist_ok=False)
    stored_name = "source" + suffix
    (directory / stored_name).write_bytes(content)
    return {"id": upload_id, "name": filename, "size": len(content),
            "path": f"/artifacts/uploads/{kind}/{upload_id}/{stored_name}"}
