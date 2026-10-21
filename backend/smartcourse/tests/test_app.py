from __future__ import annotations

import json
import base64
import io
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

from app.config import Settings
from app.course_agent import CourseStructureAgent
from app.gateway import _extract_text, extract_json
from app.server import SmartCourseApplication, make_handler
from app.task_model import create_task, retry_stage, validate_creation
from agents.code_video_composer import CodeVideoComposeAgent


class FakePipelineRunner:
    def run(self, task_id, task, progress, start_stage=1):
        results = {}
        for index in range(start_stage, 6):
            detail = {
                "stage": index,
                "processed": index * 2,
                "total": index * 2,
                "artifact": f"/artifacts/tasks/{task_id}/s{index}/result.json",
            }
            progress(index, "running", 50, detail)
            progress(index, "completed", 100, detail)
            results[f"s{index}"] = detail
        return {"taskId": task_id, "status": "completed", "stages": results}


class TaskModelTests(unittest.TestCase):
    def test_topic_source_matches_generator_language(self):
        value = validate_creation({'name': '课程', 'mode': 'topic', 'sourceLanguage': '英语',
                                   'targetLanguages': ['英语'], 'inputs': {'topic': '神经网络'}})
        self.assertEqual(value['sourceLanguage'], '中文')

    def test_topic_parameters_survive_validation(self):
        inputs = {'topic': '神经网络', 'totalPages': 3, 'durationMinutes': 5,
                  'targetLearners': '本科生', 'requirements': '包含计算例子'}
        result = validate_creation({'name': '课程', 'mode': 'topic',
                                    'targetLanguages': ['中文'], 'inputs': inputs})
        self.assertEqual(result['inputs'], inputs)

    def test_invalid_topic_page_count_is_rejected(self):
        for value in [0, -1, 31, True, 1.5, '3']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_creation({'name': '课程', 'mode': 'topic', 'targetLanguages': ['中文'],
                                   'inputs': {'topic': '神经网络', 'totalPages': value}})

    def test_upload_without_user_script_is_accepted(self):
        value=validate_creation({'name': '课程', 'mode': 'upload',
                                 'targetLanguages': ['中文'],
                                 'inputs': {'ppt': {'name': 'course.pptx'}}})
        self.assertEqual(value['inputs']['ppt']['name'],'course.pptx')

    def test_upload_mode_requires_ppt_and_user_script(self):
        value = validate_creation(
            {
                "name": "课程",
                "mode": "upload",
                "targetLanguages": ["英语", "ja-JP"],
                "inputs": {"ppt": {"name": "course.pptx"}, "script": {"name": "lecture.docx"}},
            }
        )
        self.assertEqual(value["targetLanguages"], ["英语", "日语"])

    def test_topic_mode_only_requires_topic(self):
        value = validate_creation(
            {
                "name": "课程",
                "mode": "topic",
                "targetLanguages": ["中文"],
                "inputs": {"topic": "人工智能概述"},
            }
        )
        self.assertEqual(value["mode"], "topic")

    def test_code_mode_requires_lesson_identifier(self):
        value = validate_creation(
            {
                "name": "一次函数动画课",
                "mode": "code",
                "targetLanguages": ["中文"],
                "inputs": {"lessonId": "linear-function"},
            }
        )
        self.assertEqual(value["inputs"]["lessonId"], "linear-function")

    def test_uploaded_source_language_is_preserved(self):
        task = create_task(
            {
                "name": "English source course",
                "mode": "upload",
                "sourceLanguage": "英语",
                "targetLanguages": ["中文", "英语"],
                "inputs": {"ppt": {"name": "course.pptx"}, "script": {"name": "lecture.docx"}},
            }
        )
        self.assertEqual(task["sourceLanguage"], "英语")

    def test_creation_has_exact_five_stages(self):
        task = create_task(
            {
                "name": "课程",
                "mode": "topic",
                "targetLanguages": ["中文", "英语"],
                "inputs": {"topic": "人工智能概述"},
            }
        )
        self.assertEqual(
            [stage["title"] for stage in task["stages"]],
            ["课件结构化", "多语种翻译与校验", "语音合成", "数字人生成", "视频合成"],
        )

    def test_retry_removes_previous_error(self):
        task = create_task(
            {
                "name": "课程",
                "mode": "topic",
                "targetLanguages": ["中文"],
                "inputs": {"topic": "人工智能概述"},
            }
        )
        task["error"] = {"message": "previous failure"}
        task["stages"][2]["error"] = "previous failure"
        task["stages"][2]["startedAt"] = "2026-08-11T00:00:00Z"
        task["stages"][2]["etaSeconds"] = 999
        task["outputs"]["s3"] = {"artifact": "old"}
        for index in [0,1]:
            task["stages"][index].update(status="completed", progress=100)
            task["outputs"]["s"+str(index+1)] = {"artifact": "upstream"}
        retry_stage(task, 3)
        self.assertNotIn("error", task)
        self.assertNotIn("error", task["stages"][2])
        self.assertNotIn("startedAt", task["stages"][2])
        self.assertNotIn("etaSeconds", task["stages"][2])
        self.assertNotIn("s3", task["outputs"])


class GatewayParsingTests(unittest.TestCase):
    def test_responses_text(self):
        self.assertEqual(
            _extract_text(
                {
                    "output": [
                        {"content": [{"type": "output_text", "text": "SMARTCOURSE_API_OK"}]}
                    ]
                }
            ),
            "SMARTCOURSE_API_OK",
        )

    def test_json_fence(self):
        self.assertEqual(extract_json('```json\n{"ok": true}\n```'), {"ok": True})


class CourseStructureTests(unittest.TestCase):
    def test_existing_ppt_extracts_title_points_script_and_layout(self):
        from pptx import Presentation

        with tempfile.TemporaryDirectory() as directory:
            pptx_path = Path(directory) / "course.pptx"
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[1])
            slide.shapes.title.text = "人工智能概述"
            slide.placeholders[1].text = "起源与定义\n历史与趋势\n技术架构"
            presentation.save(pptx_path)

            result = CourseStructureAgent().from_pptx(pptx_path, "task_test")
            self.assertEqual(result["total_pages"], 1)
            page = result["pages"][0]
            self.assertEqual(page["title"], "人工智能概述")
            self.assertIn("历史与趋势", page["key_points"])
            self.assertTrue(page["script_text"])
            self.assertTrue(page["layout"]["regions"])


class SubtitleLayoutTests(unittest.TestCase):
    def test_long_chinese_subtitle_wraps_within_safe_width(self):
        value = "测量pH时，把试纸放在洁净玻璃片上，用玻璃棒蘸取待测溶液，滴在试纸上并立即与标准比色卡比较。"
        wrapped = CodeVideoComposeAgent._wrap_subtitle_text(value)
        self.assertGreater(len(wrapped.splitlines()), 1)
        self.assertTrue(
            all(
                CodeVideoComposeAgent._display_width(line) <= 56
                for line in wrapped.splitlines()
            )
        )

    def test_short_subtitle_remains_on_one_line(self):
        value = "反射角等于入射角。"
        self.assertEqual(CodeVideoComposeAgent._wrap_subtitle_text(value), value)


class ServerTests(unittest.TestCase):
    def test_interruption_routes_require_course_owner(self):
        from unittest.mock import patch
        _, owner = self.api('POST', '/v1/auth/register', {'account': 'answer-owner@example.test',
                             'password': 'test-password', 'name': 'Owner'})
        _, other = self.api('POST', '/v1/auth/register', {'account': 'answer-other@example.test',
                             'password': 'test-password', 'name': 'Other'})
        _, task = self.api('POST', '/v1/tasks', {'name': '课程', 'mode': 'topic',
                          'inputs': {'topic': '神经网络'}, 'targetLanguages': ['韩语'],
                          'autoExecute': False}, owner['accessToken'])
        path = '/api/courses/' + task['id'] + '/interruptions'
        with patch('app.interruption_jobs.submit_interruption', return_value={'id': 'answer-test', 'status': 'queued'}) as submit:
            for method in ['POST', 'GET']:
                for token, expected in [('', 401), (other['accessToken'], 403)]:
                    with self.assertRaises(error.HTTPError) as caught:
                        self.api(method, path, {} if method == 'POST' else None, token=token)
                    self.assertEqual(caught.exception.code, expected)
            submit.assert_not_called()
            status, result = self.api('POST', path, {'question': '为什么？'}, token=owner['accessToken'])
            self.assertEqual(status, 202)
            self.assertEqual(result['status'], 'queued')
            submit.assert_called_once()
        status, result = self.api('GET', path, token=owner['accessToken'])
        self.assertEqual((status, result), (200, []))
        with self.assertRaises(error.HTTPError) as caught:
            self.api('GET', path + '/missing', token=owner['accessToken'])
        self.assertEqual(caught.exception.code, 404)

    def test_unified_upload_binds_ppt_script_and_photo(self):
        import zipfile
        from PIL import Image
        _, user = self.api('POST', '/v1/auth/register', {'account': 'upload-course@example.test',
                          'password': 'course-password', 'name': 'Upload owner'})
        token = user['accessToken']
        ppt = io.BytesIO()
        from pptx import Presentation
        presentation = Presentation()
        presentation.slides.add_slide(presentation.slide_layouts[6])
        presentation.save(ppt)
        doc = io.BytesIO()
        with zipfile.ZipFile(doc, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>第1页 课程讲稿</w:t></w:r></w:p></w:body></w:document>')
        photo = io.BytesIO()
        Image.new('RGB', (2, 2)).save(photo, format='PNG')
        urls = {}
        for kind, filename, content in [('ppt', 'course.pptx', ppt.getvalue()),
                                         ('script', 'lecture.docx', doc.getvalue()),
                                         ('image', 'teacher.png', photo.getvalue())]:
            _, asset = self.api('POST', '/v1/uploads', {'filename': filename, 'kind': kind,
                               'contentBase64': base64.b64encode(content).decode()}, token)
            urls[kind] = asset['path']
        status, result = self.api('POST', '/api/courses', {'mode': 'upload', 'pptUrl': urls['ppt'],
                                  'scriptUrl': urls['script'], 'teacherImageUrl': urls['image'],
                                  'targetLanguages': ['ko-KR']}, token)
        self.assertEqual(status, 202)
        _, task = self.api('GET', '/v1/tasks/' + result['jobId'], token=token)
        self.assertEqual(task['inputs']['ppt']['path'], urls['ppt'])
        self.assertEqual(task['inputs']['script']['path'], urls['script'])
        self.assertEqual(task['assets']['referenceImage']['path'], urls['image'])

    def test_unified_upload_requires_script_before_fetch(self):
        from unittest.mock import patch
        with patch('app.course_download.download_course_input') as download:
            with self.assertRaises(error.HTTPError) as caught:
                self.api('POST', '/api/courses', {'mode': 'upload', 'pptUrl': 'https://storage.test/a.pptx',
                                                'targetLanguages': ['韩语']})
            self.assertEqual(caught.exception.code, 400)
            download.assert_not_called()

    def test_unified_topic_submission_preserves_inputs(self):
        _, user = self.api('POST', '/v1/auth/register', {'account': 'submit-owner@example.test',
                           'password': 'course-password', 'name': 'Owner'})
        status, result = self.api('POST', '/api/courses', {'mode': 'topic', 'topic': '神经网络',
                                  'audience': '本科生', 'pageCount': 3, 'durationMinutes': 4,
                                  'targetLanguages': ['ko-KR'], 'voiceId': 'default'}, user['accessToken'])
        self.assertEqual(status, 202)
        _, saved = self.api('GET', '/v1/tasks/' + result['jobId'], token=user['accessToken'])
        self.assertEqual(saved['inputs']['totalPages'], 3)
        self.assertEqual(saved['inputs']['targetLearners'], '本科生')
        self.assertEqual(saved['targetLanguages'], ['韩语'])

    def test_unified_submission_requires_login_before_downloading(self):
        from unittest.mock import patch
        with patch('app.course_download.download_course_input') as download:
            with self.assertRaises(error.HTTPError) as caught:
                self.api('POST', '/api/courses', {'mode': 'upload', 'pptUrl': 'https://invalid.test/a.pptx',
                         'scriptUrl': 'https://invalid.test/a.docx'}, token='')
            self.assertEqual(caught.exception.code, 401)
            download.assert_not_called()

    def test_unified_course_query_keeps_task_permissions(self):
        _, user = self.api('POST', '/v1/auth/register', {'account': 'course-owner@example.test',
                           'password': 'course-password', 'name': 'Owner'})
        _, other = self.api('POST', '/v1/auth/register', {'account': 'course-other@example.test',
                            'password': 'course-password', 'name': 'Other'})
        _, task = self.api('POST', '/v1/tasks', {'name': '课程', 'mode': 'topic',
                          'inputs': {'topic': '神经网络'}, 'targetLanguages': ['韩语'],
                          'autoExecute': False}, user['accessToken'])
        status, result = self.api('GET', '/api/courses/' + task['id'], token=user['accessToken'])
        self.assertEqual(status, 200)
        self.assertEqual(result['jobId'], task['id'])
        self.assertIsNone(result['videoUrl'])
        self.assertIsNone(result['etaSeconds'])
        for token, expected in [('', 401), (other['accessToken'], 403)]:
            with self.assertRaises(error.HTTPError) as caught:
                self.api('GET', '/api/courses/' + task['id'], token=token)
            self.assertEqual(caught.exception.code, expected)

    def test_task_and_upload_ownership_are_enforced(self):
        _, first = self.api("POST", "/v1/auth/register", {"account": "isolation-a@example.test", "password": "isolation-password", "name": "A"})
        token_a = first["accessToken"]
        from tests.test_uploads import audio
        _, asset = self.api("POST", "/v1/uploads", {"filename": "voice.wav", "kind": "audio", "contentBase64": base64.b64encode(audio(b"\0\0" * 160)).decode()}, token_a)
        payload = {"name": "Private task", "mode": "topic", "inputs": {"topic": "Neural networks"}, "targetLanguages": ["德语"], "autoExecute": False}
        _, task_a = self.api("POST", "/v1/tasks", payload, token_a)
        _, second = self.api("POST", "/v1/auth/register", {"account": "isolation-b@example.test", "password": "isolation-password", "name": "B"})
        token_b = second["accessToken"]
        _, task_b = self.api("POST", "/v1/tasks", payload, token_b)
        _, visible = self.api("GET", "/v1/tasks", token=token_b)
        self.assertNotIn(task_a["id"], [task["id"] for task in visible])
        for method, path, value in [("GET", "/v1/tasks/"+task_a["id"], None),
                                    ("POST", "/v1/tasks/"+task_a["id"]+"/cancel", {}),
                                    ("PUT", "/v1/tasks/"+task_b["id"]+"/assets", {"referenceAudio": asset})]:
            with self.subTest(path=path), self.assertRaises(error.HTTPError) as caught:
                self.api(method, path, value, token_b)
            self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(error.HTTPError) as caught:
            self.api("GET", "/v1/tasks", token="")
        self.assertEqual(caught.exception.code, 401)
        with request.urlopen(request.Request(self.base+asset["path"], headers={"Cookie": "smartcourse-session="+token_a}), timeout=5) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(error.HTTPError) as caught:
            request.urlopen(request.Request(self.base+asset["path"], headers={"Authorization": "Bearer "+token_b}), timeout=5)
        self.assertEqual(caught.exception.code, 403)

    def test_translation_settings_are_persisted(self):
        _, original = self.api("GET", "/v1/settings/translation")
        try:
            status, updated = self.api("PUT", "/v1/settings/translation", {"semantic_similarity": .93, "maxRetries": 0})
            self.assertEqual(status, 200)
            self.assertEqual(updated["maxRetries"], 0)
            _, stored = self.api("GET", "/v1/settings/translation")
            self.assertEqual(stored["semantic_similarity"], .93)
        finally:
            self.api("PUT", "/v1/settings/translation", original)

    def test_upload_same_name_keeps_original_bytes(self):
        from tests.test_uploads import audio
        contents = [audio(b"\x00\x00" * 160), audio(b"\x01\x00" * 320)]
        uploaded = []
        for content in contents:
            status, asset = self.api("POST", "/v1/uploads", {
                "filename": "讲者 #1.wav", "kind": "audio",
                "contentBase64": base64.b64encode(content).decode(),
            })
            self.assertEqual(status, 201)
            uploaded.append(asset)
        self.assertNotEqual(uploaded[0]["path"], uploaded[1]["path"])
        for asset, content in zip(uploaded, contents):
            with request.urlopen(request.Request(self.base + asset["path"], headers={"Authorization": "Bearer "+self.default_token}), timeout=5) as response:
                self.assertEqual(response.read(), content)

    def test_upload_rejects_invalid_content(self):
        for filename, content in [("../x.png", b"invalid"), ("x.png", b"invalid")]:
            with self.subTest(filename=filename), self.assertRaises(error.HTTPError) as caught:
                self.api("POST", "/v1/uploads", {"filename": filename, "kind": "image",
                         "contentBase64": base64.b64encode(content).decode()})
            self.assertEqual(caught.exception.code, 400)

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        settings = Settings(
            data_root=root / "data",
            artifact_root=root / "artifacts",
            gateway_url="http://invalid",
            gateway_model="test",
            gateway_token="",
            host="127.0.0.1",
            port=0,
        )
        application = SmartCourseApplication(settings, pipeline_runner=FakePipelineRunner())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(application))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.default_token = ""
        cls.api("POST", "/v1/auth/register", {"account": "fixture@example.test", "password": "fixture-password", "name": "Fixture"})

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temporary.cleanup()

    @classmethod
    def api(cls, method: str, path: str, value=None, token: str | None = None):
        data = None if value is None else json.dumps(value).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token is None:
            token = cls.default_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(cls.base + path, data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            if path in {"/v1/auth/login", "/v1/auth/register"} and result.get("accessToken"):
                cls.default_token = result["accessToken"]
            return response.status, result

    def test_s1_research_endpoint_lists_all_directions_and_agents(self):
        status, value = self.api("GET", "/v1/s1/research")
        self.assertEqual(status, 200)
        self.assertEqual(value["schemaVersion"], "2026.2")
        self.assertEqual(len(value["directions"]), 9)
        self.assertEqual(len(value["agentRoles"]), 9)
        self.assertIn("visual_quality_report.json", value["outputs"])

    def test_complete_task_management_flow(self):
        status, registered = self.api(
            "POST",
            "/v1/auth/register",
            {
                "account": "teacher@example.edu",
                "password": "123456",
                "name": "教师",
                "institution": "高校在线教育中心",
            },
        )
        self.assertEqual(status, 201)
        token = registered["accessToken"]
        self.assertNotIn("passwordHash", registered["user"])
        from pptx import Presentation
        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[6])
        buffer = io.BytesIO()
        deck.save(buffer)
        _, uploaded_ppt = self.api("POST", "/v1/uploads", {"filename": "course.pptx", "kind": "ppt", "contentBase64": base64.b64encode(buffer.getvalue()).decode()})
        import zipfile
        lecture = io.BytesIO()
        with zipfile.ZipFile(lecture, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types/>')
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>课程讲稿</w:t></w:r></w:p></w:body></w:document>')
        _, uploaded_script = self.api('POST', '/v1/uploads', {
            'filename': 'lecture.docx', 'kind': 'script',
            'contentBase64': base64.b64encode(lecture.getvalue()).decode()}, token)

        status, task = self.api(
            "POST",
            "/v1/tasks",
            {
                "name": "人工智能概述",
                "mode": "upload",
                "targetLanguages": ["中文", "英语", "日语", "韩语", "德语", "法语"],
                "inputs": {"ppt": uploaded_ppt, "script": uploaded_script},
            },
            token,
        )
        self.assertEqual(status, 201)
        task_id = task["id"]
        self.assertEqual(len(task["targetLanguages"]), 6)
        self.api("POST", f"/v1/tasks/{task_id}/execute", {"wait": True})

        _, task = self.api("PUT", f"/v1/tasks/{task_id}", {"name": "人工智能概述国际版"})
        self.assertEqual(task["name"], "人工智能概述国际版")
        from tests.test_uploads import audio
        _, speaker = self.api("POST", "/v1/uploads", {"filename": "speaker.wav", "kind": "audio", "contentBase64": base64.b64encode(audio(b"\0\0" * 160)).decode()})
        _, task = self.api(
            "PUT",
            f"/v1/tasks/{task_id}/assets",
            {"referenceAudio": speaker},
        )
        self.assertEqual(task["assets"]["referenceAudio"]["name"], "speaker.wav")
        _, task = self.api("POST", f"/v1/tasks/{task_id}/stages/3/retry", {})
        self.assertEqual(task["currentStage"], 3)
        _, task = self.api("POST", f"/v1/tasks/{task_id}/cancel", {})
        self.assertEqual(task["status"], "cancelled")
        _, deleted = self.api("DELETE", f"/v1/tasks/{task_id}")
        self.assertTrue(deleted["deleted"])

    def test_health(self):
        status, result = self.api("GET", "/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(result["stages"], ["S1", "S2", "S3", "S4", "S5"])
        self.assertEqual(result["execution"], "full-pipeline")
        self.assertEqual(result["pedagogicalIr"], "2026.1")
        self.assertEqual(
            result["pedagogicalExperiments"],
            ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"],
        )

    def test_code_lesson_catalog(self):
        status, result = self.api("GET", "/v1/code-lessons")
        self.assertEqual(status, 200)
        self.assertEqual(len(result), 3)
        self.assertEqual(
            {item["lessonId"] for item in result},
            {"linear-function", "light-reflection", "ph-indicator"},
        )

    def test_phase_a_experiment_catalog_and_ir_endpoint(self):
        status, experiments = self.api("GET", "/v1/experiments")
        self.assertEqual(status, 200)
        self.assertEqual(
            [item["experimentId"] for item in experiments],
            ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"],
        )
        status, result = self.api(
            "GET",
            "/v1/pedagogical-ir/linear-function?condition=A4",
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["pedagogicalIr"]["timeline"]["eventCount"], 18)
        self.assertTrue(result["constraintReport"]["valid"])

    def test_e2_endpoint_generates_all_sync_conditions(self):
        status, result = self.api(
            "POST",
            "/v1/experiments/e2",
            {
                "lessonId": "light-reflection",
                "learnerState": {"attention": 0.4, "mastery": 0.5},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            set(result["experiment"]["variants"]),
            {"B0", "B1", "B2", "B3", "B4", "B5"},
        )
        self.assertLess(
            result["experiment"]["variants"]["B3"]["evaluation"]["temporalAlignment"],
            result["experiment"]["variants"]["B4"]["evaluation"]["temporalAlignment"],
        )

    def test_learner_state_policy_and_adaptive_experiment_endpoints(self):
        status, updated = self.api(
            "POST",
            "/v1/learner-state/update",
            {
                "learnerState": {"mastery": 0.6, "attention": 0.8},
                "observation": {
                    "concept": "反射定律",
                    "correct": False,
                    "errorType": "conceptual_gap",
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["diagnosis"]["label"], "conceptual_gap")
        status, policy = self.api(
            "POST",
            "/v1/teaching-policy/select",
            {
                "condition": "E4",
                "learnerState": updated["learnerState"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(policy["primaryAction"], "counterfactual_question")
        status, experiment = self.api(
            "POST",
            "/v1/experiments/adaptive",
            {
                "lessonId": "ph-indicator",
                "learnerState": updated["learnerState"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(set(experiment["e3Variants"]), {"C0", "C1", "C2", "C3", "C4"})
        self.assertEqual(
            set(experiment["e5Variants"]),
            {"E0", "E1", "E2", "E3", "E4", "E5"},
        )

    def test_phase_c_experiment_endpoints(self):
        state = {
            "mastery": 0.4,
            "attention": 0.3,
            "engagement": 0.7,
            "cognitiveLoad": 0.5,
        }
        status, proactive = self.api(
            "POST",
            "/v1/proactive-intervention",
            {"condition": "D4", "learnerState": state},
        )
        self.assertEqual(status, 200)
        self.assertTrue(proactive["shouldIntervene"])
        status, memory = self.api(
            "POST",
            "/v1/memory/update",
            {
                "condition": "F4",
                "evidence": {"concept": "斜率", "success": False, "confidence": 0.8},
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(memory["entries"]), 1)
        status, personalization = self.api(
            "POST",
            "/v1/personalization/plan",
            {"condition": "G5", "learnerState": state},
        )
        self.assertEqual(status, 200)
        self.assertTrue(all(personalization["enabledLayers"].values()))
        status, alignment = self.api(
            "POST",
            "/v1/pedagogical-alignment/check",
            {
                "condition": "H4",
                "learnerState": state,
                "interaction": {"requestsDirectAnswer": True, "studentReasoning": ""},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(alignment["studentReasoningRequired"])
        status, prescreen = self.api(
            "POST",
            "/v1/evaluator/prescreen",
            {
                "condition": "I0",
                "constraintReport": {"constraintSatisfaction": 1.0},
                "syncReport": {"temporalAlignment": 0.5, "semanticAlignment": 1.0},
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(prescreen["passed"])

    def test_experiment_runner_endpoint_preserves_unmeasured_human_outcomes(self):
        status, result = self.api(
            "POST",
            "/v1/experiments/run",
            {
                "experimentIds": ["E1", "E2"],
                "lessonIds": ["linear-function"],
                "seed": 11,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["conditionCount"], 11)
        self.assertEqual(result["humanOutcomeStatus"], "not_measured")
        self.assertTrue(result["manifest"].startswith("/artifacts/experiments/"))

    def test_protocol_and_analysis_endpoints(self):
        status, protocol = self.api(
            "POST",
            "/v1/experiments/protocol",
            {
                "experimentId": "E2",
                "conditions": ["B0", "B4"],
                "effectSize": 0.5,
                "alpha": 0.05,
                "power": 0.8,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(protocol["registrationStatus"], "draft_not_preregistered")
        status, analysis = self.api(
            "POST",
            "/v1/experiments/analyze",
            {
                "rows": [
                    {
                        "participant_id": "",
                        "lesson_id": "linear-function",
                        "experiment_id": "E2",
                        "condition": "B0",
                        "pretest": "",
                        "posttest": "",
                    }
                ]
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(analysis["humanOutcomeStatus"], "not_measured")

    def test_teacher_avatar_rehearsal_and_demo_endpoints(self):
        status, engines = self.api("GET", "/v1/avatar-engines")
        self.assertEqual(status, 200)
        self.assertEqual({item["engine"] for item in engines["engines"]}, {"float", "longcat-video-avatar-1.5"})
        status, profile = self.api(
            "POST",
            "/v1/teacher-profile/validate",
            {
                "profileId": "teacher_test",
                "referenceImage": "/tmp/image.png",
                "referenceAudio": "/tmp/voice.wav",
                "consent": {"authorized": True},
                "fullBodyEngine": {"name": "longcat-video-avatar-1.5", "available": True},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(profile["readiness"]["gestureCourse"])
        status, rehearsal = self.api(
            "POST",
            "/v1/rehearsal/analyze",
            {
                "courseStructure": {"course_topic": "课程", "pages": [{"page_id": 1, "title": "概念", "key_points": ["A"], "script_text": "这是讲稿。"}]},
                "pedagogicalIr": {"timeline": {"durationSeconds": 1200, "events": []}},
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(rehearsal["publishReady"])
        status, demo = self.api("GET", "/v1/demo-course")
        self.assertEqual(status, 200)
        self.assertEqual(demo["preset"]["demoId"], "ai-literacy-general")

    def test_synchronous_full_pipeline_updates_all_stages(self):
        _, registered = self.api(
            "POST",
            "/v1/auth/register",
            {
                "account": "pipeline@example.edu",
                "password": "123456",
                "name": "流程测试教师",
            },
        )
        token = registered["accessToken"]
        _, task = self.api(
            "POST",
            "/v1/tasks",
            {
                "name": "六语种课程",
                "mode": "topic",
                "targetLanguages": ["中文", "英语", "日语", "韩语", "德语", "法语"],
                "inputs": {"topic": "人工智能概述", "totalPages": 2},
            },
            token,
        )
        status, completed = self.api(
            "POST",
            f"/v1/tasks/{task['id']}/execute",
            {"wait": True},
            token,
        )
        self.assertEqual(status, 202)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["overallProgress"], 100)
        self.assertEqual([stage["progress"] for stage in completed["stages"]], [100] * 5)
        self.assertIn("result", completed["outputs"])


if __name__ == "__main__":
    unittest.main()
