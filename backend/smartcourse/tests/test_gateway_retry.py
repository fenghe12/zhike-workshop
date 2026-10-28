import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.gateway import GatewayError, GatewayJSONError, ResponsesGateway, extract_json


class GatewayRetryTests(unittest.TestCase):
    def gateway(self):
        return ResponsesGateway(SimpleNamespace(gateway_url='http://model.local/v1/chat/completions',
            gateway_model='fixture-model', gateway_token='private-fixture-token'))

    def test_incomplete_and_invalid_json_retry_without_accepting_partial_content(self):
        for invalid in ['{"pages":[{"page_id":1}', '{"pages":[1,]}', 'No JSON returned']:
            with self.subTest(invalid=invalid):
                gateway = self.gateway()
                gateway.respond = Mock(side_effect=[invalid, '{"pages":[1,2]}'])
                self.assertEqual(gateway.respond_json('Return both pages'), {'pages':[1,2]})
                self.assertEqual(gateway.respond.call_count, 2)
                self.assertIn('Return both pages', gateway.respond.call_args.args[0])
                self.assertIn('complete', gateway.respond.call_args.args[0])

    def test_only_three_json_retries_and_last_raw_response_is_retained(self):
        gateway = self.gateway()
        gateway.respond = Mock(return_value='{"pages":[')
        with self.assertRaises(GatewayJSONError) as caught:
            gateway.respond_json('Return pages')
        self.assertEqual(gateway.respond.call_count, 4)
        self.assertEqual(caught.exception.attempts, 4)
        self.assertEqual(caught.exception.raw_text, '{"pages":[')

    def test_page_owner_can_disable_nested_json_retries(self):
        gateway = self.gateway()
        gateway.respond = Mock(return_value='{"pages":[')
        with self.assertRaises(GatewayJSONError):
            gateway.respond_json('Return page', json_retries=0)
        self.assertEqual(gateway.respond.call_count, 1)

    def test_transport_failure_is_not_repeated_by_json_validation(self):
        gateway = self.gateway()
        gateway.respond = Mock(side_effect=GatewayError('transport exhausted its retries'))
        with self.assertRaisesRegex(GatewayError, 'transport exhausted'):
            gateway.respond_json('Return page')
        self.assertEqual(gateway.respond.call_count, 1)

    def test_original_response_and_finish_reason_are_saved_privately(self):
        gateway = self.gateway()
        payloads = [
            {'choices':[{'message':{'content':'{"pages":['}, 'finish_reason':'length'}]},
            {'choices':[{'message':{'content':'{"pages":[1]}'}, 'finish_reason':'stop'}]},
        ]
        replies = [io.BytesIO(json.dumps(value).encode()) for value in payloads]
        with tempfile.TemporaryDirectory() as directory, patch('app.gateway.request.urlopen', side_effect=replies):
            root = Path(directory)/'responses'
            self.assertEqual(gateway.respond_json('Return page', json_record_dir=root), {'pages':[1]})
            first = json.loads((root/'attempt-1.json').read_text())
            self.assertEqual(first['rawText'], '{"pages":[')
            self.assertEqual(first['finishReasons'], ['length'])
            self.assertIn('不完整', first['parseError'])
            second = json.loads((root/'attempt-2.json').read_text())
            self.assertEqual(second['finishReasons'], ['stop'])
            self.assertNotIn('parseError', second)
            self.assertEqual(stat.S_IMODE((root/'attempt-1.json').stat().st_mode), 0o600)
            self.assertNotIn('private-fixture-token', (root/'attempt-1.json').read_text())

    def test_quoted_brackets_and_embedded_json_are_parsed(self):
        self.assertEqual(extract_json('Result: {"text":"[quoted] }", "pages":[1]} End'),
                         {'text':'[quoted] }', 'pages':[1]})


if __name__ == '__main__':
    unittest.main()
