"""Resume only media generated for the same task and exact reference input."""
import json
import shutil
import uuid
from pathlib import Path


def read_record(path):
    try:
        value=json.loads(Path(path).read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def write_record(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.pending')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2));temporary.replace(path)


def reference_version(directory,source,kind):
    directory=Path(directory)/'reference-versions';directory.mkdir(parents=True,exist_ok=True)
    current=directory/(kind+'.json');record=read_record(current)
    source=Path(source);content=source.read_bytes()
    saved=directory/str(record.get('file','missing'))
    if record.get('version') and saved.is_file() and saved.read_bytes()==content:
        return record['version']
    version=uuid.uuid4().hex;name=version+source.suffix.lower()
    (directory/name).write_bytes(content)
    write_record(current,{'version':version,'file':name})
    return version
