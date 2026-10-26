"""Bounded compute requests; cloud credentials stay in the operator's controller."""
from pathlib import Path
import json, os, secrets, time

from .account_security import AuthSecurityError
from .remote_media import media_service_status
from .task_model import utc_now


class ComputeControl:
    def __init__(self, app):
        self.app = app
        self.last_heartbeat = 0

    def authorize(self, handler):
        filename = os.environ.get('SMARTCOURSE_CONTROL_TOKEN_FILE')
        if not filename or not Path(filename).is_file():
            raise AuthSecurityError('计算管理服务尚未配置。', 503)
        expected = Path(filename).read_text().strip()
        actual = handler.headers.get('X-Smartcourse-Control', '')
        if len(expected) < 32 or not secrets.compare_digest(expected, actual):
            raise AuthSecurityError('无权管理计算服务。', 403)
        self.last_heartbeat = time.time()

    def status(self, owner):
        requests = self.app.store.snapshot().get('computeRequests', [])
        return {'status': media_service_status(), 'controllerAvailable': time.time()-self.last_heartbeat < 90,
                'requests': [r for r in requests if r['owner'] == owner][-5:]}

    def get(self, handler, path):
        if path == '/v1/compute/status':
            handler._json(200, self.status(handler._user_id(required=True)))
            return True
        if path == '/v1/compute/control':
            self.authorize(handler)
            data = self.app.store.snapshot()
            running = [t for t in data['tasks'].values() if t.get('status') in {'processing', 'running'}
                       or t.get('status') == 'queued' and t.get('queue', {}).get('state') == 'queued']
            active = [t for t in running if int(t.get('currentStage', 1)) < 5]
            handler._json(200, {'activeTaskCount': len(active), 'requests': data.get('computeRequests', []),
                               'cpuOnlyTaskCount': len(running)-len(active),
                               'status': media_service_status()})
            return True
        return False

    def post(self, handler, path, payload):
        if path == '/v1/compute/request':
            owner = handler._agreement_user()
            if time.time()-self.last_heartbeat >= 90:
                raise AuthSecurityError('生成服务暂未开放启动，请联系项目管理员。', 503)
            maximum = self.app.product_services.preferences(owner)['maxTaskBudgetCny']
            budget = payload.get('budgetCny', maximum)
            if isinstance(budget, bool) or not isinstance(budget, (float, int)) or not .1 <= budget <= maximum:
                raise ValueError('启动预算超出单任务预算。')
            self.app.account_security.hit('compute-request:'+owner, 3, 3600)
            def enqueue(data):
                requests = data.setdefault('computeRequests', [])
                existing = next((r for r in requests if r['owner'] == owner and r['status'] == 'pending'), None)
                if existing:
                    return existing
                value = {'id': secrets.token_urlsafe(12), 'owner': owner, 'budgetCny': budget,
                         'requestedAt': utc_now(), 'status': 'pending'}
                requests.append(value)
                del requests[:-100]
                return value
            handler._json(202, self.app.store.transact(enqueue))
            return True
        if path == '/v1/compute/control':
            self.authorize(handler)
            request_ids = payload.get('requestIds') or []
            def acknowledge(data):
                for item in data.get('computeRequests', []):
                    if item['id'] in request_ids:
                        item.update(status=payload.get('requestStatus', 'accepted'), updatedAt=utc_now())
            self.app.store.transact(acknowledge)
            state = payload.get('computeState')
            if state is not None:
                filename = os.environ.get('SMARTCOURSE_REMOTE_STATE')
                if not filename or not isinstance(state, dict) or state.get('status') not in {'STARTING', 'RUNNING', 'STOPPED'}:
                    raise ValueError('计算状态格式无效。')
                owner = os.environ.get('SMARTCOURSE_COMPUTE_OWNER')
                if state.get('smartcourseOwner') != owner:
                    raise ValueError('计算资源归属无效。')
                if state['status'] == 'RUNNING' and not time.time() < float(state.get('smartcourseDeadline', 0)) <= time.time()+7200:
                    raise ValueError('计算服务必须设置两小时以内的停止时间。')
                target = Path(filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix('.update')
                temporary.write_text(json.dumps(state))
                temporary.chmod(0o600)
                temporary.replace(target)
            handler._json(200, {'updated': True})
            return True
        return False
