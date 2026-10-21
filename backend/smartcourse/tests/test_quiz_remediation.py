import unittest

from app.interruption_jobs import public_interruption
from app.quiz_remediation import _public


class QuizRemediationTests(unittest.TestCase):
    def test_queued_record_has_status_url_without_video(self):
        record={'id':'answer-test','courseId':'task-test','status':'queued',
                'purpose':'quiz_remediation','videoUrl':None}
        result=_public(record,'question-test')
        self.assertEqual(result['statusUrl'],'/v1/questions/question-test/remediation/answer-test')
        self.assertNotIn('posterUrl',result)

    def test_completed_record_exposes_poster(self):
        record={'id':'answer-test','courseId':'task-test','status':'completed',
                'purpose':'quiz_remediation','videoUrl':'/artifacts/tasks/task-test/answer.mp4'}
        result=public_interruption(record)
        self.assertEqual(result['posterUrl'],'/artifacts/tasks/task-test/answer.png')


if __name__=='__main__':
    unittest.main()
