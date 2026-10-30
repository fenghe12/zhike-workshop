"""Synchronize a verified platform lease with the application's resource guard."""
import argparse
import json
import os
from pathlib import Path


def synchronize_compute_lease(path, platform_state, *, owner, deadline):
    path = Path(path)
    current = json.loads(path.read_text())
    if current.get('smartcourseOwner') != owner:
        raise ValueError('The runtime compute owner does not match.')
    if not platform_state.get('id') or current.get('id') != platform_state['id']:
        raise ValueError('The platform snapshot belongs to another compute instance.')
    lease = platform_state.get('lease') or {}
    if lease.get('enable') and lease.get('type') == 'TIMING':
        native_end = ((lease.get('create_at') or 0) + (lease.get('duration') or 0)) / 1000
        if float(deadline) > native_end:
            raise ValueError('The application deadline exceeds the platform lease.')
    updated = {**platform_state, 'smartcourseOwner': owner, 'smartcourseDeadline': float(deadline)}
    stat = path.stat()
    pending = path.with_name(path.name + '.lease-pending')
    try:
        with pending.open('w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            if hasattr(os, 'fchown'):
                os.fchown(stream.fileno(), stat.st_uid, stat.st_gid)
            json.dump(updated, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', required=True)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--deadline', required=True, type=float)
    args = parser.parse_args()
    value = synchronize_compute_lease(args.state, json.loads(Path(args.platform).read_text()),
                                      owner=args.owner, deadline=args.deadline)
    print(json.dumps({'synchronized': True, 'status': value['status'],
                      'deadline': value['smartcourseDeadline']}))


if __name__ == '__main__':
    main()
