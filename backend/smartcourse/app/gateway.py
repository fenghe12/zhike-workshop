from __future__ import annotations

import base64
import ast
import json
import mimetypes
import random
import re
import time
import uuid
import io
import os
import shutil
import subprocess
import tempfile
from http.client import HTTPException
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request

from .config import Settings


class GatewayError(RuntimeError):
    pass


def _curl_json(url, encoded, headers, timeout):
    """Use system TLS transport without placing credentials in command arguments."""
    with tempfile.TemporaryDirectory(prefix="smartcourse-request-") as temporary:
        root = Path(temporary)
        body, response = root / "request.json", root / "response.json"
        body.write_bytes(encoded)
        configuration = "url = " + json.dumps(url) + "\n"
        configuration += "\n".join("header = " + json.dumps(f"{key}: {value}") for key, value in headers.items())
        result = subprocess.run([shutil.which("curl"), "--config", "-", "--silent", "--show-error",
                                 "--connect-timeout", "20", "--max-time", str(timeout),
                                 "--data-binary", "@" + str(body), "--output", str(response),
                                 "--write-out", "%{http_code}"], input=configuration, text=True,
                                capture_output=True, timeout=timeout + 5)
        if result.returncode:
            raise GatewayError(f"HTTPS 传输失败，返回码 {result.returncode}")
        raw = response.read_bytes()
        status = int(result.stdout)
        if status >= 400:
            raise error.HTTPError(url, status, "API request failed", {}, io.BytesIO(raw))
        return json.loads(raw.decode("utf-8"))


def _embedded_kimi_key() -> str:
    """Credentials are supplied exclusively through runtime configuration."""
    return ""


def _file_as_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_text(payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            value = content.get("text")
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    if texts:
        return "\n".join(texts)

    for choice in payload.get("choices", []):
        if not isinstance(choice, dict):
            continue
        value = choice.get("text")
        if not value and isinstance(choice.get("message"), dict):
            value = choice["message"].get("content")
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    if texts:
        return "\n".join(texts)
    raise GatewayError("网关返回中没有可解析的文本内容")


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    starts = [(cleaned.find("{"), "{", "}"), (cleaned.find("["), "[", "]")]
    starts = [item for item in starts if item[0] >= 0]
    if not starts:
        raise GatewayError("网关文本中没有 JSON 对象")
    start, opening, closing = min(starts, key=lambda item: item[0])
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : index + 1])
    raise GatewayError("网关返回的 JSON 不完整")


class ResponsesGateway:
    def __init__(self, settings: Settings | None = None, timeout: int = 180):
        self.settings = settings or Settings.from_env()
        self.timeout = int(os.environ.get('SMARTCOURSE_GATEWAY_TIMEOUT', timeout))

    def respond(
        self,
        text: str,
        *,
        image_paths: Iterable[Path] = (),
        image_urls: Iterable[str] = (),
        reasoning_effort: str = "medium",
        max_output_tokens: int | None = None,
        response_schema: dict[str, Any] | None = None,
        retries: int = 4,
    ) -> str:
        token = self.settings.gateway_token or _embedded_kimi_key()
        if not token:
            raise GatewayError("缺少 KIMI_API_KEY 环境变量")

        if "api.kimi.com" in self.settings.gateway_url or self.settings.gateway_url.rstrip("/").endswith("chat/completions"):
            image_paths = tuple(image_paths)
            image_urls = tuple(image_urls)
            if (image_paths or image_urls) and "api.kimi.com" in self.settings.gateway_url:
                raise GatewayError("当前 Kimi 文本接口不接收图片输入")
            message_content: Any = text
            if image_paths or image_urls:
                message_content = [{"type": "text", "text": text}]
                message_content.extend({"type": "image_url", "image_url": {"url": _file_as_data_url(path)}} for path in image_paths)
                message_content.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
            body: dict[str, Any] = {
                "model": self.settings.gateway_model,
                "messages": [{"role": "user", "content": message_content}],
                "stream": False,
                "temperature": float(os.environ.get('SMARTCOURSE_GATEWAY_TEMPERATURE', '1')),
                # Kimi K3 may use part of the completion budget for reasoning.
                # Keep enough room for the final content even for short checks.
                "max_tokens": max(512, max_output_tokens or 8192),
            }
            if response_schema is not None:
                body["response_format"] = {"type": "json_object", "schema": response_schema}
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            }
        else:
            content: list[dict[str, str]] = [{"type": "input_text", "text": text}]
            for path in image_paths:
                content.append({"type": "input_image", "image_url": _file_as_data_url(path)})
            for url in image_urls:
                content.append({"type": "input_image", "image_url": url})

            body = {
                "model": self.settings.gateway_model,
                "input": [{"role": "user", "content": content}],
                "stream": False,
                "reasoning": {"effort": reasoning_effort, "summary": "detailed"},
            }
            if max_output_tokens:
                body["max_output_tokens"] = max_output_tokens

            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "BCS-APIHub-RequestId": str(uuid.uuid4()),
                "X-CHJ-GWToken": token,
            }

        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                if "api.kimi.com" in self.settings.gateway_url and shutil.which("curl"):
                    payload = _curl_json(self.settings.gateway_url, encoded, headers, self.timeout)
                else:
                    req = request.Request(self.settings.gateway_url, data=encoded, headers=headers, method="POST")
                    with request.urlopen(req, timeout=self.timeout) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                return _extract_text(payload)
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = GatewayError(f"网关 HTTP {exc.code}: {detail}")
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
            except (error.URLError, HTTPException, TimeoutError, subprocess.TimeoutExpired, json.JSONDecodeError, GatewayError) as exc:
                last_error = exc
            if attempt + 1 < retries:
                time.sleep(min(2**attempt, 12) + random.random())
        raise GatewayError(f"网关请求失败：{last_error}")

    def respond_json(self, text: str, **kwargs: Any) -> Any:
        for attempt in range(2):
            raw = self.respond(text, **kwargs)
            try:
                return extract_json(raw)
            except ValueError:
                if attempt == 1:
                    raise
                text += "\nReturn only valid JSON. Escape quotation marks and line breaks inside strings. Do not include commentary or Markdown fences."
