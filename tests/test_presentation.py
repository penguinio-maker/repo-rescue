"""Public beta workflow tests using fictional projects/history only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import inspect_project, inspect_sessions
from scripts.present_report import present

REPO = Path(__file__).resolve().parents[1]


class PresentationCase(unittest.TestCase):
    def setUp(self):
        scratch = REPO / '.test-tmp'
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='beta-fictional-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.project = self.base / 'tiny-harbor'
        self.home = self.base / 'fictional-codex-home'
        self.project.mkdir()
        self.home.mkdir()
        (self.project / 'README.md').write_text('# Fictional harbor\nA small fishing game.\n', encoding='utf-8')
        self.env = patch.dict(os.environ, {'CODEX_HOME': str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        records = [
            {'timestamp': '2020-01-01T12:00:00Z', 'type': 'session_meta', 'payload': {'cwd': str(self.project)}},
            {'timestamp': '2020-01-01T12:01:00Z', 'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                'content': [{'type': 'input_text', 'text': 'Goal: timing-based fishing\nDecision: maximum 3 boats\nProblem: boats disappear after reload\nNext: verify saved boats'}]}}]
        path = self.home / 'sessions' / 'rollout-fictional-beta.jsonl'
        path.parent.mkdir()
        path.write_text(''.join(json.dumps(item) + '\n' for item in records), encoding='utf-8')

    def match(self):
        return inspect_sessions.match_metadata(self.project, opt_in_project=self.project,
            metadata_approval_project=self.project, codex_home=self.home)

    def test_project_shortlist_approval_and_concise_recovery_flow(self):
        with patch.object(inspect_sessions, 'history_home', side_effect=AssertionError('history detected')):
            project = inspect_project.Scanner(self.project).run()
            initial = present(project)
        self.assertEqual(initial['where_i_left_off'], [])
        self.assertEqual(initial['tests'], 'not_run')
        self.assertEqual(len(initial['next_actions']), 3)
        with self.assertRaisesRegex(inspect_sessions.SessionError, 'metadata_approval_required'):
            inspect_sessions.match_metadata(self.project, opt_in_project=self.project)
        raw = self.match()
        shortlist = present(raw)
        self.assertEqual(shortlist['sessions'][0]['choice'], 1)
        self.assertNotIn('timing-based fishing', json.dumps(shortlist))
        selected = raw['matching_sessions'][shortlist['sessions'][0]['choice'] - 1]
        with self.assertRaisesRegex(inspect_sessions.SessionError, 'body_approval_required'):
            inspect_sessions.recover(self.project, opt_in_project=self.project,
                metadata_approval_project=self.project, session_refs=[selected['session_ref']])
        recovered = inspect_sessions.recover(self.project, opt_in_project=self.project,
            metadata_approval_project=self.project, codex_home=self.home,
            review_id=selected['approval_id'], session_refs=[selected['session_ref']])
        view = present(recovered)
        self.assertIn('verify saved boats', json.dumps(view['where_i_left_off']))
        self.assertIn('maximum 3 boats', json.dumps(view['past_decisions']))
        self.assertIn('boats disappear', json.dumps(view['unresolved_problems']))
        self.assertEqual(len(view['next_actions']), 3)
        self.assertEqual(view['tests'], 'not_run')
        self.assertTrue(view['evidence']['historical'])
        for hidden in ('approval_id', 'review_id', 'snapshot', 'next_cursor', 'session_ref'):
            self.assertNotIn(hidden, json.dumps(view))

    def test_shortlist_hides_transport_and_offers_more_without_cursor_strings(self):
        raw = self.match()
        raw['matching_sessions'] *= 5
        raw['pagination']['next_cursor'] = 'CURSOR_SENTINEL'
        view = present(raw)
        self.assertEqual(len(view['sessions']), 3)
        self.assertEqual(view['more_matches'], 2)
        self.assertTrue(view['more_to_search'])
        self.assertNotIn('CURSOR_SENTINEL', json.dumps(view))
        for hidden in ('approval_id', 'review_id', 'snapshot', 'next_cursor', 'session_ref'):
            self.assertNotIn(hidden, json.dumps(view))
        with patch.object(inspect_sessions, 'recover', side_effect=AssertionError('body read')):
            self.assertEqual(present(raw, verbose=True)['diagnostics'], raw)

    def test_declining_bodies_empty_matches_and_partial_reads_remain_useful(self):
        raw = self.match()
        with patch.object(inspect_sessions.RecordReader, 'record', side_effect=AssertionError('body read')):
            self.assertFalse(present(raw)['conversation_read'])
            raw['matching_sessions'] = []
            self.assertEqual(present(raw)['sessions'], [])
            self.assertIn('No matching', present(raw)['message'])
            view = present(inspect_project.Scanner(self.project).run())
            self.assertEqual(len(view['next_actions']), 3)
        view = present({'current_project': {}, 'context': {}, 'coverage': {'partial': True},
                        'sessions': [{'coverage': {'reached_eof': False, 'stop_reason': 'record_byte_limit'}}]})
        self.assertTrue(view['incomplete'])
        self.assertEqual(view['tests'], 'not_run')
        self.assertNotIn('record_byte_limit', json.dumps(view))

    def test_cli_verbose_is_presentation_only_and_invalid_input_is_sanitized(self):
        command = [sys.executable, '-B', str(REPO / 'scripts' / 'present_report.py')]
        raw = {'status': 'disabled', 'bodies_read': False}
        plain = subprocess.run(command, input=json.dumps(raw), text=True, capture_output=True, check=True)
        self.assertNotIn('diagnostics', json.loads(plain.stdout))
        detail = subprocess.run(command + ['--verbose'], input=json.dumps(raw), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(detail.stdout)['diagnostics'], raw)
        bad = subprocess.run(command, input='PRIVATE_SENTINEL', text=True, capture_output=True)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn('PRIVATE_SENTINEL', bad.stdout + bad.stderr)

    def test_material_gaps_and_changed_selection_are_plain_without_exposing_diagnostics(self):
        raw = self.match()
        raw['match_counts']['unresolved'] = 1
        self.assertTrue(present(raw)['search_gaps'])
        raw = {'error': {'code': 'selected_session_changed_rediscover_and_reapprove',
                         'private_detail': 'PRIVATE_SENTINEL'}}
        view = present(raw)
        self.assertIn('approve again', view['message'])
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(view))
        self.assertEqual(present(raw, verbose=True)['diagnostics'], raw)

    def test_suggestions_and_uncertainty_keep_evidence_and_are_not_promoted_to_facts(self):
        raw = {'current_project': {}, 'context': {'decisions': [{
            'statement': 'Decision: consider a fourth boat', 'kind': 'ai_suggestion',
            'current_status': 'unverified', 'timestamp': '2020-01-01T12:00:00Z', 'evidence': ['s1']}]},
            'evidence': [{'id': 's1', 'source': 'session_statement', 'path': 'sessions/fictional.jsonl',
                          'line': 2, 'role': 'assistant', 'timestamp': '2020-01-01T12:00:00Z'},
                         {'id': 'unused', 'private_diagnostic': 'PRIVATE_SENTINEL'}]}
        view = present(raw)
        item = view['past_decisions'][0]
        self.assertEqual(item['kind'], 'ai_suggestion')
        self.assertEqual(item['current_status'], 'unverified')
        self.assertEqual(view['evidence']['historical'][0]['line'], 2)
        self.assertEqual(view['evidence']['historical'][0]['role'], 'assistant')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(view))
        self.assertIn('No complete-project guarantee', view['coverage_note'])


if __name__ == '__main__':
    unittest.main()
