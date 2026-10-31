"""Public beta workflow tests using fictional projects/history only."""
import json
import copy
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
        self.assertIn('unclear', initial['where_you_left_off'][0])
        self.assertNotIn('tests', initial)
        self.assertEqual(len(initial['next_steps']), 3)
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
        self.assertIn('timing-based fishing', json.dumps(view['where_you_left_off']))
        self.assertIn('maximum 3 boats', json.dumps(view['previous_decisions']))
        self.assertIn('boats disappear', json.dumps(view['unresolved']))
        self.assertEqual(len(view['next_steps']), 3)
        self.assertNotIn('tests', view)
        self.assertEqual(present(recovered, verbose=True)['diagnostics'], recovered)
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
            self.assertEqual(len(view['next_steps']), 3)
        view = present({'current_project': {}, 'context': {}, 'coverage': {'partial': True},
                        'sessions': [{'coverage': {'reached_eof': False, 'stop_reason': 'record_byte_limit'}}]})
        self.assertEqual(view['warning'], 'Some historical context may be missing.')
        self.assertNotIn('tests', view)
        self.assertNotIn('record_byte_limit', json.dumps(view))

    def test_cli_verbose_is_presentation_only_and_invalid_input_is_sanitized(self):
        command = [sys.executable, '-B', str(REPO / 'scripts' / 'present_report.py')]
        raw = {'status': 'disabled', 'bodies_read': False}
        plain = subprocess.run(command, input=json.dumps(raw), text=True, capture_output=True, check=True)
        self.assertNotIn('diagnostics', json.loads(plain.stdout))
        detail = subprocess.run(command + ['--verbose'], input=json.dumps(raw), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(detail.stdout)['diagnostics'], raw)
        alias = subprocess.run(command + ['--details'], input=json.dumps(raw), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(alias.stdout), json.loads(detail.stdout))
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
        self.assertEqual(view['previous_decisions'], [])
        details = present(raw, verbose=True)['diagnostics']
        self.assertEqual(details['context']['decisions'][0]['kind'], 'ai_suggestion')
        self.assertEqual(details['context']['decisions'][0]['current_status'], 'unverified')
        self.assertEqual(details['evidence'][0]['line'], 2)
        self.assertEqual(details['evidence'][0]['role'], 'assistant')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(view))

    def test_default_report_has_only_five_sections_and_no_internal_metadata(self):
        raw = self.match()
        selected = raw['matching_sessions'][0]
        report = inspect_sessions.recover(self.project, opt_in_project=self.project,
            metadata_approval_project=self.project, codex_home=self.home,
            review_id=selected['approval_id'], session_refs=[selected['session_ref']])
        original = copy.deepcopy(report)
        view = present(report)
        self.assertEqual(set(view), {'project', 'where_you_left_off', 'previous_decisions', 'unresolved', 'next_steps'})
        self.assertEqual(view['project'], {'name': 'Fictional harbor', 'description': 'A small fishing game.'})
        self.assertLess(len(json.dumps(view).split()), 200)
        for hidden in ('.jsonl', 'session_ref', 'records_read', 'bytes_read', 'EOF', 'parser',
                       'diagnostics', 'evidence', 'current_status', 'test_execution', 'hash'):
            self.assertNotIn(hidden, json.dumps(view))
        self.assertEqual(report, original)
        self.assertEqual(present(report, verbose=True)['diagnostics'], original)

    def test_duplicate_facts_and_ai_proposals_do_not_become_repeated_decisions(self):
        def fact(text, kind='historical_statement'):
            return {'statement': text, 'kind': kind}
        report = {'documentation': [], 'context': {
            'user_goals': [fact('Goal: maximum three boats'), fact('Goal: timing-based fishing')],
            'decisions': [fact('Decision: maximum three boats'), fact('Decision: Maximum three boats!'),
                          fact('Decision: four boats', 'ai_suggestion')],
            'next_actions': [fact('Next: check saved boats'), fact('Next: Check saved boats!')]}}
        view = present(report)
        text = json.dumps(view).lower()
        self.assertEqual(text.count('maximum three boats'), 1)
        self.assertEqual(text.count('check saved boats'), 1)
        self.assertNotIn('four boats', text)
        self.assertEqual(len(view['next_steps']), 3)

    def test_up_to_five_decisions_and_short_warning_with_full_details(self):
        report = {'current_project': {}, 'sessions': [{'coverage': {'partial': True, 'reached_eof': True}}],
                  'context': {'decisions': [{'statement': 'Decision: ' + choice, 'kind': 'historical_statement'}
                      for choice in ['manual saving', 'small maps', 'three boats', 'short days', 'timed fishing', 'single player']]},
                  'coverage': {'partial': True, 'stop_reason': 'input_text_limit'}}
        view = present(report)
        self.assertEqual(len(view['previous_decisions']), 5)
        self.assertEqual(view['warning'], 'Some historical context may be missing.')
        self.assertNotIn('input_text_limit', json.dumps(view))
        self.assertLess(len(json.dumps(view).split()), 200)
        self.assertEqual(present(report, verbose=True)['diagnostics'], report)

    def test_technical_text_is_kept_in_details_without_inventing_progress(self):
        report = {'context': {'user_goals': [
            {'statement': 'Goal: read sessions/fictional.jsonl', 'kind': 'historical_statement'},
            {'statement': 'Goal: inspect abc12345def67890', 'kind': 'historical_statement'},
            {'statement': 'Goal: EOF records_read: 9', 'kind': 'historical_statement'}]}}
        view = present(report)
        self.assertIn('unclear', view['where_you_left_off'][0])
        self.assertEqual(view['previous_decisions'], [])
        self.assertEqual(view['unresolved'], [])
        self.assertNotIn('.jsonl', json.dumps(view))
        self.assertNotIn('abc12345', json.dumps(view))
        self.assertEqual(present(report, verbose=True)['diagnostics'], report)

    def test_current_changes_do_not_imply_unfinished_work_or_accept_ai_goals(self):
        report = {'git': {'working_tree': [{'path': 'game.py'}]},
                  'context': {'user_goals': [{'statement': 'Goal: add submarines', 'kind': 'ai_suggestion'}]}}
        view = present(report)
        self.assertEqual(view['where_you_left_off'], ['There are local changes to review.'])
        self.assertEqual(view['previous_decisions'], [])
        self.assertNotIn('earlier goal', json.dumps(view))
        self.assertNotIn('submarines', json.dumps(view))
        self.assertEqual(len(view['next_steps']), 3)


if __name__ == '__main__':
    unittest.main()
