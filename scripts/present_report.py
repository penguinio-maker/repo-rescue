#!/usr/bin/env python3
"""Compact presentation of already-collected JSON; no project/history access."""
import argparse
from datetime import datetime, timezone
import json
import re
import sys

MAX_INPUT_BYTES = 8 * 1024 * 1024


def _started(item):
    value = item.get('session_started_at')
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.astimezone(timezone.utc) if date.tzinfo else None
    except ValueError:
        return None


def session_choices(report):
    """Private choice-to-evidence mapping; stable across compact/show-all views."""
    matches = [item for item in report['matching_sessions'] if item.get('is_active') is not True]
    latest = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(matches, key=lambda item: (_started(item) is None, _started(item) or latest))


def _size(value):
    if type(value) is not int or value < 0:
        return 'Unknown'
    if value >= 1024 * 1024:
        return f'{value / (1024 * 1024):.1f} MiB'
    return f'{value / 1024:.1f} KiB'


def _shortlist(report, all_sessions):
    choices = session_choices(report)
    indexes = list(range(len(choices)))
    if len(indexes) > 10 and not all_sessions:
        dated = [index for index in indexes if _started(choices[index]) is not None]
        edges = dated if dated else indexes
        selected = set(edges[:5] + edges[-5:])
        for index in indexes:
            if len(selected) == 10:
                break
            selected.add(index)
        indexes = sorted(selected)
    rows = []
    for index in indexes:
        item = choices[index]
        date = _started(item)
        rows.append({'choice': index + 1, 'date': date.date().isoformat() if date else 'Unknown',
                     'size': _size(item.get('size_bytes')), 'active': item.get('is_active')})
    excluded = sum(item.get('is_active') is True for item in report['matching_sessions'])
    message = ('Choose one or more sessions; dates and sizes do not reveal their contents.' if rows
               else 'No matching historical sessions are available in this search.')
    if len(choices) > len(rows):
        message += ' Oldest and newest dated matches are shown; ask to see all.' if dated else ' Ask to see all matches.'
    if excluded:
        message += ' The active session is excluded.'
    if any(item.get('is_active') is None for item in choices):
        message += ' Active status is unknown for some sessions.'
    return {'message': message, 'sessions': rows, 'more_matches': len(choices) - len(rows),
            'show_all_option': len(choices) > len(rows), 'active_excluded': bool(excluded),
            'more_to_search': bool(report.get('pagination', {}).get('next_cursor')),
            'search_gaps': bool(report.get('coverage', {}).get('partial')
                or report.get('match_counts', {}).get('unresolved') or report.get('match_counts', {}).get('unsupported')),
            'conversation_read': False}


def _text(value):
    """Select display text conservatively; raw findings remain in diagnostics."""
    text = re.sub(r'^(?:Goal|Decision|Tried|Problem|Next):\s*', '', str(value or '').strip(), flags=re.I)
    if re.search(r'\.jsonl\b|\b[0-9a-f]{7,64}\b|\b(?:EOF|session_ref|approval_id|review_id|records_read|bytes_read|parser_version)\b', text, re.I):
        return ''
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return ' '.join(text.replace('`', '').split()).rstrip('.!?')


def _identity(project):
    docs = sorted(project.get('documentation', []),
                  key=lambda item: not item.get('path', '').lower().split('/')[-1].startswith('readme'))
    name, description = 'Project', ''
    for doc in docs:
        for line in doc.get('excerpt', '').splitlines():
            if line.startswith('# ') and name == 'Project':
                candidate = _text(line[2:])
                if candidate and len(candidate.split()) <= 6:
                    name = candidate
            elif line and not line.startswith(('#', '```', '-', '|')):
                candidate = _text(line)
                sentence = re.split(r'(?<=[.!?])\s+', candidate, maxsplit=1)[0]
                if sentence and len(sentence.split()) <= 18:
                    description = sentence.rstrip('.!?') + '.'
            if description:
                return name, description
    return name, 'Its purpose is unclear from the available documentation.'


def _summary(report):
    project = report.get('current_project', report)
    context = report.get('context', {})
    name, description = _identity(project)
    seen = {re.sub(r'\W+', '', description.casefold())}

    def select(category, limit, words, prefix=''):
        result = []
        for finding in reversed(context.get(category, [])):
            # Suggestions and heuristic classifications are not established decisions.
            if finding.get('kind') != 'historical_statement':
                continue
            text = _text(finding.get('statement'))
            key = re.sub(r'\W+', '', text.casefold())
            rendered = f'{prefix}{text}.'
            cost = len(rendered.split())
            if not text or key in seen or cost > words:
                continue
            result.append(rendered)
            seen.add(key)
            words -= cost
            if len(result) == limit:
                break
        return list(reversed(result))

    decisions = select('decisions', 5, 45, 'Earlier choice: ')
    problems = select('unresolved_problems', 2, 24, 'Previously reported: ')
    where = select('user_goals', 1, 18, 'You previously wanted: ')
    has_goal = bool(where)
    where += select('attempted_fixes', 1, 18, 'You previously tried: ')
    if not where:
        where = select('user_statements', 2, 36, 'You previously said: ')
    changes = bool(project.get('git', {}).get('working_tree'))
    if not where:
        where = ['There are local changes to review.' if changes
                 else 'Your previous stopping point is unclear from the available context.']
    actions = select('next_actions', 3, 45, 'Review the earlier plan: ')
    candidates = []
    if problems:
        candidates.append('Check whether the reported problem still occurs.')
    if changes:
        candidates.append('Review the local changes before editing.')
    if project.get('test_commands'):
        candidates.append('Choose a relevant available test to check the next change.')
    if decisions:
        candidates.append('Confirm which earlier choices should still guide the work.')
    if has_goal:
        candidates.append('Identify which part of the earlier goal is still unfinished.')
    # Ask about concrete gaps when evidence cannot support three implementation tasks.
    candidates += [f'Identify the last unfinished task in {name}.',
                   f'Confirm the intended next outcome for {name}.',
                   f'Choose an acceptance check for the next {name} change.']
    for candidate in candidates:
        if len(actions) == 3:
            break
        key = re.sub(r'\W+', '', candidate.casefold())
        if key not in seen:
            actions.append(candidate)
            seen.add(key)
    result = {'project': {'name': name, 'description': description},
              'where_you_left_off': where, 'previous_decisions': decisions,
              'unresolved': problems, 'next_steps': actions}
    incomplete = (report.get('coverage', {}).get('partial')
                  or ('current_project' in report and not report.get('sessions'))
                  or any(item.get('coverage', {}).get('partial') or not item.get('coverage', {}).get('reached_eof')
                         for item in report.get('sessions', [])))
    if incomplete:
        result['warning'] = ('Some historical context may be missing.' if 'current_project' in report
                             else 'Some project context may be missing.')
    return result


def present(report, *, verbose=False, all_sessions=False):
    if report.get('status') == 'disabled':
        result = {'message': 'Session recovery is off. Project inspection remains available.'}
    elif 'error' in report:
        code = report['error'].get('code', '')
        message = ('The selected session changed. Review fresh metadata and approve again before reading.'
                   if code == 'selected_session_changed_rediscover_and_reapprove'
                   else 'The search location or limits changed. Review the new scope and approve again.'
                   if code == 'metadata_search_scope_changed_renew_approval'
                   else 'The project or session location changed. Review the selection and approve again.'
                   if code == 'approval_project_or_home_changed'
                   else 'The recovery limits changed. Review them and approve again.'
                   if code == 'approval_read_limits_changed'
                   else 'Session access needs explicit approval before continuing.' if 'approval' in code
                   else 'Inspection could not finish. Continue with available file evidence.')
        result = {'message': message}
    elif 'matching_sessions' in report:
        result = _shortlist(report, all_sessions)
    else:
        result = _summary(report)
    if verbose:
        result['diagnostics'] = report
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verbose', '--details', dest='verbose', action='store_true',
                        help='Include private evidence/diagnostics; does not grant additional access.')
    parser.add_argument('--all-sessions', action='store_true', help='Show all already-matched historical choices; no body access.')
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError
        report = json.loads(raw)
        if not isinstance(report, dict):
            raise ValueError
        print(json.dumps(present(report, verbose=args.verbose, all_sessions=args.all_sessions), ensure_ascii=True, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print(json.dumps({'message': 'Expected a bounded scanner JSON report.'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
