"""Build user downloads without private export checkpoints or partial files."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def archive_course(directory, destination):
    directory = Path(directory).resolve()
    destination = Path(destination).resolve()
    if destination.is_relative_to(directory):
        raise ValueError('下载压缩包必须位于课程目录之外')
    pending = destination.with_name('.' + destination.name + '.pending')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(pending, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(directory)
            if any(part.startswith('.') for part in relative.parts):
                continue
            if path.name.endswith(('.export.json', '.pending.json')):
                continue
            if path.is_symlink():
                raise ValueError('交付目录不能包含符号链接')
            if path.is_file():
                archive.write(path, relative.as_posix())
    pending.replace(destination)
    return destination
