import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from app.compute_lease import synchronize_compute_lease
from app.remote_media import media_service_status


class ComputeLeaseTests(unittest.TestCase):
    def test_renewal_refreshes_both_application_and_platform_expiry_checks(self):
        now = time.time()
        old = {'id': 'owned-compute', 'status': 'RUNNING', 'smartcourseOwner': 'course-owner',
               'smartcourseDeadline': now - 5,
               'lease': {'enable': True, 'type': 'TIMING', 'create_at': int((now - 7200) * 1000), 'duration': 3600000}}
        fresh = {**old, 'lease': {'enable': True, 'type': 'TIMING', 'create_at': int(now * 1000), 'duration': 3600000}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'compute-state.json'
            path.write_text(json.dumps(old))
            with patch.dict(os.environ, {'SMARTCOURSE_REMOTE_MEDIA': '1', 'SMARTCOURSE_MEDIA_SERVICE_ENABLED': '1',
                                         'SMARTCOURSE_REMOTE_STATE': str(path), 'SMARTCOURSE_COMPUTE_OWNER': 'course-owner'}):
                self.assertEqual(media_service_status(), 'LEASE_EXPIRED')
                synchronize_compute_lease(path, fresh, owner='course-owner', deadline=now + 1200)
                self.assertEqual(media_service_status(), 'RUNNING')
                saved = json.loads(path.read_text())
                self.assertEqual(saved['lease'], fresh['lease'])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_other_instance_or_excessive_deadline_preserves_current_state(self):
        now = time.time()
        current = {'id': 'owned-compute', 'status': 'RUNNING', 'smartcourseOwner': 'course-owner',
                   'smartcourseDeadline': now + 1200,
                   'lease': {'enable': True, 'type': 'TIMING', 'create_at': int(now * 1000), 'duration': 3600000}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'compute-state.json'
            path.write_text(json.dumps(current))
            other = {**current, 'id': 'another-compute'}
            with self.assertRaises(ValueError):
                synchronize_compute_lease(path, other, owner='course-owner', deadline=now + 1200)
            with self.assertRaises(ValueError):
                synchronize_compute_lease(path, current, owner='course-owner', deadline=now + 7200)
            self.assertEqual(json.loads(path.read_text()), current)
