"""Isolated PDF translation process, with an atomic result record."""
import json
import sys
from pathlib import Path
from .config import Settings
from .gateway import ResponsesGateway
from .pdf_translation import translate_native_pdf


def main():
    source, destination, language, font = sys.argv[1:]
    destination = Path(destination)
    record = destination.with_suffix('.worker-result.json')
    def save(value):
        pending = record.with_suffix('.pending.json')
        pending.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        pending.replace(record)
    try:
        result = translate_native_pdf(Path(source), destination, ResponsesGateway(Settings.from_env()), language, Path(font))
        save({'status':'completed', 'result':result})
    except Exception as error:
        save({'status':'failed', 'message':str(error)})
        raise


if __name__ == '__main__':
    main()
