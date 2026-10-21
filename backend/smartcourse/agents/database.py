"""
智课工坊 - 数据库模块 (SQLite)
用户注册/登录 + 任务管理
"""

import os
import sqlite3
import hashlib
import secrets
import time
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartcourse.db")

# ==================== 初始化 ====================

def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """建表（首次启动自动调用）"""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            salt        TEXT    NOT NULL,
            nickname    TEXT    DEFAULT '',
            avatar      TEXT    DEFAULT '',
            role        TEXT    DEFAULT 'user',
            status      INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            updated_at  TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            token       TEXT    UNIQUE NOT NULL,
            device      TEXT    DEFAULT 'web',
            expired_at  TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     TEXT    UNIQUE NOT NULL,
            user_id     INTEGER NOT NULL,
            mode        TEXT    NOT NULL,
            topic       TEXT    DEFAULT '',
            language    TEXT    DEFAULT 'English',
            pages       INTEGER DEFAULT 10,
            status      TEXT    DEFAULT 'pending',
            error_msg   TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            updated_at  TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_user  ON tasks(user_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_user  ON tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_token ON tokens(token);
    """)

    # 预置管理员
    cur = db.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
    if cur.fetchone()[0] == 0:
        _create_user(db, "admin", "admin123", role="admin")
        print("[DB] Default admin created: admin / admin123")

    db.commit()
    db.close()
    print(f"[DB] Initialized: {DB_PATH}")


# ==================== 密码工具 ====================

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def _create_user(db, username: str, password: str, role: str = "user") -> int:
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    cur = db.execute(
        "INSERT INTO users (username, password, salt, role) VALUES (?, ?, ?, ?)",
        (username, pw_hash, salt, role),
    )
    return cur.lastrowid


# ==================== 用户认证 ====================

def register(username: str, password: str) -> Dict:
    """注册新用户"""
    if len(username) < 3 or len(username) > 32:
        return {"error": "用户名长度3-32位"}
    if len(password) < 6:
        return {"error": "密码至少6位"}

    db = get_db()
    try:
        cur = db.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            return {"error": "用户名已存在"}
        uid = _create_user(db, username, password)
        db.commit()
        return {"user_id": uid, "username": username}
    finally:
        db.close()


def login(username: str, password: str) -> Dict:
    """登录，返回token"""
    db = get_db()
    try:
        cur = db.execute(
            "SELECT id, username, password, salt, role, status FROM users WHERE username=?",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return {"error": "用户名或密码错误"}
        if row["status"] != 1:
            return {"error": "账号已被禁用"}

        pw_hash = _hash_password(password, row["salt"])
        if pw_hash != row["password"]:
            return {"error": "用户名或密码错误"}

        # 生成token，有效期7天
        token = secrets.token_hex(32)
        expired = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 简单算7天后
        import datetime as dt
        expired = (dt.datetime.now() + dt.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        db.execute(
            "INSERT INTO tokens (user_id, token, expired_at) VALUES (?, ?, ?)",
            (row["id"], token, expired),
        )
        db.commit()

        return {
            "token": token,
            "user": {
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
            },
        }
    finally:
        db.close()


def verify_token(token: str) -> Optional[Dict]:
    """验证token，返回用户信息"""
    if not token:
        return None
    db = get_db()
    try:
        cur = db.execute(
            """SELECT u.id, u.username, u.role, t.expired_at
               FROM tokens t JOIN users u ON t.user_id=u.id
               WHERE t.token=? AND u.status=1""",
            (token,),
        )
        row = cur.fetchone()
        if not row:
            return None
        # 检查过期
        expired = row["expired_at"]
        if expired < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
            db.execute("DELETE FROM tokens WHERE token=?", (token,))
            db.commit()
            return None
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    finally:
        db.close()


def logout(token: str):
    """注销token"""
    db = get_db()
    try:
        db.execute("DELETE FROM tokens WHERE token=?", (token,))
        db.commit()
    finally:
        db.close()


def get_user_info(user_id: int) -> Optional[Dict]:
    """获取用户信息"""
    db = get_db()
    try:
        cur = db.execute(
            "SELECT id, username, nickname, avatar, role, created_at FROM users WHERE id=?",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        db.close()


# ==================== 任务管理 ====================

def create_task_record(task_id: str, user_id: int, mode: str,
                       topic: str = "", language: str = "English", pages: int = 10) -> bool:
    db = get_db()
    try:
        db.execute(
            "INSERT INTO tasks (task_id, user_id, mode, topic, language, pages) VALUES (?,?,?,?,?,?)",
            (task_id, user_id, mode, topic, language, pages),
        )
        db.commit()
        return True
    except Exception as e:
        print(f"[DB] create_task error: {e}")
        return False
    finally:
        db.close()


def update_task_status(task_id: str, status: str, error_msg: str = ""):
    db = get_db()
    try:
        db.execute(
            "UPDATE tasks SET status=?, error_msg=?, updated_at=datetime('now','localtime') WHERE task_id=?",
            (status, error_msg, task_id),
        )
        db.commit()
    finally:
        db.close()


def list_user_tasks(user_id: int) -> List[Dict]:
    db = get_db()
    try:
        cur = db.execute(
            """SELECT task_id, mode, topic, language, pages, status, error_msg, created_at, updated_at
               FROM tasks WHERE user_id=? ORDER BY created_at DESC""",
            (user_id,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        db.close()


def get_task_record(task_id: str) -> Optional[Dict]:
    db = get_db()
    try:
        cur = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def delete_task_record(task_id: str, user_id: int) -> bool:
    db = get_db()
    try:
        cur = db.execute("DELETE FROM tasks WHERE task_id=? AND user_id=?", (task_id, user_id))
        db.commit()
        return cur.rowcount > 0
    finally:
        db.close()


# ==================== 管理员 ====================

def list_all_users() -> List[Dict]:
    db = get_db()
    try:
        cur = db.execute(
            "SELECT id, username, nickname, role, status, created_at FROM users ORDER BY id"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        db.close()


def list_all_tasks() -> List[Dict]:
    db = get_db()
    try:
        cur = db.execute(
            """SELECT t.*, u.username FROM tasks t JOIN users u ON t.user_id=u.id
               ORDER BY t.created_at DESC LIMIT 100"""
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        db.close()
