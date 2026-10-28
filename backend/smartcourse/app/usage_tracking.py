"""Persistent first-party usage events; no third-party telemetry."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

KINDS = {'page_view', 'result_play', 'result_download', 'example_selected', 'login', 'register'}


class UsageStore:
    def __init__(self, root):
        self.path = Path(root)/'usage.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, kind TEXT NOT NULL, task_id TEXT, created REAL NOT NULL, detail TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS events_user_time ON events(user_id, created)')
            db.execute('CREATE INDEX IF NOT EXISTS events_kind_time ON events(kind, created)')
            if 'network' not in {row['name'] for row in db.execute('PRAGMA table_info(events)')}:
                db.execute("ALTER TABLE events ADD COLUMN network TEXT NOT NULL DEFAULT '{}'")
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def record(self, user_id, kind, detail=None, event_id=None, task_id=None, network=None):
        if kind not in KINDS:
            raise ValueError('使用记录类型无效')
        event_id = event_id or uuid.uuid4().hex
        if not isinstance(event_id, str) or len(event_id) > 100:
            raise ValueError('使用记录编号无效')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO events (id,user_id,kind,task_id,created,detail,network) VALUES (?,?,?,?,?,?,?)',
                       (user_id+":"+event_id, user_id, kind, task_id, time.time(), json.dumps(detail or {}, ensure_ascii=False),json.dumps(network or {},ensure_ascii=False)))
        return {'saved': True}

    def rows(self, start=None, end=None, user_id=None):
        sql, args = 'SELECT * FROM events WHERE 1=1', []
        for condition, value in [('created >= ?', start), ('created < ?', end), ('user_id = ?', user_id)]:
            if value is not None:
                sql += ' AND '+condition
                args.append(value)
        with self.connect() as db:
            return [dict(row, detail=json.loads(row['detail']), network=json.loads(row['network'])) for row in db.execute(sql+' ORDER BY created', args)]
