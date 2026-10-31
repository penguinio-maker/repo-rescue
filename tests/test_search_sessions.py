"""Aggregate metadata consent using generated synthetic history only."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import inspect_project, inspect_sessions as sessions, search_sessions as search
from scripts.present_report import present
from tests import test_sessions as fixtures


class SearchCase(unittest.TestCase):
    setUp = fixtures.SessionCase.setUp
    header = fixtures.SessionCase.header
    msg = fixtures.SessionCase.msg
    write = fixtures.SessionCase.write
    initial_only = fixtures.SmartDiscoveryCase.initial_only

    def populate(self, count):
        prefixes = {}
        for index in range(count):
            header = self.header()
            path = self.write([header, self.msg(f'Goal: build fictional dock {index}')],
                              name=f'sessions/rollout-fictional-{index:03}.jsonl')
            prefixes[path] = (json.dumps(header) + '\n').encode()
        return prefixes

    def plan(self):
        return search.plan_search(self.root, opt_in_project=self.root, codex_home=self.home)

    def run_search(self, plan):
        return search.search_metadata(self.root, opt_in_project=self.root,
            codex_home=self.home, approval_id=plan['approval_id'])

    def test_plan_never_enumerates_or_reads_sessions_and_missing_consent_stops_early(self):
        self.populate(1)
        with (patch.object(sessions.os, 'scandir', side_effect=AssertionError('enumeration')),
              patch.object(Path, 'open', side_effect=AssertionError('header read'))):
            plan = self.plan()
        self.assertFalse(plan['headers_read'])
        self.assertFalse(plan['bodies_read'])
        self.assertEqual(plan['limits']['sessions'], 500)
        with patch.object(sessions, 'history_home', side_effect=AssertionError('history detected')):
            with self.assertRaisesRegex(sessions.SessionError, 'metadata_search_approval_required'):
                search.search_metadata(self.root, opt_in_project=self.root)
            with self.assertRaisesRegex(sessions.SessionError, 'session_opt_in_required'):
                search.plan_search(self.root)
            inspect_project.Scanner(self.root).run()

    def test_one_approval_covers_all_batches_with_one_inventory_and_no_body_reads(self):
        prefixes = self.populate(5)
        (self.home / 'history.jsonl').write_text('fictional legacy index excluded from this scope', encoding='utf-8')
        original_check = sessions.checked_path
        def disclosed_locations_only(path):
            self.assertNotEqual(Path(path).name, 'history.jsonl', 'undisclosed legacy index was inspected')
            return original_check(path)
        with patch.object(sessions, 'MAX_FILES', 2):
            plan = self.plan()
            with (self.initial_only(prefixes), patch.object(sessions, 'discover', wraps=sessions.discover) as inventory,
                  patch.object(sessions, 'checked_path', side_effect=disclosed_locations_only)):
                report = self.run_search(plan)
        self.assertEqual(inventory.call_count, 1)
        self.assertEqual(report['coverage']['batches_processed'], 3)
        self.assertEqual(report['match_counts']['matched'], 5)
        self.assertEqual(report['coverage']['metadata_bytes_read'], sum(map(len, prefixes.values())))
        self.assertEqual(report['coverage']['stop_reason'], 'catalogue_exhausted')
        self.assertFalse(report['coverage']['partial'])
        self.assertFalse(report['bodies_read'])
        self.assertNotIn('build fictional dock', json.dumps(report))
        self.assertNotIn(str(self.base), json.dumps(report))

    def test_aggregate_byte_budget_is_not_reset_on_the_next_batch(self):
        prefixes = self.populate(5)
        opened = []
        budget = len(next(iter(prefixes.values()))) * 2
        with patch.object(sessions, 'MAX_FILES', 1), patch.object(sessions, 'MAX_METADATA_TOTAL_BYTES', budget):
            plan = self.plan()
            with self.initial_only(prefixes, opened):
                report = self.run_search(plan)
        self.assertEqual(len(opened), 2)
        self.assertEqual(report['coverage']['metadata_bytes_read'], budget)
        self.assertEqual(report['coverage']['stop_reason'], 'metadata_byte_limit')
        self.assertEqual(report['coverage']['uninspected_sessions'], 3)
        self.assertTrue(report['coverage']['partial'])

    def test_internal_batch_size_does_not_invalidate_aggregate_scope(self):
        prefixes = self.populate(5)
        with patch.object(sessions, 'MAX_FILES', 2):
            plan = self.plan()
        with patch.object(sessions, 'MAX_FILES', 1), self.initial_only(prefixes):
            report = self.run_search(plan)
        self.assertEqual(report['coverage']['batches_processed'], 5)
        self.assertEqual(report['match_counts']['matched'], 5)

    def test_session_budget_and_deadline_stop_without_automatic_restart(self):
        prefixes = self.populate(5)
        with patch.object(search, 'MAX_SEARCH_FILES', 3), patch.object(sessions, 'MAX_FILES', 2):
            plan = self.plan()
            with self.initial_only(prefixes):
                report = self.run_search(plan)
        self.assertEqual(report['coverage']['sessions_inspected'], 3)
        self.assertEqual(report['coverage']['stop_reason'], 'session_limit')
        clock = [0]
        original = sessions.MetadataReader.record
        def slow(reader, source):
            result = original(reader, source)
            clock[0] = 31
            return result
        with patch.object(search.time, 'monotonic', side_effect=lambda: clock[0]):
            plan = self.plan()
            with self.initial_only(prefixes), patch.object(sessions.MetadataReader, 'record', slow):
                report = self.run_search(plan)
        self.assertEqual(report['coverage']['sessions_inspected'], 1)
        self.assertEqual(report['coverage']['stop_reason'], 'processing_time_limit')

    def test_changed_project_home_or_limits_need_new_approval_before_enumeration(self):
        self.populate(1)
        plan = self.plan()
        other = self.base / 'other-fictional-project'
        other.mkdir()
        with patch.object(sessions, 'discover', side_effect=AssertionError('enumeration')):
            for root, home in [(other, self.home), (self.root, other)]:
                with self.assertRaisesRegex(sessions.SessionError, 'metadata_search_scope_changed_renew_approval'):
                    search.search_metadata(root, opt_in_project=root, codex_home=home, approval_id=plan['approval_id'])
            with patch.object(search, 'MAX_SEARCH_FILES', 501):
                with self.assertRaisesRegex(sessions.SessionError, 'metadata_search_scope_changed_renew_approval'):
                    self.run_search(plan)
            with patch.object(sessions, 'MAX_METADATA_TOTAL_BYTES', 12345):
                with self.assertRaisesRegex(sessions.SessionError, 'metadata_search_scope_changed_renew_approval'):
                    self.run_search(plan)
        view = present({'error': {'code': 'metadata_search_scope_changed_renew_approval'}})
        self.assertIn('location or limits changed', view['message'])
        self.assertNotIn('metadata_search_scope', json.dumps(view))

    def test_directory_replacement_during_search_stops_before_next_header(self):
        prefixes = self.populate(3)
        plan = self.plan()
        original = sessions.MetadataReader.record
        def replace_root(reader, source):
            result = original(reader, source)
            self.root.rename(self.base / 'old-fictional-project')
            self.root.mkdir()
            return result
        opened = []
        with self.initial_only(prefixes, opened), patch.object(sessions.MetadataReader, 'record', replace_root):
            with self.assertRaisesRegex(sessions.SessionError, 'metadata_search_scope_changed_renew_approval'):
                self.run_search(plan)
        self.assertEqual(len(opened), 1)

    def test_frozen_inventory_does_not_silently_add_new_sessions(self):
        prefixes = self.populate(2)
        plan = self.plan()
        original = sessions.discover
        original_open = Path.open
        def add_after_snapshot(*args, **kwargs):
            report = original(*args, **kwargs)
            # Fixture mutation only; the scanner's guarded open still rejects this file.
            with original_open(self.home / 'sessions/rollout-fictional-new.jsonl', 'w', encoding='utf-8') as stream:
                stream.write(json.dumps(self.header()) + '\n')
            return report
        with self.initial_only(prefixes), patch.object(sessions, 'discover', side_effect=add_after_snapshot):
            report = self.run_search(plan)
        self.assertEqual(report['coverage']['sessions_inspected'], 2)
        self.assertEqual(len(report['matching_sessions']), 2)

    def test_separate_body_gate_and_joint_selection_keep_per_session_validation(self):
        self.populate(3)
        plan = self.plan()
        report = self.run_search(plan)
        selected = report['matching_sessions'][:2]
        refs = [item['session_ref'] for item in selected]
        with patch.object(Path, 'open', side_effect=AssertionError('body access without approval')):
            with self.assertRaisesRegex(sessions.SessionError, 'body_approval_required'):
                sessions.recover(self.root, opt_in_project=self.root, session_refs=refs)
            with self.assertRaisesRegex(sessions.SessionError, 'invalid_transcript_approval'):
                sessions.recover(self.root, opt_in_project=self.root, review_id=plan['approval_id'], session_refs=refs)
        # A change to an unrelated candidate never invalidates these selected approvals.
        unrelated = self.home / report['matching_sessions'][2]['path']
        with unrelated.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(self.msg('Goal: unrelated update')) + '\n')
        recovered = sessions.recover(self.root, opt_in_project=self.root, codex_home=self.home,
            metadata_approval_project=self.root, review_id=[item['approval_id'] for item in selected], session_refs=refs)
        self.assertEqual({item['session_ref'] for item in recovered['sessions']}, set(refs))
        self.assertEqual(len(recovered['context']['user_goals']), 2)
        # Growth of a selected file still requires fresh consent before any read.
        with (self.home / selected[0]['path']).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(self.msg('Goal: selected update')) + '\n')
        with patch.object(Path, 'open', side_effect=AssertionError('changed selection opened')):
            with self.assertRaisesRegex(sessions.SessionError, 'selected_session_changed_rediscover_and_reapprove'):
                sessions.recover(self.root, opt_in_project=self.root, codex_home=self.home,
                    metadata_approval_project=self.root, review_id=[item['approval_id'] for item in selected], session_refs=refs)

    def test_cli_plan_search_and_multiple_body_flags_preserve_the_two_gates(self):
        self.populate(2)
        script = str(Path(search.__file__).resolve())
        common = ['--project', str(self.root), '--session-opt-in', str(self.root), '--codex-home', str(self.home)]
        def run(action, *extra):
            result = subprocess.run([sys.executable, '-B', script, action, *common, *extra],
                                    capture_output=True, text=True, check=False)
            return result.returncode, json.loads(result.stdout)
        code, plan = run('plan')
        self.assertEqual(code, 0)
        code, denied = run('search')
        self.assertEqual(code, 2)
        self.assertEqual(denied['error']['code'], 'metadata_search_approval_required')
        code, report = run('search', '--approve-search', plan['approval_id'])
        self.assertEqual(code, 0)
        command = [sys.executable, '-B', str(Path(sessions.__file__).resolve()), 'recover', *common,
                   '--approve-metadata', str(self.root)]
        for item in report['matching_sessions']:
            command += ['--approve-bodies', item['approval_id'], '--session', item['session_ref']]
        recovered = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(len(json.loads(recovered.stdout)['sessions']), 2)

    def test_empty_mixed_and_catalogue_limited_results_remain_explicitly_scoped(self):
        empty = self.run_search(self.plan())
        self.assertEqual(empty['coverage']['metadata_bytes_read'], 0)
        self.assertEqual(empty['matching_sessions'], [])
        self.write([self.header()])
        self.write([self.header(cwd=self.home)], name='sessions/rollout-fictional-other.jsonl')
        self.write([{'type': 'event_msg', 'payload': {'message': 'not a header'}}],
                   name='sessions/rollout-fictional-unsupported.jsonl')
        with patch.object(sessions, 'MAX_FILES', 1):
            report = self.run_search(self.plan())
        self.assertEqual(report['match_counts'], {'matched': 1, 'unmatched': 1, 'unresolved': 0, 'unsupported': 1})
        with patch.object(sessions, 'MAX_ENTRIES', 1):
            limited = self.run_search(self.plan())
        self.assertTrue(limited['coverage']['partial'])
        self.assertEqual(limited['coverage']['catalogue']['entries_visited'], 1)


if __name__ == '__main__':
    unittest.main()
