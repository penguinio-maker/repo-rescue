"""Chronological, metadata-only choices with synthetic host identities/history."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import inspect_sessions as sessions, search_sessions as search
from scripts.present_report import present, session_choices
from tests import test_sessions as fixtures

FICTIONAL_ACTIVE = 'ffffffff-ffff-4fff-8fff-ffffffffffff'


class ShortlistCase(unittest.TestCase):
    header = fixtures.SessionCase.header
    msg = fixtures.SessionCase.msg
    write = fixtures.SessionCase.write
    initial_only = fixtures.SmartDiscoveryCase.initial_only

    def setUp(self):
        fixtures.SessionCase.setUp(self)
        host = patch.dict(search.os.environ, {'CODEX_THREAD_ID': FICTIONAL_ACTIVE, 'CODEX_SESSION_ID': ''})
        host.start()
        self.addCleanup(host.stop)

    def populate(self, count):
        prefixes = {}
        for index in range(1, count + 1):
            header = self.header()
            header['timestamp'] = header['payload']['timestamp'] = f'2020-01-{index:02}T12:00:00Z'
            header['payload']['id'] = f'00000000-0000-4000-8000-{index:012}'
            # Same-size bodies contain different content; metadata cannot establish usefulness.
            text = ('Goal: build the fictional original harbor plan' if index == 1
                    else 'Goal: repeat a fictional recovery check').ljust(160)
            path = self.write([header, self.msg(text)], name=f'sessions/rollout-fictional-{index:02}.jsonl')
            prefixes[path] = (json.dumps(header) + os.linesep).encode()
        return prefixes

    def match(self, prefixes, **kwargs):
        plan = search.plan_search(self.root, opt_in_project=self.root, codex_home=self.home)
        with self.initial_only(prefixes):
            return search.search_metadata(self.root, opt_in_project=self.root, codex_home=self.home,
                                          approval_id=plan['approval_id'], **kwargs)

    def check_count(self, count):
        report = self.match(self.populate(count))
        # Renderer must work even if a caller supplies newest-first results.
        report['matching_sessions'].reverse()
        before = copy.deepcopy(report)
        with patch.object(Path, 'open', side_effect=AssertionError('presentation opened history')):
            view = present(report)
            full = present(report, all_sessions=True)
        expected = list(range(1, count + 1)) if count <= 10 else [1, 2, 3, 4, 5, 11, 12, 13, 14, 15]
        self.assertEqual([item['choice'] for item in view['sessions']], expected)
        self.assertEqual(len(full['sessions']), count)
        self.assertEqual(view['show_all_option'], count > 10)
        self.assertEqual(view['sessions'][0]['date'], '2020-01-01')
        self.assertEqual(view['sessions'][-1]['date'], f'2020-01-{count:02}')
        self.assertEqual(len({item['size'] for item in full['sessions']}), 1)
        for row in full['sessions']:
            self.assertEqual(set(row), {'choice', 'date', 'size', 'active'})
            self.assertFalse(row['active'])
        text = json.dumps(view)
        for hidden in ('original harbor plan', 'recovery check', '.jsonl', 'approval_id', 'session_ref', 'confidence', 'bytes_read'):
            self.assertNotIn(hidden, text)
        self.assertEqual(report, before)
        # Oldest useful context remains reachable, but only after explicit body consent.
        chosen = session_choices(report)[view['sessions'][0]['choice'] - 1]
        with patch.object(Path, 'open', side_effect=AssertionError('unapproved body read')):
            with self.assertRaisesRegex(sessions.SessionError, 'body_approval_required'):
                sessions.recover(self.root, opt_in_project=self.root, session_refs=[chosen['session_ref']])
        recovered = sessions.recover(self.root, opt_in_project=self.root, codex_home=self.home,
            metadata_approval_project=self.root, review_id=chosen['approval_id'], session_refs=[chosen['session_ref']])
        self.assertIn('original harbor plan', json.dumps(recovered['context']))

    def test_one_matching_session(self):
        self.check_count(1)

    def test_three_matching_sessions(self):
        self.check_count(3)

    def test_ten_matching_sessions(self):
        self.check_count(10)

    def test_fifteen_matching_sessions_include_oldest_and_newest(self):
        self.check_count(15)

    def test_active_session_excluded_in_both_views_and_joint_consent_still_works(self):
        prefixes = self.populate(3)
        report = self.match(prefixes, active_session_id='00000000-0000-4000-8000-000000000002')
        self.assertTrue(report['matching_sessions'][1]['is_active'])
        for all_sessions in (False, True):
            view = present(report, all_sessions=all_sessions)
            self.assertEqual([row['date'] for row in view['sessions']], ['2020-01-01', '2020-01-03'])
            self.assertTrue(view['active_excluded'])
        selected = session_choices(report)
        recovered = sessions.recover(self.root, opt_in_project=self.root, codex_home=self.home,
            metadata_approval_project=self.root, review_id=[item['approval_id'] for item in selected],
            session_refs=[item['session_ref'] for item in selected])
        self.assertEqual({item['session_ref'] for item in recovered['sessions']}, {item['session_ref'] for item in selected})
        self.assertNotIn(report['matching_sessions'][1]['session_ref'], {item['session_ref'] for item in recovered['sessions']})

    def test_host_identity_fallback_and_unknown_status_never_guess_from_recency(self):
        prefixes = self.populate(3)
        identifier = '00000000-0000-4000-8000-000000000001'
        with patch.dict(search.os.environ, {'CODEX_THREAD_ID': '', 'CODEX_SESSION_ID': identifier}):
            known = self.match(prefixes)
        self.assertTrue(known['matching_sessions'][0]['is_active'])
        with patch.dict(search.os.environ, {'CODEX_THREAD_ID': '', 'CODEX_SESSION_ID': ''}):
            unknown = self.match(prefixes)
        self.assertTrue(all(item['is_active'] is None for item in unknown['matching_sessions']))
        view = present(unknown)
        self.assertEqual(len(view['sessions']), 3)
        self.assertIn('unknown', view['message'])
        self.assertTrue(all(row['active'] is None for row in view['sessions']))

    def test_missing_header_identity_is_unknown_even_with_a_known_host_identity(self):
        header = self.header()
        del header['payload']['id']
        path = self.write([header, self.msg('Goal: fictional historical task')])
        report = self.match({path: (json.dumps(header) + os.linesep).encode()})
        self.assertIsNone(report['matching_sessions'][0]['is_active'])
        self.assertIsNone(present(report)['sessions'][0]['active'])

    def test_show_all_cli_is_metadata_only_and_preserves_choice_numbers(self):
        report = self.match(self.populate(15))
        script = str(Path(__file__).resolve().parents[1] / 'scripts/present_report.py')
        result = subprocess.run([sys.executable, '-B', script, '--all-sessions'],
                                input=json.dumps(report), capture_output=True, text=True, check=True)
        full = json.loads(result.stdout)
        subset = present(report)
        self.assertEqual(len(full['sessions']), 15)
        self.assertNotIn('diagnostics', full)
        self.assertEqual([full['sessions'][item['choice'] - 1] for item in subset['sessions']], subset['sessions'])


if __name__ == '__main__':
    unittest.main()
