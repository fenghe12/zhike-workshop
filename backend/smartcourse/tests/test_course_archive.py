import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from app.course_archive import archive_course


class CourseArchiveTests(unittest.TestCase):
    def test_private_records_excluded_and_user_outputs_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            course = root / 'course'
            (course / 'pages').mkdir(parents=True)
            for name in ('index.html', 'timeline.json', 'pages/page-001.mp4',
                         'pages/page-001.export.json', 'pages/.page-002.mp4',
                         'pages/page-003.pending.json'):
                (course / name).write_text(name)
            result = archive_course(course, root / 'course.zip')
            with ZipFile(result) as archive:
                self.assertEqual(set(archive.namelist()), {'index.html', 'timeline.json', 'pages/page-001.mp4'})

    def test_rejects_external_link_without_overwriting_existing_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            course = root / 'course'
            course.mkdir()
            outside = root / 'private.txt'
            outside.write_text('private')
            (course / 'unexpected.txt').symlink_to(outside)
            destination = root / 'course.zip'
            destination.write_bytes(b'previous completed archive')
            with self.assertRaises(ValueError):
                archive_course(course, destination)
            self.assertEqual(destination.read_bytes(), b'previous completed archive')
