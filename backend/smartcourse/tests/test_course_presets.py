import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.course_presets import bind_course_presets, available_voice_presets


class CoursePresetTests(unittest.TestCase):
    def test_catalog_lists_only_existing_files_without_paths(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            voice = Path(directory) / 'private-reference.wav'
            voice.write_bytes(b'fixture')
            settings = SimpleNamespace(default_reference_audio=voice)
            with patch.dict('os.environ', {'SMARTCOURSE_VOICE_PRESETS': json.dumps({'su_teacher': str(voice), 'missing': '/absent/voice.wav'}),
                                          'SMARTCOURSE_VOICE_LABELS': '{"su_teacher":"苏老师音色"}'}):
                result = available_voice_presets(settings)
            self.assertEqual(result, [{'id': 'default', 'name': '苏老师音色'}, {'id': 'su_teacher', 'name': '苏老师音色'}])
            self.assertNotIn(str(voice), json.dumps(result))

    def test_invalid_labels_report_configuration_error(self):
        with patch.dict('os.environ', {'SMARTCOURSE_VOICE_PRESETS': '{}', 'SMARTCOURSE_VOICE_LABELS': '[]'}):
            with self.assertRaisesRegex(ValueError, '名称配置'):
                available_voice_presets(SimpleNamespace(default_reference_audio=None))

    def test_default_materials_are_task_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / 'voice.wav'
            photo = root / 'teacher.jpg'
            audio.write_bytes(b'fixture audio')
            photo.write_bytes(b'fixture photo')
            settings = SimpleNamespace(artifact_root=root, default_reference_audio=audio,
                                       default_reference_image=photo)
            task = {'id': 'course-one', 'assets': {}}
            with patch.dict('os.environ', {'SMARTCOURSE_VOICE_PRESETS': '{}'}):
                bind_course_presets(task, {}, settings)
            self.assertEqual(task['voiceId'], 'default')
            public_path = task['assets']['referenceAudio']['path']
            bound = root / public_path.removeprefix('/artifacts/')
            self.assertEqual(bound.read_bytes(), audio.read_bytes())
            self.assertNotEqual(bound, audio)
            self.assertTrue(public_path.startswith('/artifacts/tasks/'))
            self.assertIn('/tasks/course-one/', task['assets']['referenceImage']['url'])

    def test_unknown_voice_does_not_use_default(self):
        with patch.dict('os.environ', {'SMARTCOURSE_VOICE_PRESETS': '{}'}):
            with self.assertRaisesRegex(ValueError, '音色不存在'):
                bind_course_presets({'id': 'test', 'assets': {}}, {'voiceId': 'unknown'},
                                    SimpleNamespace(default_reference_audio=None))
