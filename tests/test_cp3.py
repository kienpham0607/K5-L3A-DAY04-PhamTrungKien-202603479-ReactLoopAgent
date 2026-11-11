"""CP3: lỗi phục hồi được, lỗi kết thúc run và trace để debug; không gọi API."""
import json
import unittest
from unittest.mock import patch

from agent import run_agent
from status_tools import StatusTools
from test_lab import FakeProvider, final, tool_call


class ErrorHandlingTests(unittest.TestCase):
    def test_max_steps_limits_model_calls_and_records_exhaustion(self):
        fake = FakeProvider([
            tool_call(str(step), 'get_status', '{"provider":"github"}')
            for step in range(1, 4)
        ])
        result = run_agent('Kiểm tra', fake, StatusTools(), max_steps=3)

        self.assertEqual(result['status'], 'max_steps')
        self.assertEqual(result['answer'], '')
        self.assertEqual(len(fake.histories), 3)
        self.assertEqual(len(result['usage']), 3)
        self.assertEqual(result['trace'][-1], {
            'event': 'max_steps', 'step': 3, 'max_steps': 3,
        })

    def test_bad_json_does_not_skip_other_calls(self):
        response = tool_call('bad', 'get_status', '{')
        good = tool_call('good', 'get_status', '{"provider":"github"}')
        response['calls'] += good['calls']
        response['message']['tool_calls'] += good['message']['tool_calls']
        fake = FakeProvider([response, final('Chỉ kiểm tra được GitHub.')])
        tools = StatusTools()

        with patch.object(tools, 'execute', wraps=tools.execute) as execute:
            result = run_agent('Kiểm tra', fake, tools)

        self.assertEqual(result['status'], 'completed')
        execute.assert_called_once_with('get_status', {'provider': 'github'})
        observations = fake.histories[1][-2:]
        self.assertEqual([m['tool_call_id'] for m in observations], ['bad', 'good'])
        self.assertEqual(json.loads(observations[0]['content'])['error'], 'INVALID_ARGUMENTS')
        self.assertEqual(json.loads(observations[1]['content'])['provider'], 'github')
        for event in result['trace']:
            self.assertIn('event', event)
            if event['event'] == 'tool':
                self.assertEqual(set(event), {'event', 'step', 'name', 'arguments', 'result'})
                self.assertEqual(event['step'], 1)

    def test_registry_errors_are_returned_to_model_and_recorded(self):
        cases = [
            ('missing', '{}', StatusTools(), 'UNKNOWN_TOOL'),
            ('get_status', '{"provider":"invalid"}', StatusTools(), 'ValueError'),
            ('get_status', '{"provider":"github"}', StatusTools(fail=True), 'TimeoutError'),
        ]
        for name, arguments, tools, error in cases:
            with self.subTest(error=error):
                fake = FakeProvider([
                    tool_call('error-call', name, arguments),
                    final('Chưa đủ dữ liệu để kết luận.'),
                ])
                result = run_agent('Kiểm tra', fake, tools)

                self.assertEqual(result['status'], 'completed')
                message = fake.histories[1][-1]
                self.assertEqual(message['tool_call_id'], 'error-call')
                observation = json.loads(message['content'])
                self.assertFalse(observation['ok'])
                self.assertEqual(observation['error'], error)
                event = next(e for e in result['trace'] if e['event'] == 'tool')
                self.assertEqual(event['result'], observation)

    def test_truncated_tool_call_is_not_executed(self):
        response = tool_call('partial', 'get_status', '{"provider":')
        response['message']['content'] = 'Nội dung chưa hoàn tất'
        response['finish'] = 'length'
        response['usage'] = {'completion_tokens': 100}
        fake = FakeProvider([response])
        tools = StatusTools()

        with patch.object(tools, 'execute') as execute:
            result = run_agent('Kiểm tra', fake, tools)

        execute.assert_not_called()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(len(fake.histories), 1)
        self.assertEqual(result['usage'], [{'completion_tokens': 100}])
        self.assertEqual(result['trace'][-1]['error'], 'OUTPUT_TRUNCATED')
        self.assertEqual(result['trace'][-1]['finish'], 'length')

    def test_provider_failure_preserves_previous_trace_and_usage(self):
        fake = FakeProvider([])
        tools = StatusTools()
        response = tool_call('first', 'get_status', '{"provider":"github"}')
        response['usage'] = {'total_tokens': 42}
        with patch.object(fake, 'complete', side_effect=[response, RuntimeError('HTTP 503')]) as complete:
            result = run_agent('Kiểm tra', fake, tools)

        self.assertEqual(complete.call_count, 2)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['usage'], [{'total_tokens': 42}])
        self.assertEqual([e['event'] for e in result['trace']],
                         ['model', 'tool', 'provider_error'])
        self.assertEqual(result['trace'][-1]['step'], 2)
        self.assertIn('HTTP 503', result['trace'][-1]['message'])

    def test_provider_credentials_are_redacted_from_errors(self):
        fake = FakeProvider([])
        fake.key = 'dummy-sensitive-provider-key'
        with patch.object(fake, 'complete', side_effect=RuntimeError('Rejected ' + fake.key)):
            result = run_agent('Kiểm tra', fake, StatusTools())

        serialized = json.dumps(result)
        self.assertNotIn(fake.key, serialized)
        self.assertIn('[REDACTED]', result['error'])

    def test_incomplete_provider_response_returns_error(self):
        fake = FakeProvider([{'message': {'role': 'assistant', 'content': 'partial'}}])
        result = run_agent('Kiểm tra', fake, StatusTools())

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['usage'], [])
        self.assertEqual(result['trace'][-1]['event'], 'provider_error')
        self.assertEqual(result['trace'][-1]['error'], 'KeyError')


if __name__ == '__main__':
    unittest.main()
