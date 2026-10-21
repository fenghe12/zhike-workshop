import unittest
from types import SimpleNamespace
from app.course_content_review import review_course_content


class ContentReviewTests(unittest.TestCase):
    def test_atomic_topic_with_commas_is_not_split(self):
        from unittest.mock import Mock
        requirement = '围绕主题：输入、权重，阈值'
        gateway = Mock()
        gateway.respond_json.return_value = {'checks': [{'requirement': requirement, 'met': True,
                                                        'sources': [{'page': 1, 'quote': '输入、权重、阈值'}]}]}
        result = review_course_content([{'page': 1, 'text': '输入、权重、阈值'}], [requirement], gateway)
        self.assertTrue(result['passed'])

    def review(self, checks):
        gateway = SimpleNamespace(respond_json=lambda *args, **kwargs: {'checks': checks})
        return review_course_content([{'page': 1, 'text': '计算：2×1+3×2+1=9'}], '包含计算例子', gateway)

    def test_valid_quote_is_required(self):
        result = self.review([{'requirement': '包含计算例子', 'met': True,
                               'sources': [{'page': 1, 'quote': '2×1+3×2+1=9'}]}])
        self.assertTrue(result['passed'])

    def test_invented_quote_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '不存在'):
            self.review([{'requirement': '包含计算例子', 'met': True,
                          'sources': [{'page': 1, 'quote': '3+3=6'}]}])

    def test_reviewer_cannot_add_cover_requirement(self):
        with self.assertRaisesRegex(ValueError, '更改'):
            self.review([{'requirement': '必须有封面', 'met': False, 'sources': []}])

    def test_missing_coverage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '逐条'):
            self.review([])
