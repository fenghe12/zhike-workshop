from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .task_model import utc_now


class JsonStore:
    def __init__(self, path: Path, task_template_path: Path | None = None):
        self.path = path
        self.task_template_path = task_template_path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with self._file_lock():
            if not self.path.exists():
                initial: dict[str, Any] = {"users": {}, "tokens": {}, "tasks": {}}
                if task_template_path and task_template_path.exists():
                    task = json.loads(task_template_path.read_text(encoding="utf-8"))
                    initial["tasks"][task["id"]] = task
                self._write(initial)

    @contextmanager
    def _file_lock(self, shared: bool = False):
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        previous = self.path.stat() if self.path.exists() else None
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            if previous is not None and os.geteuid() == 0:
                os.chown(temporary, previous.st_uid, previous.st_gid)
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.path.chmod(0o600)

    def transact(self, operation):
        with self._lock:
            with self._file_lock():
                data = self._read()
                result = operation(data)
                self._write(data)
                return copy.deepcopy(result)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            with self._file_lock(shared=True):
                return copy.deepcopy(self._read())

    @staticmethod
    def _password_hash(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return f"{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"

    @staticmethod
    def _password_matches(password: str, encoded: str) -> bool:
        salt_value, _ = encoded.split(":", 1)
        salt = base64.b64decode(salt_value)
        return hmac.compare_digest(JsonStore._password_hash(password, salt), encoded)

    def register(
        self, phone: str, password: str, display_name: str, institution: str = "", policy_consent=None, verified_email=None
    ) -> dict[str, Any]:
        phone = phone.strip()
        display_name = display_name.strip() or "智课用户"
        if len(phone) < 6 or len(password) < 6:
            raise ValueError("账号和密码均须至少 6 个字符")
        if len(phone) > 128 or any(character.isspace() for character in phone):
            raise ValueError("账号不能包含空格，且不能超过 128 个字符")
        if len(password) > 128 or not password.strip():
            raise ValueError("密码须为 6 至 128 个字符，且不能全部为空格")

        def operation(data):
            if phone in data["users"]:
                raise ValueError("该账号已注册")
            user = {
                "id": f"user_{secrets.token_hex(6)}",
                "phone": phone,
                "displayName": display_name,
                "institution": institution.strip(),
                "passwordHash": self._password_hash(password),
                "createdAt": utc_now(),
            }
            if verified_email:
                if any(u.get('email') == verified_email for u in data['users'].values()):
                    raise ValueError('该邮箱已绑定其他账号。')
                user.update(email=verified_email, emailVerifiedAt=utc_now())
            data["users"][phone] = user
            if policy_consent is not None:
                user['policyConsent'] = copy.deepcopy(policy_consent)
            return self._issue_token(data, user)

        return self.transact(operation)

    def login(self, phone: str, password: str, policy_consent=None) -> dict[str, Any]:
        def operation(data):
            user = data["users"].get(phone.strip())
            if not user or not self._password_matches(password, user["passwordHash"]):
                raise ValueError("账号或密码错误")
            if policy_consent is not None:
                user['policyConsent'] = copy.deepcopy(policy_consent)
            return self._issue_token(data, user)

        return self.transact(operation)

    def accept_policy(self, user_id, consent):
        def operation(data):
            user = next((x for x in data['users'].values() if x['id'] == user_id), None)
            if user is None:
                raise ValueError('账号不存在')
            user['policyConsent'] = copy.deepcopy(consent)
            return self._public_user(user)
        return self.transact(operation)

    def bind_email(self, user_id, email):
        def operation(data):
            if any(u.get('email') == email and u['id'] != user_id for u in data['users'].values()):
                raise ValueError('该邮箱已绑定其他账号。')
            user = next(u for u in data['users'].values() if u['id'] == user_id)
            user.update(email=email, emailVerifiedAt=utc_now())
            return self._public_user(user)
        return self.transact(operation)

    def change_password(self, user_id, password, current_password=None):
        if not isinstance(password, str) or not 6 <= len(password) <= 128:
            raise ValueError('新密码长度须为 6 至 128 位。')
        def operation(data):
            user = next(u for u in data['users'].values() if u['id'] == user_id)
            if current_password is not None and not self._password_matches(current_password, user['passwordHash']):
                raise ValueError('当前密码不正确。')
            user['passwordHash'] = self._password_hash(password)
            user['passwordChangedAt'] = utc_now()
            data['tokens'] = {key: token for key, token in data['tokens'].items() if token['userId'] != user_id}
            return self._issue_token(data, user)
        return self.transact(operation)

    @staticmethod
    def _public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in user.items() if key != "passwordHash"}

    def _issue_token(self, data: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        data["tokens"][token] = {"userId": user["id"], "createdAt": now.isoformat(),
                                  'expiresAt':(now+timedelta(days=7)).isoformat()}
        for old_token, record in list(data['tokens'].items()):
            if not self._token_current(record):
                del data['tokens'][old_token]
        return {"accessToken": token, "user": self._public_user(user)}

    def user_for_token(self, token: str) -> dict[str, Any] | None:
        data = self.snapshot()
        record = data["tokens"].get(token)
        if not record or not self._token_current(record):
            return None
        for user in data["users"].values():
            if user["id"] == record["userId"]:
                return self._public_user(user)
        return None

    @staticmethod
    def _token_current(record):
        try:
            created = datetime.fromisoformat(record['createdAt'].replace('Z','+00:00'))
            expires = datetime.fromisoformat(record['expiresAt'].replace('Z','+00:00')) if record.get('expiresAt') else created+timedelta(days=7)
            return datetime.now(timezone.utc) < expires.replace(tzinfo=expires.tzinfo or timezone.utc)
        except (KeyError, TypeError, ValueError):
            return False
