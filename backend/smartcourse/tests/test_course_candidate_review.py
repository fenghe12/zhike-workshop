import unittest
from app.course_candidate_review import structural_findings


class CandidateReviewTests(unittest.TestCase):
    def test_structural_failure_cannot_be_removed_by_content_review(self):
        report = {'findings': ['页面文字超出边界', '第1页：缺少计算示例'],
                  'content_critic': [{'page': 1, 'errors': ['缺少计算示例']}]}
        self.assertEqual(structural_findings(report), ['页面文字超出边界'])

    def test_unclassified_findings_remain_blocking(self):
        self.assertEqual(structural_findings({'findings': ['第1页：渲染失败']}), ['第1页：渲染失败'])
