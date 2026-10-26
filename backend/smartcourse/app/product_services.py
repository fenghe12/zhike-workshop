"""Account tools, resumable inputs, storage preferences, and generation estimates."""
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .account_email import AccountEmail, email_address
from .account_policy import validate_media_consent
from .account_security import AuthSecurityError
from .resumable_uploads import ResumableUploads
from .task_model import utc_now


class ProductServices:
    def __init__(self, app):
        self.app = app
        self.email = AccountEmail(app.account_security)
        self.uploads = ResumableUploads(app.settings.data_root, app.settings.artifact_root, app.store)
        self.closed = threading.Event()

    def preferences(self, owner):
        saved = self.app.store.snapshot().get('userPreferences', {}).get(owner, {})
        return {'retentionDays': 0, 'maxTaskBudgetCny': 10, **saved}

    def estimate(self, payload):
        minutes = max(.25, min(180, float(payload.get('durationMinutes') or 2)))
        languages = payload.get('targetLanguages') or ['zh-CN']
        count = len(set(languages)) if isinstance(languages, list) else 1
        if not 1 <= count <= 8:
            raise ValueError('输出语言数量无效。')
        pages = max(1, min(30, int(payload.get('totalPages') or 2)))
        rates = []
        for task in self.app.store.snapshot().get('tasks', {}).values():
            if task.get('excludeFromCostCalibration'):
                continue
            output = (task.get('outputs', {}).get('s5') or {}).get('languages') or {}
            duration = sum(float(item.get('durationSeconds') or item.get('duration') or 0)
                           for item in output.values() if isinstance(item, dict))
            elapsed = sum(float(stage.get('elapsedSeconds') or 0) for stage in task.get('stages', []))
            if task.get('status') == 'completed' and duration >= 10 and 0 < elapsed/duration < 50:
                rates.append(elapsed/duration)
        ratio = sorted(rates)[len(rates)//2] if rates else 4
        runtime = (minutes*count*ratio+pages*.25)
        hourly = float(os.environ.get('SMARTCOURSE_COMPUTE_HOURLY_CNY', '18.682'))
        lower, upper = round(runtime*.75, 1), round(runtime*1.6+5, 1)
        return {'estimatedMinutes': [lower, upper], 'estimatedComputeCny': [round(lower*hourly/60, 2), round(upper*hourly/60, 2)],
                'hourlyCny': hourly, 'sampleCount': len(rates), 'includesRestoration': False,
                'message': '估计包含所选语言的生成步骤；恢复环境、存储和流量费用另计。'}

    def _remove_upload(self, identifier, owner):
        if not re.fullmatch(r'[a-f0-9]{32}', identifier):
            raise ValueError('素材编号无效。')
        with self.app._execution_lock:
            def remove(data):
                asset = data.get('uploads', {}).get(identifier)
                if not asset or asset.get('createdBy') != owner:
                    raise AuthSecurityError('无权删除此素材。', 403)
                for task in data.get('tasks', {}).values():
                    if identifier in json.dumps([task.get('inputs'), task.get('assets')], ensure_ascii=False):
                        raise AuthSecurityError('素材仍被课程使用，请先删除对应课程。', 409)
                relative = asset['path'].removeprefix('/artifacts/')
                target = (self.app.settings.artifact_root/relative).resolve()
                root = (self.app.settings.artifact_root/'uploads').resolve()
                if not target.is_relative_to(root) or target.parent.is_symlink():
                    raise ValueError('素材存储位置无效。')
                if target.parent.exists():
                    shutil.rmtree(target.parent)
                del data['uploads'][identifier]
                return {'deleted': True, 'id': identifier}
            return self.app.store.transact(remove)

    def remove_task(self, identifier, owner):
        if not re.fullmatch(r'task_[a-f0-9]{12}', identifier):
            raise ValueError('任务编号无效。')
        with self.app._execution_lock:
            active = self.app._executions.get(identifier)
            if active and active.is_alive():
                raise AuthSecurityError('任务仍在执行，请等待停止后再删除。', 409)
            def remove(data):
                task = data['tasks'].get(identifier)
                if not task or task.get('createdBy') != owner:
                    raise AuthSecurityError('无权删除此课程。', 403)
                if task.get('status') in {'processing', 'running'}:
                    raise AuthSecurityError('任务仍在执行，请先取消。', 409)
                paths = {self.app.settings.artifact_root/'tasks'/identifier}
                if self.app.settings.workspace_root:
                    paths.add(self.app.settings.workspace_root/identifier)
                for path in paths:
                    if path.is_symlink():
                        raise ValueError('课程目录不能是符号链接。')
                    if path.is_dir():
                        shutil.rmtree(path)
                data['executionQueue'] = [m for m in data.get('executionQueue', []) if m['taskId'] != identifier]
                del data['tasks'][identifier]
                return {'deleted': True, 'id': identifier, 'filesDeleted': True}
            return self.app.store.transact(remove)

    def cleanup(self):
        self.uploads.cleanup()
        snapshot = self.app.store.snapshot()
        for task in snapshot.get('tasks', {}).values():
            owner = task.get('createdBy')
            days = self.preferences(owner)['retentionDays']
            if not days or task.get('status') not in {'completed', 'cancelled', 'failed'} or task.get('teacherDemoUsers'):
                continue
            try:
                updated = datetime.fromisoformat(task['updatedAt'].replace('Z', '+00:00')).timestamp()
                if time.time()-updated > days*86400:
                    self.remove_task(task['id'], owner)
            except (KeyError, ValueError, AuthSecurityError):
                continue
        for identifier, asset in self.app.store.snapshot().get('uploads', {}).items():
            owner = asset.get('createdBy')
            days = self.preferences(owner)['retentionDays']
            if not days:
                continue
            try:
                target = self.app.settings.artifact_root/asset['path'].removeprefix('/artifacts/')
                created = asset.get('createdAtEpoch') or target.stat().st_mtime
                if time.time()-created > days*86400:
                    self._remove_upload(identifier, owner)
            except (KeyError, ValueError, OSError, AuthSecurityError):
                continue

    def start(self):
        def work():
            while not self.closed.is_set():
                try:
                    self.cleanup()
                except Exception:
                    import logging
                    logging.exception('Scheduled input cleanup failed')
                self.closed.wait(3600)
        threading.Thread(target=work, name='smartcourse-retention', daemon=True).start()

    def get(self, handler, path):
        if path == '/v1/auth/capabilities':
            handler._json(200, {'emailEnabled': self.email.enabled, 'registrationEmailRequired': self.email.enabled})
            return True
        if path == '/v1/settings/storage':
            handler._json(200, self.preferences(handler._user_id(required=True)))
            return True
        if path == '/v1/uploads':
            owner = handler._user_id(required=True)
            handler._json(200, [asset for asset in self.app.store.snapshot().get('uploads', {}).values()
                                if asset.get('createdBy') == owner])
            return True
        match = re.fullmatch(r'/v1/uploads/resumable/([a-f0-9]{32})', path)
        if match:
            handler._json(200, self.uploads.status(match[1], handler._user_id(required=True)))
            return True
        return False

    def post(self, handler, path, payload):
        if path == '/v1/tasks/estimate':
            owner = handler._user_id(required=True)
            handler._json(200, {**self.estimate(payload), 'maxTaskBudgetCny': self.preferences(owner)['maxTaskBudgetCny']})
            return True
        if path == '/v1/auth/email/request':
            if not self.email.enabled:
                raise AuthSecurityError('邮箱服务暂未启用，请联系项目管理员。', 503)
            purpose = payload.get('purpose')
            address = email_address(payload.get('email'))
            if purpose == 'bind':
                handler._user_id(required=True)
            else:
                self.app.account_security.consume(payload.get('captchaId'), payload.get('captchaCode'))
            if purpose == 'reset':
                user = next((u for u in self.app.store.snapshot()['users'].values()
                             if u.get('email') == address and u.get('emailVerifiedAt')), None)
                if not user:
                    self.app.account_security.hit('unknown-reset:'+handler._client_identity(), 12, 3600)
                    handler._json(200, {'sent': True, 'expiresInSeconds': 600, 'retryAfterSeconds': 60})
                    return True
            handler._json(200, self.email.send(address, purpose, handler._client_identity()))
            return True
        if path == '/v1/auth/email/confirm':
            owner = handler._user_id(required=True)
            address = self.email.consume(payload.get('email'), 'bind', payload.get('code'))
            handler._json(200, {'user': self.app.store.bind_email(owner, address)})
            return True
        if path in {'/v1/auth/password/change', '/v1/auth/password/reset'}:
            password = payload.get('password')
            if password != payload.get('confirmPassword') or not isinstance(password, str) or not 6 <= len(password) <= 128:
                raise ValueError('两次输入的新密码须相同，长度为 6 至 128 位。')
            if path.endswith('/change'):
                owner = handler._user_id(required=True)
                self.app.account_security.check_attempts('password:'+owner)
                current = payload.get('currentPassword')
                if not isinstance(current, str) or not current:
                    raise ValueError('请填写当前密码。')
                try:
                    result = self.app.store.change_password(owner, password, current)
                except ValueError:
                    self.app.account_security.failed('password:'+owner)
                    raise
                self.app.account_security.succeeded('password:'+owner)
            else:
                address = self.email.consume(payload.get('email'), 'reset', payload.get('code'))
                user = next((u for u in self.app.store.snapshot()['users'].values()
                             if u.get('email') == address and u.get('emailVerifiedAt')), None)
                if not user:
                    raise ValueError('邮箱验证码或账号信息无效。')
                result = self.app.store.change_password(user['id'], password)
            handler._json(200, result, handler._session_cookie(result['accessToken']))
            return True
        if path == '/v1/uploads/resumable':
            owner = handler._agreement_user()
            consent = validate_media_consent(payload.get('mediaConsent'), owner) if payload.get('kind') in {'image', 'audio'} else None
            handler._json(201, self.uploads.begin(owner, payload, consent))
            return True
        match = re.fullmatch(r'/v1/uploads/resumable/([a-f0-9]{32})/complete', path)
        if match:
            handler._json(201, self.uploads.complete(match[1], handler._agreement_user()))
            return True
        return False

    def put(self, handler, path, payload=None):
        match = re.fullmatch(r'/v1/uploads/resumable/([a-f0-9]{32})/parts/(\d+)', path)
        if match:
            owner = handler._agreement_user()
            length = int(handler.headers.get('Content-Length', '0'))
            if not 0 < length <= self.uploads.chunk_size:
                raise ValueError('上传分段长度无效。')
            content = handler.rfile.read(length)
            handler._json(200, self.uploads.write(match[1], int(match[2]), owner, content))
            return True
        if path == '/v1/settings/storage' and payload is not None:
            owner = handler._user_id(required=True)
            days, budget = payload.get('retentionDays'), payload.get('maxTaskBudgetCny')
            if isinstance(days, bool) or days not in {0, 7, 30, 90}:
                raise ValueError('保留期限须为 7、30、90 天或永久保留。')
            if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not .1 <= budget <= 50:
                raise ValueError('单任务预算须为 0.1 至 50 元。')
            value = {'retentionDays': days, 'maxTaskBudgetCny': budget, 'updatedAt': utc_now()}
            self.app.store.transact(lambda data: data.setdefault('userPreferences', {}).update({owner: value}))
            handler._json(200, value)
            return True
        return False

    def delete(self, handler, path):
        owner = handler._user_id(required=True)
        match = re.fullmatch(r'/v1/uploads/resumable/([a-f0-9]{32})', path)
        if match:
            handler._json(200, self.uploads.discard(match[1], owner))
            return True
        match = re.fullmatch(r'/v1/uploads/([a-f0-9]{32})', path)
        if match:
            handler._json(200, self._remove_upload(match[1], owner))
            return True
        match = re.fullmatch(r'/v1/tasks/(task_[a-f0-9]{12})', path)
        if match:
            handler._json(200, self.remove_task(match[1], owner))
            return True
        return False
