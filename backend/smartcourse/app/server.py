from __future__ import annotations

import argparse
import base64
import copy
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .adaptive_teaching import (
    ADAPTIVE_EXPERIMENT_CATALOG,
    build_adaptive_experiment,
    select_teaching_policy,
    update_learner_state,
)
from .advanced_experiments import (
    ADVANCED_EXPERIMENT_CATALOG,
    build_personalization_plan,
    check_pedagogical_alignment,
    prescreen_candidate,
    select_proactive_intervention,
    update_structured_memory,
)
from .config import Settings
from .code_lessons import get_lesson_spec, list_lesson_specs
from .full_pipeline import FullPipelineRunner, StageInputRequired, StageReviewRequired
from .experiment_runner import ExperimentRunner
from .experiment_analysis import analyze_learning_rows, build_experiment_protocol
from .demo_course import build_demo_course_manifest, prepare_demo_package
from .ai_intro_product import ai_intro_status, execute_fixed_ai_intro_interrupt
from .interactive_course import execute_fixed_interrupt, list_interruptions
from .pedagogical_ir import EXPERIMENT_CATALOG, build_e2_variants, compile_lesson_ir
from .store import JsonStore
from .account_security import AccountSecurity, AuthSecurityError
from .product_services import ProductServices
from .compute_control import ComputeControl
from .account_policy import accepted_policy, policy_documents, validate_policy_consent, validate_media_consent
from .task_queue import PersistentTaskQueue, TaskAlreadyQueued, with_queue_position
from .uploads import save_upload
from .translation_policy import validate_policy
from .user_feedback import list_feedback, submit_feedback
from .usage_tracking import UsageStore
from .visitor_traffic import IpLocator, client_ip
from .admin_console import AdminConsole
from .course_profile import normalize_profile, DOMAINS, AUDIENCES
from .task_model import create_task, retry_stage, safe_artifact_name, utc_now, replace_task_assets
from .teacher_features import (draft_blueprint, update_blueprint, approve_blueprint, reserve_unit_build, update_unit_build, get_unit_build, make_patch_plan, approve_patch_plan, create_question, generate_question_batch, review_question, attempt_question, question_stats, public_question, _read)
from .teacher_microcourse import assemble_units
from .patch_release import start_script_release, start_subtitle_release
from .quiz_remediation import submit_quiz_remediation, get_quiz_remediation
from .rehearsal_analyzer import analyze_rehearsal
from .s1_quality_system import AGENT_ROLES, RESEARCH_DIRECTIONS
from .teacher_avatar import (
    build_teacher_profile,
    longcat_engine_readiness,
    schedule_gestures,
    validate_profile_files,
)
from rag.generator import GroundedGenerator
from rag.service import CourseRAGService


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class TaskCancelled(RuntimeError):
    pass


class SmartCourseApplication:
    def __init__(self, settings: Settings, pipeline_runner=None):
        self.settings = settings
        self.settings.data_root.mkdir(parents=True, exist_ok=True)
        self.settings.artifact_root.mkdir(parents=True, exist_ok=True)
        self.task_template_path = self.settings.data_root / "recovered-task.json"
        self.store = JsonStore(self.settings.data_root / "state.json", self.task_template_path)
        self.usage = UsageStore(self.settings.data_root)
        self.ip_locator = IpLocator(self.settings.data_root)
        self.admin = AdminConsole(self)
        self.account_security = AccountSecurity(self.settings.data_root / 'account-security.sqlite3')
        self.product_services = ProductServices(self)
        self.compute_control = ComputeControl(self)
        from .task_recovery import recover_exited_workers
        self.store.transact(recover_exited_workers)
        self.rag = CourseRAGService(
            Path(os.environ.get("SMARTCOURSE_RAG_ROOT", settings.artifact_root / "rag")),
            GroundedGenerator(
                settings.gateway_url,
                settings.gateway_model,
                settings.gateway_token,
            ),
        )
        self.pipeline_runner = pipeline_runner or FullPipelineRunner(
            settings,
            rag_service=self.rag,
        )
        from .course_studio import CourseStudio
        self.studio = CourseStudio(self)
        self._execution_lock = threading.RLock()
        self._executions: dict[str, threading.Thread] = {}
        self.task_queue = PersistentTaskQueue(
            self.store, self._execute, os.environ.get("SMARTCOURSE_TASK_WORKERS", "3")
        )
        self.task_queue.start()
        from .feedback_repair import recover_repairs
        recover_repairs(self)

    def task_template(self) -> dict[str, Any] | None:
        if not self.task_template_path.exists():
            return None
        return json.loads(self.task_template_path.read_text(encoding="utf-8"))

    def rag_for_user(self, user_id):
        return CourseRAGService(self.settings.data_root / "rag" / safe_artifact_name(user_id),
                                self.rag.generator)

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        data = self.store.snapshot()
        tasks = [with_queue_position(task, data) for task in data["tasks"].values()
                 if not task.get('inputs', {}).get('interruptionParent')]
        if status:
            tasks = [task for task in tasks if task.get("status") == status]
        return sorted(tasks, key=lambda task: task.get("updatedAt", ""), reverse=True)

    def get_task(self, task_id: str) -> dict[str, Any]:
        data = self.store.snapshot()
        task = data["tasks"].get(task_id)
        if not task:
            raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
        task['canResumeWithoutCompute'] = int(task.get('currentStage', 1)) >= 5 or (
            task.get('currentStage') == 4 and self.cached_avatar_stage_ready(task))
        return with_queue_position(task, data)

    def add_task(self, payload: dict[str, Any], user_id: str | None, validated_assets=None) -> dict[str, Any]:
        task = create_task(payload)
        task['inputs']['courseProfile'] = normalize_profile(task.get('inputs', {}).get('courseProfile'))
        task['voiceId'] = payload.get('voiceId', 'default')
        from .course_presets import bind_course_presets
        bind_course_presets(task, payload, self.settings, overrides=validated_assets)
        task["createdBy"] = user_id

        def operation(data):
            saved_policy = data.get("translationPolicies", {}).get(user_id, data.get("translationPolicy"))
            task["translationPolicy"] = validate_policy(payload.get("translationPolicy", saved_policy))
            from .teaching_memory import task_memory
            task['teachingMemory'] = task_memory(data, user_id)
            self.studio.prepare_task(task, payload, user_id, data)
            from .narration_style import STYLE_VERSION
            task['generationConfig'] = {'model':self.settings.gateway_model,'narrationStyleVersion':STYLE_VERSION,
                                         'translationVersion':'direct-teaching-v3'}
            data["tasks"][task["id"]] = task
            return task

        result = self.store.transact(operation)
        if bool(payload.get("autoExecute", self.settings.auto_execute)):
            self.execute_task(result["id"], asynchronous=True)
            return self.get_task(result["id"])
        return result

    def mutate_task(self, task_id: str, operation):
        def transaction(data):
            task = data["tasks"].get(task_id)
            if not task:
                raise ApiError(HTTPStatus.NOT_FOUND, "任务不存在")
            return operation(task, data)

        return self.store.transact(transaction)

    def _progress_callback(self, task_id: str):
        def update(stage_index: int, status: str, progress: int, detail: dict[str, Any]):
            now = utc_now()

            def operation(task, _data):
                if task.get("status") == "cancelled":
                    raise TaskCancelled("任务已取消")
                stages = task.setdefault("stages", [])
                stage = next(
                    (item for item in stages if int(item.get("index", 0)) == stage_index),
                    None,
                )
                if stage is None:
                    raise ApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "任务阶段数据不完整")
                if status == 'queued' and not stage.get('queuedAtEpoch'):
                    stage['queuedAtEpoch'] = time.time()
                if status in {'running','completed','failed'} and stage.get('queuedAtEpoch'):
                    stage['queueWaitSeconds'] = round(stage.get('queueWaitSeconds', 0) + max(0, time.time()-stage.pop('queuedAtEpoch')), 3)
                if status == "running" and not stage.get("startedAt"):
                    stage["startedAt"] = now
                    stage["startedAtEpoch"] = time.time()
                stage["status"] = status
                stage["progress"] = max(0, min(100, int(progress)))
                stage.pop("error", None)
                stage["detail"] = copy.deepcopy(detail)
                started = float(stage.get("startedAtEpoch", time.time()))
                elapsed = max(0, time.time() - started)
                stage["elapsedSeconds"] = round(elapsed, 1)
                if 0 < stage["progress"] < 100:
                    stage["etaSeconds"] = round(
                        elapsed * (100 - stage["progress"]) / stage["progress"], 1
                    )
                else:
                    stage["etaSeconds"] = 0
                if status == "completed":
                    stage["completedAt"] = now
                    task.setdefault("outputs", {})[stage["key"]] = copy.deepcopy(detail)
                    for following in stages:
                        if following["index"] == stage_index + 1:
                            following["status"] = "waiting"
                            following["progress"] = 0
                task["currentStage"] = min(5, stage_index + (status == "completed"))
                task["overallProgress"] = round(
                    sum(int(item.get("progress", 0)) for item in stages) / 5, 1
                )
                task["status"] = "completed" if task["overallProgress"] == 100 else "processing"
                if status == "queued":
                    task["queue"] = {"state": "waiting_resource", "message": detail.get("step"),
                                     "resource": detail.get("resource")}
                else:
                    task["queue"] = {"state": "running"}
                task["updatedAt"] = now
                return task

            self.mutate_task(task_id, operation)

        return update

    def _execute(self, task_id: str, start_stage: int) -> None:
        with self._execution_lock:
            self._executions[task_id] = threading.current_thread()
        try:
            progress = self._progress_callback(task_id)
            progress(start_stage, "running", 0, {})
            task = self.get_task(task_id)
            result = self.pipeline_runner.run(
                task_id,
                task,
                progress,
                start_stage=start_stage,
            )

            def complete(task_value, _data):
                if task_value.get("status") == "cancelled":
                    return task_value
                task_value["status"] = "completed"
                task_value.pop("error", None)
                task_value["currentStage"] = 5
                task_value["overallProgress"] = 100
                task_value.setdefault("outputs", {})["result"] = result
                task_value["updatedAt"] = utc_now()
                return task_value

            self.mutate_task(task_id, complete)
        except TaskCancelled:
            return
        except StageReviewRequired as exc:
            def await_review(value,_data):
                value.update(status='waiting_review',currentStage=3,updatedAt=utc_now())
                value.pop('error',None)
                value['stages'][2].update(status='waiting_review',message=str(exc))
                return value
            self.mutate_task(task_id,await_review)
        except StageInputRequired as exc:
            required_stage, required_asset, message = exc.stage, exc.asset, str(exc)
            def await_input(task_value, _data):
                if task_value.get("status") == "cancelled":
                    return task_value
                task_value.update(status="waiting_input", currentStage=required_stage,
                                  requiredAsset=required_asset, updatedAt=utc_now())
                task_value.pop("error", None)
                for stage in task_value.get("stages", []):
                    if stage["index"] == required_stage:
                        stage.update(status="waiting_input", progress=0, message=message)
                return task_value
            self.mutate_task(task_id, await_input)
        except Exception as exc:
            import logging
            from .task_errors import task_error_message
            logging.exception('Course task failed: %s', task_id)
            public_message = task_error_message(exc)
            def fail(task_value, _data):
                if task_value.get("status") == "cancelled":
                    return task_value
                task_value["status"] = "failed"
                task_value["error"] = {
                    "message": public_message,
                    "stage": task_value.get("currentStage", start_stage),
                    "time": utc_now(),
                }
                for stage in task_value.get("stages", []):
                    if stage.get("status") == "running" or stage.get("index") == task_value.get("currentStage", start_stage):
                        stage["status"] = "failed"
                        stage["error"] = public_message
                task_value["updatedAt"] = utc_now()
                return task_value

            try:
                self.mutate_task(task_id, fail)
            except ApiError as mutation_error:
                if mutation_error.status != HTTPStatus.NOT_FOUND:
                    raise
        finally:
            with self._execution_lock:
                self._executions.pop(task_id, None)

    def cached_avatar_stage_ready(self, task):
        if (task.get('inputs', {}).get('avatarEngine') or os.environ.get('SMARTCOURSE_AVATAR_ENGINE')) != 'flashhead':
            return False
        try:
            reference = (task.get('assets', {}).get('referenceImage') or {})['path']
            if not reference.startswith('/artifacts/'):
                return False
            photo = (self.settings.artifact_root/reference.removeprefix('/artifacts/')).resolve()
            if not photo.is_relative_to(self.settings.artifact_root.resolve()):
                return False
            runtime = (self.settings.workspace_root or self.settings.artifact_root/'tasks')/task['id']/'runtime'
            from agents.flashhead_agent import FlashHeadAvatarAgent
            from .config import SUPPORTED_LANGUAGES
            agent = FlashHeadAvatarAgent(runtime, photo)
            languages = task.get('outputs', {}).get('s3', {}).get('languages', {})
            for language in task['targetLanguages']:
                code = next(k for k, v in SUPPORTED_LANGUAGES.items() if language in {k, v})
                path = languages[code]['timeline']
                timeline = self.settings.artifact_root/path.removeprefix('/artifacts/')
                if not agent.cache_ready(code, timeline):
                    return False
            return bool(task['targetLanguages'])
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            return False

    def execute_task(
        self, task_id: str, start_stage: int = 1, asynchronous: bool = True
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        from .remote_media import media_service_status
        media_status = media_service_status()
        require_owned = bool(os.environ.get('SMARTCOURSE_COMPUTE_OWNER'))
        cached_only = start_stage == 4 and self.cached_avatar_stage_ready(task)
        if start_stage < 5 and not cached_only and (media_status == "INACTIVE" or (require_owned and media_status != 'RUNNING')):
            raise ApiError(HTTPStatus.CONFLICT, "本项目计算服务当前已暂停，历史课程仍可播放。启动服务后可继续执行。")
        if start_stage not in range(1, 6):
            raise ApiError(HTTPStatus.BAD_REQUEST, "阶段编号必须为 1 至 5")
        if any(not task.get("outputs", {}).get("s"+str(index)) for index in range(1, start_stage)):
            raise ApiError(HTTPStatus.CONFLICT, "前置阶段尚未完成")
        preferences = self.store.snapshot().get('userPreferences', {}).get(task.get('createdBy'), {})
        if start_stage < 5 and not cached_only and 'maxTaskBudgetCny' in preferences:
            inputs = task.get('inputs') or {}
            estimate = self.product_services.estimate({'durationMinutes': inputs.get('durationMinutes', 2),
                'totalPages': inputs.get('totalPages', 2), 'targetLanguages': task.get('targetLanguages')})
            if estimate['estimatedComputeCny'][1] > preferences['maxTaskBudgetCny']:
                raise ApiError(HTTPStatus.CONFLICT, '估计费用超过单任务预算，请减少时长、语言或调整预算。')
        with self._execution_lock:
            active = self._executions.get(task_id)
            if active and active.is_alive():
                raise ApiError(HTTPStatus.CONFLICT, "任务正在执行")
            try:
                self.task_queue.submit(task_id, start_stage)
            except TaskAlreadyQueued as exc:
                raise ApiError(HTTPStatus.CONFLICT, str(exc)) from exc
        if asynchronous:
            return {"accepted": True, "taskId": task_id, "startStage": start_stage,
                    "queue": self.get_task(task_id).get("queue")}
        self.task_queue.wait(task_id)
        return self.get_task(task_id)


def make_handler(application: SmartCourseApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SmartCourse/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))

        def _cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

        def _json(self, status: int, payload: Any, extra_headers=None) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            limit_mb = 380 if urlparse(self.path).path == "/v1/uploads" else 30
            if length < 0 or length > limit_mb * 1024 * 1024:
                raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"请求内容超过 {limit_mb} MB 或长度无效")
            if not length:
                return {}
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ApiError(HTTPStatus.BAD_REQUEST, "请求 JSON 格式不正确") from exc
            if not isinstance(value, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "请求体必须为 JSON 对象")
            return value

        def _token(self) -> str:
            authorization = self.headers.get("Authorization", "")
            if authorization.lower().startswith("bearer "):
                return authorization[7:].strip()
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            return cookies["smartcourse-session"].value if "smartcourse-session" in cookies else ""

        def _user_id(self, required: bool = False) -> str | None:
            user = application.store.user_for_token(self._token())
            if required and not user:
                raise ApiError(HTTPStatus.UNAUTHORIZED, "登录已失效，请重新登录" if self._token() else "请先登录")
            return user["id"] if user else None

        def _task_owner(self, task_id, permission=None):
            user_id = self._user_id(required=True)
            task = application.get_task(task_id)
            from .course_access import require_course, visible_task
            if permission is None:
                permission = 'read' if self.command in {'GET','HEAD'} else 'manage' if self.command == 'DELETE' else 'edit'
                if permission == 'read' and any(part in self.path for part in ('/teacher/questions','/question-stats','/patch-plans','/blueprints')):
                    permission = 'review'
            require_course(task, user_id, permission)
            if user_id in task.get('teacherDemoUsers',[]) and task.get('demoTitle'):
                task={**task,'name':task['demoTitle']}
            return visible_task(task,user_id) if permission == 'read' else task

        def _guard_task_route(self, path):
            match = re.match(r"/v1/tasks/([^/]+)(?:/|$)", path)
            if match:
                self._task_owner(match.group(1))

        def _session_cookie(self, token):
            return {"Set-Cookie": "smartcourse-session="+token+"; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"}

        def _client_identity(self):
            return client_ip(self.client_address[0], self.headers)

        def _network_info(self):
            return application.ip_locator.describe(self._client_identity())

        def _agreement_user(self):
            self._user_id(required=True)
            user = application.store.user_for_token(self._token())
            if not accepted_policy(user):
                raise ApiError(HTTPStatus.FORBIDDEN, '请先阅读并同意用户协议和隐私说明。')
            return user['id']

        def _authorize_account(self, payload, registering):
            account = payload.get('account', payload.get('phone',''))
            password = payload.get('password','')
            if not isinstance(account,str) or not isinstance(password,str):
                raise ValueError('账号和密码必须为文本')
            consent = validate_policy_consent(payload)
            identity = self._client_identity()+'|'+account.strip()[:128]
            application.account_security.check_attempts(identity)
            try:
                application.account_security.consume(payload.get('captchaId'),payload.get('captchaCode'))
                if registering:
                    name, institution = payload.get('name',''), payload.get('institution','')
                    if not isinstance(name,str) or not isinstance(institution,str):
                        raise ValueError('姓名和单位必须为文本')
                    if payload.get('confirmPassword',password) != password:
                        raise ValueError('两次输入的密码不一致')
                    verified_email = None
                    if application.product_services.email.enabled:
                        verified_email = application.product_services.email.consume(payload.get('email'), 'register', payload.get('emailCode'))
                        if any(u.get('email') == verified_email for u in application.store.snapshot()['users'].values()):
                            raise ValueError('该邮箱已绑定其他账号。')
                    result = application.store.register(account,password,name,institution,policy_consent=consent,verified_email=verified_email)
                else:
                    result = application.store.login(account,password,policy_consent=consent)
            except ValueError:
                application.account_security.failed(identity)
                raise
            application.account_security.succeeded(identity)
            application.usage.record(result['user']['id'], 'register' if registering else 'login', network=self._network_info())
            def update_activity(data):
                user = data['users'][result['user']['phone']]
                user['lastLoginAt'] = utc_now()
                user['loginCount'] = int(user.get('loginCount', 0)) + 1
            application.store.transact(update_activity)
            return result

        def _uploaded_asset(self, value, kind):
            user_id = self._user_id(required=True)
            if not isinstance(value, dict) or not isinstance(value.get("path"), str):
                raise ApiError(HTTPStatus.BAD_REQUEST, "请先上传有效素材")
            path = value["path"]
            prefix = "/artifacts/uploads/"+kind+"/"
            if not path.startswith(prefix):
                raise ApiError(HTTPStatus.BAD_REQUEST, "素材来源无效，请重新上传")
            identifier = path[len(prefix):].split("/")[0]
            asset = application.store.snapshot().get("uploads", {}).get(identifier)
            if not asset or asset.get("createdBy") != user_id or asset.get("path") != path:
                raise ApiError(HTTPStatus.FORBIDDEN, "无权绑定此素材")
            if kind in {'image','audio'} and not asset.get('consent',{}).get('authorized'):
                raise ApiError(HTTPStatus.FORBIDDEN, '该素材尚未确认授权，请确认后重新上传。')
            return {key: asset[key] for key in ["id", "name", "size", "path",'consent'] if key in asset}

        def _copy_task_asset(self, task_id, role, asset):
            artifact_root = application.settings.artifact_root.resolve()
            source = (artifact_root / asset["path"].removeprefix("/artifacts/")).resolve()
            if artifact_root not in source.parents or not source.is_file():
                raise ApiError(HTTPStatus.BAD_REQUEST, "素材文件不存在")
            directory = artifact_root / "tasks" / task_id / "references"
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / (role + source.suffix.lower())
            descriptor, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=directory)
            temporary = Path(temporary_name)
            try:
                with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
                    shutil.copyfileobj(reader, writer)
                    writer.flush()
                    os.fsync(writer.fileno())
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
            public_path = "/artifacts/" + str(destination.relative_to(artifact_root))
            return {**asset, "path": public_path, "url": public_path}

        def _serve_file(self, path: Path, *, head_only: bool = False) -> None:
            if not path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "文件不存在")
            size = path.stat().st_size
            start = 0
            end = size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range", "").strip()
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                if not match or (not match.group(1) and not match.group(2)):
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self._cors_headers()
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else size - 1
                else:
                    suffix = int(match.group(2))
                    start = max(0, size - suffix)
                if start >= size or start > end:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self._cors_headers()
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(status)
            self._cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
            self.end_headers()
            if head_only:
                return
            with path.open("rb") as source:
                source.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _serve_artifact(self, relative: str, *, head_only: bool = False) -> None:
            root = application.settings.artifact_root.resolve()
            path = (root / unquote(relative)).resolve()
            if root != path and root not in path.parents:
                raise ApiError(HTTPStatus.FORBIDDEN, "文件路径无效")
            user_id = self._user_id(required=True)
            parts = path.relative_to(root).parts
            if len(parts) > 1 and parts[0] == "tasks":
                from .course_access import course_role, require_course, published_artifacts, personal_remediation_artifacts
                task = application.get_task(parts[1])
                role = require_course(task,user_id)
                if role not in {'owner','editor'}:
                    public_url = '/artifacts/'+str(path.relative_to(root))
                    image_folder = '/artifacts/tasks/'+task['id']+'/s1/source-slide-images/'
                    own_quiz_media=public_url in personal_remediation_artifacts(task,user_id,application.store.snapshot())
                    if public_url not in published_artifacts(task) and not own_quiz_media and not (role in {'reviewer','learner'} and public_url.startswith(image_folder) and path.suffix == '.png'):
                        raise ApiError(HTTPStatus.FORBIDDEN,'此文件不属于共享课程的可读结果。')
            elif len(parts) > 2 and parts[0] == "uploads":
                asset = application.store.snapshot().get("uploads", {}).get(parts[2])
                if not asset or asset.get("createdBy") != user_id:
                    raise ApiError(HTTPStatus.FORBIDDEN, "无权访问此素材")
            if not path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "文件不存在")
            self._serve_file(path, head_only=head_only)

        def _serve_course(self, relative: str, *, head_only: bool = False) -> None:
            product_root = Path(
                os.environ.get(
                    "SMARTCOURSE_AI_INTRO_ROOT",
                    application.settings.artifact_root / "ai-intro",
                )
            ).resolve()
            root = Path(
                os.environ.get("SMARTCOURSE_AI_INTRO_SITE_ROOT", product_root / "site")
            ).resolve()
            requested = unquote(relative).strip("/") or "index.html"
            path = (root / requested).resolve()
            if root != path and root not in path.parents:
                raise ApiError(HTTPStatus.FORBIDDEN, "课程文件路径无效")
            if not path.is_file():
                raise ApiError(HTTPStatus.NOT_FOUND, "课程文件不存在")
            self._serve_file(path, head_only=head_only)

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors_headers()
            self.end_headers()

        def do_HEAD(self) -> None:
            try:
                path = urlparse(self.path).path.rstrip("/") or "/"
                if path == "/":
                    self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                    self.send_header("Location", "/course/")
                    self.end_headers()
                    return
                if path == "/course":
                    self._serve_course("index.html", head_only=True)
                    return
                if path.startswith("/course/"):
                    self._serve_course(path.removeprefix("/course/"), head_only=True)
                    return
                if path.startswith("/artifacts/"):
                    self._serve_artifact(path.removeprefix("/artifacts/"), head_only=True)
                    return
                raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
            except (BrokenPipeError, ConnectionResetError):
                return
            except (ApiError, AuthSecurityError) as exc:
                self._json(exc.status, {"message": str(exc)})

        def do_GET(self) -> None:
            try:
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                query = parse_qs(parsed.query)
                if application.studio.get(self,path,query):
                    return
                if application.admin.get(self, path, query):
                    return
                if path == '/v1/course-profile/options':
                    self._user_id(required=True)
                    self._json(HTTPStatus.OK, {'domains':DOMAINS, 'audiences':AUDIENCES})
                    return
                if path == '/v1/settings/teaching-memory':
                    from .teaching_memory import read_memory
                    self._json(HTTPStatus.OK, read_memory(application.store, self._user_id(required=True)))
                    return
                match = re.fullmatch(r'/v1/tasks/([^/]+)/execution-journal', path)
                if match:
                    from .execution_journal import read_journal
                    task = self._task_owner(match.group(1), 'edit')
                    root = application.settings.workspace_root or application.settings.artifact_root / 'tasks'
                    journal = read_journal(root / safe_artifact_name(task['id']) / 'execution-journal.json')
                    self._json(HTTPStatus.OK, {'journal': journal, 'teachingMemory': task.get('teachingMemory')})
                    return
                if application.compute_control.get(self, path) or application.product_services.get(self, path):
                    return
                if path == '/v1/feedback':
                    user_id = self._user_id(required=True)
                    task_id = query.get('taskId', [None])[0]
                    if task_id:
                        self._task_owner(task_id)
                    self._json(HTTPStatus.OK, list_feedback(application.store, user_id, task_id))
                    return
                if path == '/v1/auth/policies':
                    self._json(HTTPStatus.OK, policy_documents())
                    return
                if path == '/v1/auth/captcha':
                    self._json(HTTPStatus.OK, application.account_security.issue(self._client_identity()))
                    return
                if path == "/":
                    self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                    self.send_header("Location", "/course/")
                    self.end_headers()
                    return
                if path == "/course":
                    self._serve_course("index.html")
                    return
                if path.startswith("/course/"):
                    self._serve_course(path.removeprefix("/course/"))
                    return
                match = re.fullmatch(r"/v1/courses/([^/]+)/blueprints", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    data=_read(application.settings)
                    self._json(HTTPStatus.OK, [x for x in data.get("blueprints", {}).values() if x.get("course_id")==course_id]); return
                match = re.fullmatch(r"/v1/blueprints/([^/]+)/unit-build", path)
                if match:
                    blueprint_id=unquote(match.group(1))
                    blueprint=_read(application.settings).get('blueprints',{}).get(blueprint_id)
                    if not blueprint:raise ApiError(HTTPStatus.NOT_FOUND,'蓝图不存在')
                    self._task_owner(blueprint['course_id'])
                    record=get_unit_build(application.settings,blueprint_id)
                    if not record:raise ApiError(HTTPStatus.NOT_FOUND,'微课单元生成任务不存在')
                    record=copy.deepcopy(record)
                    if record.get('result'):
                        artifact_root=application.settings.artifact_root.resolve()
                        for unit in record['result'].get('units',[]):
                            for key in ('video','pdf','subtitles','sourceEditablePptx'):
                                source=Path(unit[key]).resolve()
                                if artifact_root in source.parents:
                                    unit[key]='/artifacts/'+str(source.relative_to(artifact_root))
                    self._json(HTTPStatus.OK,record); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/teacher/questions", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    data=_read(application.settings)
                    self._json(HTTPStatus.OK, [x for x in data.get("questions", {}).values() if x.get("course_id")==course_id]); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/patch-plans", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    data=_read(application.settings)
                    self._json(HTTPStatus.OK, [x for x in data.get("patchPlans", {}).values() if x.get("course_id")==course_id]); return
                match = re.fullmatch(r"/v1/patch-plans/([^/]+)/release", path)
                if match:
                    record=_read(application.settings).get('patchPlans',{}).get(unquote(match.group(1)))
                    if not record:raise ApiError(HTTPStatus.NOT_FOUND,'局部修订方案不存在')
                    self._task_owner(record['course_id'])
                    release=application.get_task(record['releaseTaskId']) if record.get('releaseTaskId') else None
                    self._json(HTTPStatus.OK, {'patchPlanId':record['patch_plan_id'],
                                               'releaseTaskId':record.get('releaseTaskId'),
                                               'status':release['status'] if release else record.get('releaseStatus'),
                                               'error':release.get('error') if release else record.get('releaseError')}); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/questions", path)
                if match:
                    course_id=unquote(match.group(1)); self._user_id(required=True)
                    data=_read(application.settings)
                    self._json(HTTPStatus.OK, [public_question(x) for x in data.get("questions", {}).values()
                                               if x.get("course_id")==course_id and x.get("status")=="APPROVED"]); return
                match = re.fullmatch(r"/v1/questions/([^/]+)/remediation/([^/]+)", path)
                if match:
                    user=self._user_id(required=True)
                    try:
                        result=get_quiz_remediation(application,unquote(match.group(1)),unquote(match.group(2)),user)
                    except KeyError as exc:raise ApiError(HTTPStatus.NOT_FOUND,str(exc)) from exc
                    except PermissionError as exc:raise ApiError(HTTPStatus.FORBIDDEN,str(exc)) from exc
                    self._json(HTTPStatus.OK,result); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/question-stats", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    self._json(HTTPStatus.OK, question_stats(application.settings,course_id)); return
                if path == "/v1/health":
                    from .remote_media import media_service_status
                    self._json(
                        HTTPStatus.OK,
                        {
                            "status": "ok",
                            "service": "smartcourse",
                            "version": "1.0.0",
                            "stages": ["S1", "S2", "S3", "S4", "S5"],
                            "creationModes": ["upload", "topic", "code"],
                            "execution": "full-pipeline",
                            "pedagogicalIr": "2026.1",
                            "coursewareSystem": "2026.2",
                            "coursewareResearchDirections": [
                                item["id"] for item in RESEARCH_DIRECTIONS
                            ],
                            "pedagogicalExperiments": [
                                "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"
                            ],
                            "autoExecute": application.settings.auto_execute,
                            "taskQueue": {"workers": application.task_queue.workers, "maxWorkers": 5,
                                          "stageLimits": application.task_queue.resources.stage_limits},
                            "mediaService": media_service_status(),
                        },
                    )
                    return
                if path == "/v1/settings/translation":
                    user_id = self._user_id(required=True)
                    state = application.store.snapshot()
                    self._json(HTTPStatus.OK, validate_policy(state.get("translationPolicies", {}).get(user_id, state.get("translationPolicy"))))
                    return
                if path == "/v1/s1/research":
                    self._json(
                        HTTPStatus.OK,
                        {
                            "schemaVersion": "2026.2",
                            "directions": RESEARCH_DIRECTIONS,
                            "agentRoles": AGENT_ROLES,
                            "outputs": [
                                "course_brief.json",
                                "course_structure.json",
                                "course_quality_report.json",
                                "visual_quality_report.json",
                                "learning_evaluation.json",
                                "research_coverage.json",
                                "pedagogical_ir.json",
                            ],
                        },
                    )
                    return
                if path == "/v1/code-lessons":
                    self._json(HTTPStatus.OK, list_lesson_specs())
                    return
                if path == "/v1/avatar-engines":
                    bundle_root = os.environ.get(
                        "SMARTCOURSE_LONGCAT_BUNDLE_ROOT",
                        "/lpai/volumes/ad-base-vla-vol-ga/mayongjia/ad-base-vla-vol-ga/group/fh/code/aaai27-benchmark-baselines/fh/aaai27-benchmark-baselines/LongCat-Video-Avatar",
                    )
                    environment_python = os.environ.get(
                        "SMARTCOURSE_LONGCAT_ENV_PYTHON",
                        "/lpai/volumes/ad-base-vla-vol-ga/mayongjia/ad-base-vla-vol-ga/group/fh/envs/longcat-avatar15-xtuners/bin/python",
                    )
                    self._json(
                        HTTPStatus.OK,
                        {
                            "default": "float",
                            "engines": [
                                {"engine": "float", "ready": True, "mode": "face_avatar"},
                                longcat_engine_readiness(bundle_root, environment_python),
                            ],
                        },
                    )
                    return
                if path == "/v1/demo-course":
                    runtime_root = application.settings.artifact_root.resolve().parent
                    self._json(
                        HTTPStatus.OK,
                        build_demo_course_manifest(runtime_root),
                    )
                    return
                if path == "/v1/demo-interruptions":
                    self._json(HTTPStatus.OK, list_interruptions())
                    return
                if path == "/v1/ai-intro":
                    product_root = Path(
                        os.environ.get(
                            "SMARTCOURSE_AI_INTRO_ROOT",
                            application.settings.artifact_root / "ai-intro",
                        )
                    )
                    self._json(HTTPStatus.OK, ai_intro_status(product_root))
                    return
                if path == "/v1/rag/status":
                    self._json(HTTPStatus.OK, application.rag_for_user(self._user_id(required=True)).status())
                    return
                if path == "/v1/experiments":
                    self._json(
                        HTTPStatus.OK,
                        sorted(
                            [
                                *EXPERIMENT_CATALOG,
                                *ADAPTIVE_EXPERIMENT_CATALOG,
                                *ADVANCED_EXPERIMENT_CATALOG,
                            ],
                            key=lambda item: int(item["experimentId"][1:]),
                        ),
                    )
                    return
                match = re.fullmatch(r"/v1/pedagogical-ir/([^/]+)", path)
                if match:
                    condition = str(query.get("condition", ["A4"])[0])
                    ir, report = compile_lesson_ir(
                        get_lesson_spec(match.group(1)),
                        condition=condition,
                    )
                    self._json(
                        HTTPStatus.OK,
                        {"pedagogicalIr": ir, "constraintReport": report},
                    )
                    return
                if path == '/api/voices':
                    from .course_presets import available_voice_presets
                    self._json(HTTPStatus.OK, available_voice_presets(application.settings))
                    return
                if path == "/v1/tasks":
                    status = query.get("status", [None])[0]
                    user_id = self._user_id(required=True)
                    visible=[task for task in application.list_tasks(status)
                             if task.get("createdBy") == user_id or user_id in task.get('teacherDemoUsers',[])]
                    self._json(HTTPStatus.OK, [{**task,'name':task.get('demoTitle',task['name'])}
                                               if user_id in task.get('teacherDemoUsers',[]) else task
                                               for task in visible])
                    return
                match = re.fullmatch(r"/api/courses/([^/]+)/interruptions(?:/([^/]+))?", path)
                if match:
                    task = self._task_owner(match.group(1))
                    records = application.store.snapshot().get('interruptions', {})
                    from .interruption_jobs import public_interruption
                    if match.group(2):
                        record = records.get(match.group(2))
                        if not record or record.get('courseId') != task['id']:
                            raise ApiError(HTTPStatus.NOT_FOUND, '打断记录不存在')
                        self._json(HTTPStatus.OK, public_interruption(record))
                    else:
                        self._json(HTTPStatus.OK, [public_interruption(record) for record in records.values()
                                                  if record.get('courseId') == task['id']])
                    return
                match = re.fullmatch(r"/api/courses/([^/]+)", path)
                if match:
                    from .course_api import course_status
                    self._json(HTTPStatus.OK, course_status(self._task_owner(match.group(1))))
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)", path)
                if match:
                    self._json(HTTPStatus.OK, self._task_owner(match.group(1)))
                    return
                if path == "/v1/recovered-artifacts":
                    manifest = application.settings.data_root / "recovered-artifacts.json"
                    if not manifest.exists():
                        raise ApiError(HTTPStatus.NOT_FOUND, "恢复产物清单尚未生成")
                    self._json(HTTPStatus.OK, json.loads(manifest.read_text(encoding="utf-8")))
                    return
                if path.startswith("/artifacts/"):
                    self._serve_artifact(path.removeprefix("/artifacts/"))
                    return
                raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
            except (BrokenPipeError, ConnectionResetError):
                return
            except (ApiError, AuthSecurityError) as exc:
                self._json(exc.status, {"message": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": str(exc)})

        def do_POST(self) -> None:
            try:
                path = urlparse(self.path).path.rstrip("/") or "/"
                payload = self._body()
                if application.studio.post(self,path,payload):
                    return
                if application.compute_control.post(self, path, payload) or application.product_services.post(self, path, payload):
                    return
                self._guard_task_route(path)
                if path == '/v1/settings/teaching-memory':
                    from .teaching_memory import save_memory
                    owner = self._user_id(required=True)
                    self._json(HTTPStatus.OK, save_memory(application.store, owner, payload))
                    return
                if path == '/v1/visits':
                    page = payload.get('page', '')
                    if not isinstance(page, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', page):
                        raise ValueError('页面名称无效')
                    self._json(HTTPStatus.CREATED, application.usage.record(self._user_id() or '', 'page_view', {'page':page}, payload.get('eventId'), network=self._network_info()))
                    return
                if path == '/v1/usage':
                    user_id = self._user_id(required=True)
                    kind = payload.get('kind')
                    if kind not in {'page_view','result_play','result_download','example_selected'}:
                        raise ValueError('使用记录类型无效')
                    task_id = payload.get('taskId')
                    if task_id is not None:
                        if not isinstance(task_id, str): raise ValueError('课程编号无效')
                        self._task_owner(task_id)
                    if kind in {'result_play','result_download'} and not task_id:
                        raise ValueError('播放和下载记录需要关联课程')
                    detail = {key:payload[key] for key in ('page','language','exampleId','exampleKind','fileType') if key in payload}
                    if any(not isinstance(value,str) or len(value)>120 for value in detail.values()):
                        raise ValueError('使用记录参数无效')
                    self._json(HTTPStatus.CREATED, application.usage.record(user_id, kind, detail, payload.get('eventId'), task_id, network=self._network_info()))
                    return
                if path == '/v1/feedback':
                    user_id = self._user_id(required=True)
                    task_id = payload.get('taskId')
                    if task_id is not None and (not isinstance(task_id, str) or not re.fullmatch(r'task_[a-f0-9]{12}', task_id)):
                        raise ValueError('关联课程编号无效')
                    task = self._task_owner(task_id, 'read') if task_id else None
                    self._json(HTTPStatus.CREATED, submit_feedback(application.store, user_id, payload, task))
                    return
                match = re.fullmatch(r"/v1/courses/([^/]+)/blueprints", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    user=self._user_id(required=True); result=draft_blueprint(application.settings,course_id,payload,user); self._json(HTTPStatus.CREATED,result); return
                match = re.fullmatch(r"/v1/blueprints/([^/]+)/approve", path)
                if match:
                    record=_read(application.settings).get('blueprints',{}).get(unquote(match.group(1)))
                    if not record: raise ApiError(HTTPStatus.NOT_FOUND,'蓝图不存在')
                    self._task_owner(record['course_id'])
                    user=self._user_id(required=True); result=approve_blueprint(application.settings,unquote(match.group(1)),user,payload.get("expected_revision")); self._json(HTTPStatus.OK,result); return
                match = re.fullmatch(r"/v1/blueprints/([^/]+)/unit-build", path)
                if match:
                    blueprint_id=unquote(match.group(1))
                    blueprint=_read(application.settings).get('blueprints',{}).get(blueprint_id)
                    if not blueprint:raise ApiError(HTTPStatus.NOT_FOUND,'蓝图不存在')
                    self._task_owner(blueprint['course_id'])
                    user=self._user_id(required=True)
                    record,created,approved=reserve_unit_build(application.settings,blueprint_id,user,bool(payload.get('force')))
                    if created:
                        def build_units():
                            try:
                                update_unit_build(application.settings,blueprint_id,record['build_id'],'RUNNING')
                                result=assemble_units(application.settings,approved)
                                update_unit_build(application.settings,blueprint_id,record['build_id'],'COMPLETED',result=result)
                            except Exception as exc:
                                update_unit_build(application.settings,blueprint_id,record['build_id'],'FAILED',error=str(exc))
                        threading.Thread(target=build_units,daemon=True,name='unit-build-'+record['build_id']).start()
                    self._json(HTTPStatus.ACCEPTED,record); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/patch-plans", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    user=self._user_id(required=True); result=make_patch_plan(application.settings,course_id,payload,user); self._json(HTTPStatus.CREATED,result); return
                match = re.fullmatch(r"/v1/patch-plans/([^/]+)/approve", path)
                if match:
                    record=_read(application.settings).get('patchPlans',{}).get(unquote(match.group(1)))
                    if not record: raise ApiError(HTTPStatus.NOT_FOUND,'PatchPlan 不存在')
                    self._task_owner(record['course_id'])
                    user=self._user_id(required=True); result=approve_patch_plan(application.settings,unquote(match.group(1)),user); self._json(HTTPStatus.OK,result); return
                match = re.fullmatch(r"/v1/patch-plans/([^/]+)/execute", path)
                if match:
                    plan_id=unquote(match.group(1))
                    record=_read(application.settings).get('patchPlans',{}).get(plan_id)
                    if not record:raise ApiError(HTTPStatus.NOT_FOUND,'局部修订方案不存在')
                    self._task_owner(record['course_id'])
                    execute=start_subtitle_release if all(item.get('kind')=='subtitle' for item in record.get('changes',[])) else start_script_release
                    result=execute(application,plan_id,self._user_id(required=True))
                    self._json(HTTPStatus.ACCEPTED,result); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/questions", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    user=self._user_id(required=True); result=create_question(application.settings,course_id,payload,user); self._json(HTTPStatus.CREATED,result); return
                match = re.fullmatch(r"/v1/courses/([^/]+)/questions/batch", path)
                if match:
                    course_id=unquote(match.group(1)); self._task_owner(course_id)
                    user=self._user_id(required=True)
                    resource=application.pipeline_runner.resources.STAGES['S2'][0]
                    with application.pipeline_runner.resources.acquire(resource):
                        result=generate_question_batch(application.settings,course_id,user,application.pipeline_runner.gateway,payload.get('count',5),payload.get('locale','zh-CN'))
                    self._json(HTTPStatus.CREATED,result); return
                match = re.fullmatch(r"/v1/questions/([^/]+)/review", path)
                if match:
                    record=_read(application.settings).get('questions',{}).get(unquote(match.group(1)))
                    if not record: raise ApiError(HTTPStatus.NOT_FOUND,'题目不存在')
                    self._task_owner(record['course_id'])
                    user=self._user_id(required=True); result=review_question(application.settings,unquote(match.group(1)),user,bool(payload.get("approved"))); self._json(HTTPStatus.OK,result); return
                match = re.fullmatch(r"/v1/questions/([^/]+)/attempt", path)
                if match:
                    user=self._user_id(required=True)
                    question_id=unquote(match.group(1))
                    question_record=_read(application.settings).get('questions',{}).get(question_id)
                    if not question_record:raise ApiError(HTTPStatus.NOT_FOUND,'题目不存在')
                    application.studio.task(question_record['course_id'],user)
                    result=attempt_question(application.settings,question_id,str(payload.get("option_id")),user,
                                            payload.get("clientEventId"))
                    if not result['correct']:
                        question=_read(application.settings).get('questions',{}).get(question_id)
                        try:result['remediation']=submit_quiz_remediation(application,question,str(payload.get('option_id')),user)
                        except Exception as exc:result['remediationError']=str(exc)
                    self._json(HTTPStatus.OK,result); return
                if path == "/v1/auth/register":
                    result = self._authorize_account(payload, True)
                    self._json(HTTPStatus.CREATED, result, self._session_cookie(result["accessToken"]))
                    return
                if path == "/v1/auth/login":
                    result = self._authorize_account(payload, False)
                    self._json(HTTPStatus.OK, result, self._session_cookie(result["accessToken"]))
                    return
                if path == "/v1/auth/session":
                    self._user_id(required=True)
                    user = application.store.user_for_token(self._token())
                    public = {key: user[key] for key in ["id", "displayName", "phone", "institution",'policyConsent'] if key in user}
                    self._json(HTTPStatus.OK, {"user": public,'agreementRequired':not accepted_policy(user)}, self._session_cookie(self._token()))
                    return
                if path == '/v1/auth/consent':
                    user_id = self._user_id(required=True)
                    public = application.store.accept_policy(user_id,validate_policy_consent(payload))
                    self._json(HTTPStatus.OK, {'user':public,'agreementRequired':False})
                    return
                if path == "/v1/auth/logout":
                    token = self._token()
                    application.store.transact(lambda data: data.get("tokens", {}).pop(token, None))
                    self._json(HTTPStatus.OK, {"loggedOut": True}, {"Set-Cookie": "smartcourse-session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"})
                    return
                match = re.fullmatch(r"/api/courses/([^/]+)/interruptions/([^/]+)/retry", path)
                if match:
                    from .interruption_jobs import retry_interruption
                    self._json(HTTPStatus.ACCEPTED, retry_interruption(application,
                               self._task_owner(match.group(1)), match.group(2)))
                    return
                match = re.fullmatch(r"/api/courses/([^/]+)/interruptions", path)
                if match:
                    task = self._task_owner(match.group(1))
                    from .interruption_jobs import submit_interruption
                    self._json(HTTPStatus.ACCEPTED, submit_interruption(application, task, payload))
                    return
                if path == '/api/courses':
                    user_id = self._agreement_user()
                    from .course_api import course_request, course_status
                    from .course_download import download_course_input
                    def resolve_asset(url, kind):
                        if isinstance(url, str) and url.startswith('/artifacts/'):
                            return self._uploaded_asset({'path': url}, kind)
                        consent = validate_media_consent(payload.get('mediaConsent'),user_id) if kind in {'image','audio'} else None
                        filename, content = download_course_input(url, kind)
                        uploaded = save_upload(application.settings.artifact_root, filename, kind, content)
                        if consent:
                            uploaded['consent'] = consent
                        application.store.transact(lambda data: data.setdefault('uploads', {}).update(
                            {uploaded['id']: {**uploaded, 'createdBy': user_id}}))
                        return uploaded
                    normalized_request, assets = course_request(payload, resolve_asset)
                    if normalized_request['mode'] == 'upload':
                        from .course_preflight import validate_course_files
                        normalized_request['inputs'].update(validate_course_files(
                            normalized_request['inputs'], application.settings.artifact_root))
                    task = application.add_task(normalized_request, user_id, validated_assets=assets)
                    self._json(HTTPStatus.ACCEPTED, course_status(task))
                    return
                if path == "/v1/tasks":
                    self._agreement_user()
                    if payload.get("mode") == "upload":
                        inputs = payload.get("inputs") or {}
                        inputs["ppt"] = self._uploaded_asset(inputs.get("ppt"), "ppt")
                        if inputs.get("script"):
                            inputs["script"] = self._uploaded_asset(inputs["script"], "script")
                        payload["inputs"] = inputs
                    task = application.add_task(payload, self._user_id(required=True))
                    self._json(HTTPStatus.CREATED, task)
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)/deliverables", path)
                if match:
                    task=self._task_owner(match.group(1))
                    from .delivery import package_completed_task
                    result=package_completed_task(task,application.settings.artifact_root)
                    def publish(value,_data):
                        value['outputs']['s5']=result
                        value['updatedAt']=utc_now()
                        return value
                    updated=application.mutate_task(task['id'],publish)
                    self._json(HTTPStatus.OK,updated)
                    return
                if path == "/v1/rag/query":
                    service = application.rag_for_user(self._user_id(required=True))
                    if service.index is None:
                        raise ApiError(HTTPStatus.CONFLICT, "请先导入课程参考课件")
                    try:
                        result = service.query(payload)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                    self._json(HTTPStatus.OK, result)
                    return
                if path == "/v1/rag/verify":
                    self._json(HTTPStatus.OK, application.rag_for_user(self._user_id(required=True)).verify(payload))
                    return
                if path == "/v1/rag/ingest":
                    user_id = self._user_id(required=True)
                    if payload.get("registry"):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "请上传当前账户的 PPTX 参考课件")
                    uploaded = payload.get("pptx")
                    if isinstance(uploaded, str):
                        uploaded = {"path": uploaded}
                    asset = self._uploaded_asset(uploaded, "ppt")
                    source = (application.settings.artifact_root / asset["path"].removeprefix("/artifacts/")).resolve()
                    if source.suffix.lower() != ".pptx":
                        raise ApiError(HTTPStatus.BAD_REQUEST, "知识库当前接收 PPTX 参考课件")
                    try:
                        result = application.rag_for_user(user_id).ingest({**payload, "pptx": str(source)})
                    except (ValueError, FileNotFoundError) as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                    self._json(HTTPStatus.CREATED, result)
                    return
                if path == "/v1/experiments/e2":
                    lesson_id = str(payload.get("lessonId", "")).strip()
                    if not lesson_id:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 lessonId")
                    learner_state = payload.get("learnerState")
                    ir, report = compile_lesson_ir(
                        get_lesson_spec(lesson_id),
                        condition="A4",
                        learner_state=learner_state,
                    )
                    self._json(
                        HTTPStatus.OK,
                        {
                            "baseConstraintReport": report,
                            "experiment": build_e2_variants(ir),
                        },
                    )
                    return
                if path == "/v1/experiments/run":
                    experiment_ids = payload.get("experimentIds") or [
                        "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"
                    ]
                    lesson_ids = payload.get("lessonIds") or [
                        "linear-function", "light-reflection", "ph-indicator"
                    ]
                    if not isinstance(experiment_ids, list) or not isinstance(lesson_ids, list):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "experimentIds 和 lessonIds 必须为数组")
                    runner = ExperimentRunner(
                        application.settings.artifact_root / "experiments"
                    )
                    result = runner.run(
                        [str(value) for value in experiment_ids],
                        [str(value) for value in lesson_ids],
                        int(payload.get("seed", 20260822)),
                    )
                    manifest_path = Path(result["manifest"]).resolve()
                    result["manifest"] = "/artifacts/" + str(
                        manifest_path.relative_to(application.settings.artifact_root.resolve())
                    )
                    self._json(HTTPStatus.CREATED, result)
                    return
                if path == "/v1/experiments/protocol":
                    experiment_id = str(payload.get("experimentId", "")).strip()
                    conditions = payload.get("conditions")
                    if not experiment_id or not isinstance(conditions, list):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 experimentId 或 conditions")
                    self._json(
                        HTTPStatus.OK,
                        build_experiment_protocol(
                            experiment_id,
                            [str(value) for value in conditions],
                            float(payload.get("effectSize", 0.5)),
                            float(payload.get("alpha", 0.05)),
                            float(payload.get("power", 0.8)),
                        ),
                    )
                    return
                if path == "/v1/experiments/analyze":
                    rows = payload.get("rows")
                    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "rows 必须为对象数组")
                    self._json(HTTPStatus.OK, analyze_learning_rows(rows))
                    return
                if path == "/v1/learner-state/update":
                    observation = payload.get("observation")
                    if not isinstance(observation, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 observation")
                    self._json(
                        HTTPStatus.OK,
                        update_learner_state(payload.get("learnerState"), observation),
                    )
                    return
                if path == "/v1/teaching-policy/select":
                    state = payload.get("learnerState")
                    if not isinstance(state, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 learnerState")
                    self._json(
                        HTTPStatus.OK,
                        select_teaching_policy(
                            state,
                            str(payload.get("condition", "E4")),
                        ),
                    )
                    return
                if path == "/v1/experiments/adaptive":
                    lesson_id = str(payload.get("lessonId", "")).strip()
                    if not lesson_id:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 lessonId")
                    ir, _report = compile_lesson_ir(
                        get_lesson_spec(lesson_id),
                        condition="A4",
                        learner_state=payload.get("learnerState"),
                    )
                    self._json(
                        HTTPStatus.OK,
                        build_adaptive_experiment(
                            ir,
                            payload.get("learnerState") or {},
                        ),
                    )
                    return
                if path == "/v1/proactive-intervention":
                    self._json(
                        HTTPStatus.OK,
                        select_proactive_intervention(
                            payload.get("learnerState") or {},
                            str(payload.get("condition", "D4")),
                            payload.get("context") or {},
                        ),
                    )
                    return
                if path == "/v1/memory/update":
                    evidence = payload.get("evidence")
                    if not isinstance(evidence, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 evidence")
                    self._json(
                        HTTPStatus.OK,
                        update_structured_memory(
                            payload.get("memory"),
                            evidence,
                            str(payload.get("condition", "F4")),
                        ),
                    )
                    return
                if path == "/v1/personalization/plan":
                    self._json(
                        HTTPStatus.OK,
                        build_personalization_plan(
                            payload.get("learnerState") or {},
                            payload.get("preferences") or {},
                            str(payload.get("condition", "G5")),
                        ),
                    )
                    return
                if path == "/v1/pedagogical-alignment/check":
                    self._json(
                        HTTPStatus.OK,
                        check_pedagogical_alignment(
                            payload.get("learnerState") or {},
                            payload.get("interaction") or {},
                            str(payload.get("condition", "H4")),
                        ),
                    )
                    return
                if path == "/v1/evaluator/prescreen":
                    self._json(
                        HTTPStatus.OK,
                        prescreen_candidate(
                            payload.get("constraintReport") or {},
                            payload.get("syncReport") or {},
                            str(payload.get("condition", "I0")),
                        ),
                    )
                    return
                if path == "/v1/teacher-profile/validate":
                    profile = build_teacher_profile(
                        str(payload.get("profileId", "teacher")),
                        payload.get("referenceImage"),
                        payload.get("referenceAudio"),
                        payload.get("gestureClips") or {},
                        payload.get("consent") or {},
                        payload.get("fullBodyEngine") or {},
                    )
                    profile["fileValidation"] = validate_profile_files(
                        profile,
                        application.settings.artifact_root,
                    )
                    self._json(HTTPStatus.OK, profile)
                    return
                if path == "/v1/gesture-schedule":
                    ir = payload.get("pedagogicalIr")
                    profile = payload.get("teacherProfile")
                    if not isinstance(ir, dict) or not isinstance(profile, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 pedagogicalIr 或 teacherProfile")
                    self._json(
                        HTTPStatus.OK,
                        schedule_gestures(
                            ir,
                            profile,
                            float(payload.get("minimumGapSeconds", 6.0)),
                        ),
                    )
                    return
                if path == "/v1/rehearsal/analyze":
                    structure = payload.get("courseStructure")
                    ir = payload.get("pedagogicalIr")
                    if not isinstance(structure, dict) or not isinstance(ir, dict):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 courseStructure 或 pedagogicalIr")
                    self._json(
                        HTTPStatus.OK,
                        analyze_rehearsal(
                            structure,
                            ir,
                            float(payload.get("maximumInteractionGapSeconds", 600)),
                        ),
                    )
                    return
                if path == "/v1/demo-course/prepare":
                    runtime_root = application.settings.artifact_root.resolve().parent
                    result = prepare_demo_package(
                        runtime_root,
                        application.settings.artifact_root / "demo" / "ai-literacy-general",
                    )
                    manifest = Path(result["manifest"]).resolve()
                    result["manifest"] = "/artifacts/" + str(
                        manifest.relative_to(application.settings.artifact_root.resolve())
                    )
                    self._json(HTTPStatus.CREATED, result)
                    return
                if path == "/v1/demo-interruptions/execute":
                    scenario_id = str(payload.get("scenarioId", "")).strip()
                    if not scenario_id:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 scenarioId")
                    try:
                        result = execute_fixed_interrupt(
                            scenario_id,
                            application.settings.artifact_root / "interactive-demo",
                        )
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                    artifact_root = application.settings.artifact_root.resolve()
                    for key, value in list(result.get("artifacts", {}).items()):
                        path_value = Path(value).resolve()
                        result["artifacts"][key] = "/artifacts/" + str(
                            path_value.relative_to(artifact_root)
                        )
                    presentation = result.get("branchPresentation", {})
                    presentation_path = Path(str(presentation.get("path", ""))).resolve()
                    if presentation.get("available") and presentation_path.is_file():
                        presentation["path"] = "/artifacts/" + str(
                            presentation_path.relative_to(artifact_root)
                        )
                    manifest_path = Path(result["manifest"]).resolve()
                    result["manifest"] = "/artifacts/" + str(
                        manifest_path.relative_to(artifact_root)
                    )
                    self._json(HTTPStatus.CREATED, result)
                    return
                if path == "/v1/ai-intro/interrupt":
                    interrupt_id = str(payload.get("interruptId", "")).strip()
                    if not interrupt_id:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少 interruptId")
                    product_root = Path(
                        os.environ.get(
                            "SMARTCOURSE_AI_INTRO_ROOT",
                            application.settings.artifact_root / "ai-intro",
                        )
                    )
                    try:
                        result = execute_fixed_ai_intro_interrupt(product_root, interrupt_id)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                    self._json(HTTPStatus.OK, result)
                    return
                if path == "/v1/uploads":
                    upload_user = self._agreement_user()
                    filename = str(payload.get("filename", ""))
                    kind = str(payload.get("kind", "asset"))
                    consent = validate_media_consent(payload.get('mediaConsent'),upload_user) if kind in {'image','audio'} else None
                    encoded = str(payload.get("contentBase64", ""))
                    if not filename or not encoded:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "缺少文件名或文件内容")
                    try:
                        content = base64.b64decode(encoded, validate=True)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Base64 文件内容无效") from exc
                    limit_mb = 280 if kind == "ppt" else 20
                    if len(content) > limit_mb * 1024 * 1024:
                        raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"上传文件超过 {limit_mb} MB")
                    try:
                        uploaded = save_upload(application.settings.artifact_root, filename, kind, content)
                    except ValueError as exc:
                        raise ApiError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
                    def save_upload_owner(data):
                        if consent:
                            uploaded['consent'] = consent
                        data.setdefault("uploads", {})[uploaded["id"]] = {**uploaded, "createdBy": upload_user}
                    application.store.transact(save_upload_owner)
                    self._json(
                        HTTPStatus.CREATED,
                        uploaded,
                    )
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)/cancel", path)
                if match:
                    def cancel(task, _data):
                        task["status"] = "cancelled"
                        task["queue"] = {"state": "cancelled"}
                        _data["executionQueue"] = [message for message in _data.get("executionQueue", [])
                                                   if message["taskId"] != task["id"]]
                        task["updatedAt"] = utc_now()
                        for stage in task.get("stages", []):
                            if stage.get("status") in {"running", "queued"}:
                                stage["status"] = "cancelled"
                        return task
                    self._json(HTTPStatus.OK, application.mutate_task(match.group(1), cancel))
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)/stages/([1-5])/retry", path)
                if match:
                    stage_index = int(match.group(2))
                    current = application.get_task(match.group(1))
                    if current.get("status") in {"queued", "processing", "running"} and current.get("queue"):
                        raise ApiError(HTTPStatus.CONFLICT, "任务已排队或正在执行")
                    result = application.mutate_task(
                        match.group(1),
                        lambda task, _data: retry_stage(task, stage_index),
                    )
                    execution = application.execute_task(
                        match.group(1), start_stage=stage_index, asynchronous=True
                    )
                    result["execution"] = execution
                    self._json(HTTPStatus.OK, result)
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)/execute", path)
                if match:
                    start_stage = int(payload.get("startStage", 1))
                    if start_stage not in range(1, 6):
                        raise ApiError(HTTPStatus.BAD_REQUEST, "startStage 必须为 1 至 5")
                    result = application.execute_task(
                        match.group(1),
                        start_stage=start_stage,
                        asynchronous=not bool(payload.get("wait", False)),
                    )
                    self._json(HTTPStatus.ACCEPTED, result)
                    return
                raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
            except (ValueError, ApiError) as exc:
                status = exc.status if isinstance(exc, (ApiError, AuthSecurityError)) else HTTPStatus.BAD_REQUEST
                message = exc.message if isinstance(exc, ApiError) else str(exc)
                self._json(status, {"message": message})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": str(exc)})

        def do_PUT(self) -> None:
            try:
                path = urlparse(self.path).path.rstrip("/") or "/"
                if application.product_services.put(self, path):
                    return
                payload = self._body()
                if application.admin.put(self, path, payload):
                    return
                if application.product_services.put(self, path, payload):
                    return
                self._guard_task_route(path)
                match = re.fullmatch(r"/v1/blueprints/([^/]+)", path)
                if match:
                    blueprint_id=unquote(match.group(1))
                    record=_read(application.settings).get('blueprints',{}).get(blueprint_id)
                    if not record:raise ApiError(HTTPStatus.NOT_FOUND,'蓝图不存在')
                    self._task_owner(record['course_id'])
                    proposal=payload.get('blueprint') if isinstance(payload.get('blueprint'),dict) else {
                        key:value for key,value in payload.items() if key!='expected_revision'
                    }
                    result=update_blueprint(application.settings,blueprint_id,proposal,payload.get('expected_revision'))
                    self._json(HTTPStatus.OK,result)
                    return
                if path == "/v1/settings/translation":
                    user_id = self._user_id(required=True)
                    policy = validate_policy(payload)
                    def save_policy(data):
                        data.setdefault("translationPolicies", {})[user_id] = policy
                        return policy
                    self._json(HTTPStatus.OK, application.store.transact(save_policy))
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)", path)
                if match:
                    name = str(payload.get("name", "")).strip()
                    if not name:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "任务名称不能为空")
                    def rename(task, _data):
                        task["name"] = name
                        task["updatedAt"] = utc_now()
                        return task
                    self._json(HTTPStatus.OK, application.mutate_task(match.group(1), rename))
                    return
                match = re.fullmatch(r"/v1/tasks/([^/]+)/assets", path)
                if match:
                    allowed = {key: copy.deepcopy(payload[key]) for key in ("referenceAudio", "referenceImage") if key in payload}
                    for key in allowed:
                        allowed[key] = self._uploaded_asset(allowed[key], "audio" if key == "referenceAudio" else "image")
                    def update_assets(task, _data):
                        updated = replace_task_assets(task, allowed)
                        consents = [asset['consent'] for asset in allowed.values() if asset.get('consent')]
                        if consents:
                            updated['assets']['consent'] = consents[-1]
                        return updated
                    task_id = match.group(1)
                    with application._execution_lock:
                        active = application._executions.get(task_id)
                        current = application.get_task(task_id)
                        if (active and active.is_alive()) or (current.get("status") == "queued" and current.get("queue")):
                            raise ApiError(HTTPStatus.CONFLICT, "当前任务仍在执行，请停止后再更换素材")
                        for key in allowed:
                            allowed[key] = self._copy_task_asset(task_id, key, allowed[key])
                        updated = application.mutate_task(task_id, update_assets)
                    if updated.get("status") == "waiting_input" and updated.get("requiredAsset") in allowed:
                        application.execute_task(task_id, start_stage=updated["currentStage"], asynchronous=True)
                        updated = application.get_task(task_id)
                    self._json(HTTPStatus.OK, updated)
                    return
                raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
            except (ValueError, ApiError) as exc:
                status = exc.status if isinstance(exc, (ApiError, AuthSecurityError)) else HTTPStatus.BAD_REQUEST
                message = exc.message if isinstance(exc, ApiError) else str(exc)
                self._json(status, {"message": message})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": str(exc)})

        def do_DELETE(self) -> None:
            try:
                path = urlparse(self.path).path.rstrip("/") or "/"
                if application.product_services.delete(self, path):
                    return
                self._guard_task_route(path)
                match = re.fullmatch(r"/v1/tasks/([^/]+)", path)
                if not match:
                    raise ApiError(HTTPStatus.NOT_FOUND, "接口不存在")
                task_id = match.group(1)
                def remove(_task, data):
                    del data["tasks"][task_id]
                    return {"deleted": True, "id": task_id}
                self._json(HTTPStatus.OK, application.mutate_task(task_id, remove))
            except (ApiError, AuthSecurityError, ValueError) as exc:
                self._json(getattr(exc, 'status', HTTPStatus.BAD_REQUEST), {"message": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": str(exc)})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="智课工坊后端服务")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    settings = Settings.from_env()
    host = args.host or settings.host
    port = args.port or settings.port
    application = SmartCourseApplication(settings)
    application.product_services.start()
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"SmartCourse API listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        application.product_services.closed.set()
        application.task_queue.close(wait=False)
        server.server_close()


if __name__ == "__main__":
    main()
