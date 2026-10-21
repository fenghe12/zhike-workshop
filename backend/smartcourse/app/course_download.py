"""Download course inputs only from configured HTTPS storage hosts."""
import os
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
import requests


def validate_source_url(value, allowed_hosts):
    if not isinstance(value, str):
        raise ValueError('文件地址必须为 HTTPS URL')
    parsed = urlparse(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment):
        raise ValueError('文件地址必须为有效的 HTTPS 存储地址')
    if parsed.hostname.lower() not in {host.lower() for host in allowed_hosts}:
        raise ValueError('文件来源未配置，请先上传到已配置的存储服务')
    name = PurePosixPath(unquote(parsed.path)).name
    if not name or any(char in name for char in ('\\', '\x00')):
        raise ValueError('文件地址缺少有效文件名')
    return name


def download_course_input(url, kind):
    allowed = [host.strip() for host in os.environ.get('SMARTCOURSE_INPUT_HOSTS', '').split(',') if host.strip()]
    name = validate_source_url(url, allowed)
    limit = (200 if kind == 'ppt' else 20) * 1024 * 1024
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
            if 300 <= response.status_code < 400:
                raise ValueError('文件地址发生重定向，请使用存储文件的直接地址')
            response.raise_for_status()
            if int(response.headers.get('Content-Length', 0)) > limit:
                raise ValueError('文件超过允许大小')
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError('文件超过允许大小')
    if not data:
        raise ValueError('文件内容为空')
    return name, bytes(data)
