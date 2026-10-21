"""Run PDF translation outside the shared HTTP worker process."""
import json
import os
import subprocess
import sys
from pathlib import Path


def translate_pdf_in_worker(source, destination, settings, language, font_file):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                       SMARTCOURSE_GATEWAY_URL=settings.gateway_url,
                       SMARTCOURSE_GATEWAY_MODEL=settings.gateway_model,
                       KIMI_API_KEY=settings.gateway_token)
    command = [sys.executable, '-m', 'app.pdf_worker', str(source), str(destination), language, str(Path(font_file).resolve())]
    with destination.with_suffix('.worker.log').open('a') as log:
        completed = subprocess.run(command, env=environment, stdout=log, stderr=log, timeout=3600)
    record_path = destination.with_suffix('.worker-result.json')
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    if completed.returncode or record.get('status') != 'completed':
        raise RuntimeError(record.get('message') or 'PDF 翻译工作进程未完成，请查看任务日志')
    if not destination.is_file():
        raise RuntimeError('PDF 工作进程未返回输出文件')
    return record['result']
