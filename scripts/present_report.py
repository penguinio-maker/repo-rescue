#!/usr/bin/env python3
"""Compact presentation of already-collected JSON; no project/history access."""
import argparse
import json
import sys

MAX_INPUT_BYTES = 8 * 1024 * 1024


def present(report, *, verbose=False):
    if report.get('status') == 'disabled':
        result = {'message': 'Session recovery is off. Project inspection remains available.'}
    elif 'error' in report:
        code = report['error'].get('code', '')
        message = ('The selected session changed. Review fresh metadata and approve again before reading.'
                   if code == 'selected_session_changed_rediscover_and_reapprove'
                   else 'Session access needs explicit approval before continuing.' if 'approval' in code
                   else 'Inspection could not finish. Continue with available file evidence.')
        result = {'message': message}
    elif 'matching_sessions' in report:
        matches = report['matching_sessions']
        result = {'message': 'Choose sessions to review.' if matches else 'No matching sessions found in this search.',
                  'sessions': [{'choice': index, 'started': item.get('session_started_at'),
                      'modified': item.get('modified_at'), 'size_bytes': item.get('size_bytes'),
                      'project_confidence': item.get('confidence'),
                      'may_be_incomplete': item.get('body_may_be_truncated', False)}
                      for index, item in enumerate(matches[:3], 1)],
                  'more_matches': max(0, len(matches) - 3),
                  'more_to_search': bool(report.get('pagination', {}).get('next_cursor')),
                  'search_gaps': bool(report.get('coverage', {}).get('partial')
                      or report.get('match_counts', {}).get('unresolved')
                      or report.get('match_counts', {}).get('unsupported')),
                  'conversation_read': False}
    else:
        project = report.get('current_project', report)
        git = project.get('git', {})
        context = report.get('context', {})
        def items(category):
            return [{key: item.get(key) for key in ('statement', 'kind', 'current_status', 'evidence', 'timestamp')}
                    for item in context.get(category, [])[-3:]]
        docs = project.get('documentation', [])
        result = {'project': {'description_evidence': [{'path': item.get('path'),
                      'excerpt': item.get('excerpt', '')[:400], 'evidence': item.get('evidence', [])} for item in docs[:1]],
                      'branch': git.get('branch'), 'working_changes': len(git.get('working_tree', []))},
                  'where_i_left_off': items('next_actions') or items('user_goals') or items('user_statements'),
                  'past_decisions': items('decisions'), 'unresolved_problems': items('unresolved_problems'),
                  'next_actions': [
                      'Preserve current working changes before editing (requires write approval).' if git.get('working_tree')
                      else 'Confirm the next milestone from current project documentation.',
                      'Verify the reported problem against current files; execution needs separate approval.' if items('unresolved_problems')
                      else 'Review available test commands; execution needs separate approval.',
                      'Choose one small next change grounded in the evidence before requesting edit approval.'],
                  'confidence': 'Historical statements require verification against current files.' if 'current_project' in report
                      else 'File/Git evidence only; past intent is unknown.',
                  'coverage_note': 'Scoped evidence; exclusions apply. No complete-project guarantee.',
                  'incomplete': bool(report.get('coverage', {}).get('partial') or project.get('coverage', {}).get('partial')
                      or any(not item.get('coverage', {}).get('reached_eof') for item in report.get('sessions', []))),
                  'tests': project.get('test_execution', {}).get('status', 'not_run'),
                  'evidence': {}}
        used = set(git.get('evidence', []))
        for item in result['project']['description_evidence'] + result['where_i_left_off'] + result['past_decisions'] + result['unresolved_problems']:
            used.update(item.get('evidence') or [])
        for label, entries in [('current', project.get('evidence', [])),
                               ('historical', report.get('evidence', []) if 'current_project' in report else [])]:
            result['evidence'][label] = [{key: entry[key] for key in ('id', 'source', 'path', 'line', 'timestamp', 'role') if key in entry}
                                        for entry in entries if entry.get('id') in used]
    if verbose:
        result['diagnostics'] = report
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbose', action='store_true', help='Include private diagnostics; does not grant additional access.')
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError
        report = json.loads(raw)
        if not isinstance(report, dict):
            raise ValueError
        print(json.dumps(present(report, verbose=args.verbose), ensure_ascii=True, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print(json.dumps({'message': 'Expected a bounded scanner JSON report.'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
