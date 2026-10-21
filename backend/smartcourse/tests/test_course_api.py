import unittest
from app.course_api import course_status, course_request


class CourseApiTests(unittest.TestCase):
    def test_all_user_facing_target_languages_are_accepted(self):
        from app.task_model import normalize_language
        expected={'中文':'中文','英语':'英语','日语':'日语','韩语':'韩语','德语':'德语','法语':'法语','俄语':'俄语'}
        self.assertEqual({name:normalize_language(name) for name in expected},expected)
    def test_failed_course_exposes_safe_specific_error(self):
        result = course_status({'id':'task-one','status':'failed','currentStage':3,
                                'error':{'message':'目标语言口播稿超出时长对应的长度限制，需要重新组织'}})
        self.assertIn('口播稿超出', result['message'])
        self.assertEqual(result['error']['stage'], 'synthesizing_speech')

    def test_failed_course_does_not_expose_internal_paths(self):
        result = course_status({'id':'task-one','status':'failed',
                                'error':{'message':'生成失败 /home/private/secret.json'}})
        self.assertNotIn('/home/',str(result))
        self.assertIn('联系管理员',result['message'])

    def test_subtitle_selection_is_preserved(self):
        for enabled in [True, False]:
            result, _ = course_request({'mode': 'topic', 'topic': '课程', 'subtitlesEnabled': enabled},
                                       lambda *_: None)
            self.assertEqual(result['inputs']['subtitlesEnabled'], enabled)

    def test_invalid_subtitle_setting_rejected_before_asset_fetch(self):
        def forbidden(*args):
            self.fail('Invalid request must not download inputs')
        with self.assertRaisesRegex(ValueError, '字幕开关'):
            course_request({'mode': 'upload', 'subtitlesEnabled': 'false'}, forbidden)

    def test_running_task_has_no_invented_eta_or_video(self):
        result = course_status({'id': 'task-one', 'status': 'processing', 'currentStage': 3, 'overallProgress': 42})
        self.assertEqual(result['status'], 'running')
        self.assertEqual(result['stage'], 'synthesizing_speech')
        self.assertIsNone(result['etaSeconds'])
        self.assertIsNone(result['videoUrl'])

    def test_completed_task_exposes_actual_artifacts(self):
        result = course_status({'id': 'task-two', 'status': 'completed', 'overallProgress': 100,
                                'outputs': {'s5': {'languages': {'ko-KR': {'video': '/artifacts/course.mp4',
                                                                        'coursePptx': '/artifacts/course.pptx'}}}}})
        self.assertEqual(result['videoUrl'], '/artifacts/course.mp4')
        self.assertEqual(result['etaSeconds'], 0)
        self.assertEqual(result['statusUrl'], '/api/courses/task-two')
