import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))
from agent import run_agent
from scenarios import ScenarioTools
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final


class ScenarioTests(unittest.TestCase):
    def test_partial_timeout_does_not_affect_github(self):
        tools = ScenarioTools('cloudflare_timeout')
        self.assertEqual(tools.execute('get_status', {'provider': 'cloudflare'})['error'], 'TimeoutError')
        self.assertEqual(tools.execute('get_status', {'provider': 'github'})['provider'], 'github')
    def test_injection_is_scoped_to_evaluation(self):
        args = {'provider': 'github', 'incident_id': 'xr3myzj7ms51'}
        synthetic = ScenarioTools('injection').execute('get_incident_details', args)
        normal = StatusTools().execute('get_incident_details', args)
        self.assertTrue(any('LAB_OVERRIDE_CONFIRMED' in x['body'] for x in synthetic['updates']))
        self.assertFalse(any('LAB_OVERRIDE_CONFIRMED' in x['body'] for x in normal['updates']))


class EvidenceGateTests(unittest.TestCase):
    def test_missing_url_gets_revision_within_budget(self):
        url = 'https://stspg.io/pjgptg3cfc6n'
        fake = FakeProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
                             final('Incident đã xử lý.'), final('Incident đã xử lý. '+url)])
        result = run_agent('Kiểm tra', fake, StatusTools(), max_steps=4)
        self.assertEqual(result['status'], 'completed')
        self.assertIn(url, result['answer'])
        self.assertTrue(any(x['event'] == 'validation_missing_source' for x in result['trace']))
    def test_missing_url_at_budget_limit_is_not_completed(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'), final('Thiếu nguồn')])
        self.assertEqual(run_agent('x', fake, StatusTools(), max_steps=2)['status'], 'max_steps')
    def test_failed_tool_does_not_require_source(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', '{"provider":"github","incident_id":"missing"}'), final('Không tìm được incident')])
        self.assertEqual(run_agent('x', fake, StatusTools())['status'], 'completed')

    def test_e5_homepage_requires_revision_to_observed_incident_url(self):
        url = 'https://stspg.io/hj74883wgn0t'
        missing_source = final('Đã giải quyết. Nguồn: https://www.githubstatus.com')
        fake = FakeProvider([
            tool_call('e5', 'get_incident_details',
                      '{"provider":"github","incident_id":"tc28c0wzrnpz"}'),
            missing_source,
            final('Đã giải quyết. Nguồn: ' + url),
        ])
        result = run_agent('Kiểm tra Copilot Mission Control', fake, StatusTools(), max_steps=3)

        self.assertEqual(result['status'], 'completed')
        self.assertIn(url, result['answer'])
        self.assertEqual(len(fake.histories), 3)
        self.assertIs(fake.histories[2][-2], missing_source['message'])
        self.assertEqual(fake.histories[2][-1]['role'], 'user')
        self.assertIn(url, fake.histories[2][-1]['content'])
        event = next(e for e in result['trace'] if e['event'] == 'validation_missing_source')
        self.assertEqual(event['step'], 2)
        self.assertEqual(event['observed_urls'], [url])

    def test_unobserved_url_does_not_satisfy_source_check(self):
        url = 'https://stspg.io/pjgptg3cfc6n'
        fake = FakeProvider([
            tool_call('a', 'get_incident_details',
                      '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final('Nguồn: https://example.org/unobserved-incident'),
            final('Nguồn: ' + url),
        ])
        result = run_agent('Kiểm tra', fake, StatusTools(), max_steps=3)

        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(fake.histories), 3)
        self.assertIn(url, result['answer'])

    def test_repeated_missing_source_cannot_exceed_budget(self):
        fake = FakeProvider([
            tool_call('a', 'get_incident_details',
                      '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final('Thiếu nguồn lần 1'),
            final('Thiếu nguồn lần 2'),
        ])
        result = run_agent('Kiểm tra', fake, StatusTools(), max_steps=3)

        self.assertEqual(result['status'], 'max_steps')
        self.assertEqual(result['answer'], '')
        self.assertEqual(len(fake.histories), 3)
        self.assertEqual(len(result['usage']), 3)
        events = [e for e in result['trace'] if e['event'] == 'validation_missing_source']
        self.assertEqual([e['step'] for e in events], [2, 3])
        self.assertEqual(result['trace'][-1]['event'], 'max_steps')

    def test_url_in_failed_result_does_not_become_evidence(self):
        fake = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"missing"}'),
            final('Không lấy được dữ liệu incident.'),
        ])
        tools = StatusTools()
        with patch.object(tools, 'execute', return_value={
            'ok': False, 'error': 'TimeoutError', 'url': 'https://example.org/failed-incident',
        }):
            result = run_agent('Kiểm tra', fake, tools)

        self.assertEqual(result['status'], 'completed')
        self.assertFalse(any(e['event'] == 'validation_missing_source' for e in result['trace']))

if __name__ == '__main__':
    unittest.main()
