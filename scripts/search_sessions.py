#!/usr/bin/env python3
"""One approved, bounded metadata search. No transcript bodies, writes or network."""
import json
from collections import Counter
import os
import sys
import time
import uuid

if __package__:
    from . import inspect_sessions as sessions
else:
    import inspect_sessions as sessions

MAX_SEARCH_FILES = 500
MAX_SEARCH_SECONDS = 30


def _session_id(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


class SelectionMetadataReader(sessions.MetadataReader):
    """Observe an ID in the already-approved header; never read extra records."""
    def __init__(self, active_ids):
        super().__init__()
        self.active_ids = active_ids
        self.is_active = None

    def record(self, source):
        self.is_active = None
        record, digest = super().record(source)
        session_id = _session_id(record['payload'].get('id'))
        if session_id is not None and self.active_ids:
            self.is_active = session_id in self.active_ids
        return record, digest


def search_limits():
    return {"sessions": MAX_SEARCH_FILES, "metadata_bytes": sessions.MAX_METADATA_TOTAL_BYTES,
            "header_bytes": sessions.MAX_METADATA_BYTES, "entries": sessions.MAX_ENTRIES,
            "depth": sessions.MAX_DEPTH, "processing_seconds": MAX_SEARCH_SECONDS,
            "batch_size": sessions.MAX_FILES}


def scope_id(root, home):
    limits = search_limits()
    limits.pop("batch_size")  # Internal paging never broadens the approved aggregate scope.
    return sessions.digest(["metadata-search-v1", sessions.approval_scope(root, home), limits])


def plan_search(project, *, opt_in_project=None, codex_home=None):
    """Describe consent scope; stat known roots only, never enumerate/read sessions."""
    root = sessions.project_consent(project, opt_in_project)
    home, label = sessions.history_home(codex_home)
    return {"status": "metadata_search_approval_required", "project": ".",
            "approval_id": scope_id(root, home), "limits": search_limits(),
            "locations": [f"{label}/sessions", f"{label}/archived_sessions"],
            "bodies_read": False, "headers_read": False,
            "privacy_notice": "Only known directory identities were checked. No session inventory or headers read. "
                              "Private metadata may be processed remotely by Codex. No uploads or persistence."}


def search_metadata(project, *, opt_in_project=None, approval_id=None, codex_home=None, active_session_id=None):
    """Run one bounded search under scoped operator consent; never auto-restart."""
    root = sessions.project_consent(project, opt_in_project)
    if not isinstance(approval_id, str) or not approval_id:
        raise sessions.SessionError("metadata_search_approval_required")
    home, _ = sessions.history_home(codex_home)

    def validate_scope():
        if approval_id != scope_id(root, home):
            raise sessions.SessionError("metadata_search_scope_changed_renew_approval")

    validate_scope()  # Reject changed locations/identities/limits before enumeration.
    if active_session_id is not None and _session_id(active_session_id) is None:
        raise sessions.SessionError('invalid_active_session_id')
    values = ([active_session_id] if active_session_id is not None else
              [os.environ.get('CODEX_THREAD_ID'), os.environ.get('CODEX_SESSION_ID')])
    active_ids = {value for item in values if (value := _session_id(item)) is not None}
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    catalogue = sessions.discover(root, opt_in_project=root, codex_home=home, _catalogue=True)
    validate_scope()
    reader = SelectionMetadataReader(active_ids)  # Shared budget; no extra header/body reads.
    counts = Counter({name: 0 for name in ("matched", "unmatched", "unresolved", "unsupported")})
    reasons = Counter()
    inspected, matches = [], []
    stop = "catalogue_exhausted"
    batches = 0
    candidates = catalogue["candidates"]
    for offset in range(0, min(len(candidates), MAX_SEARCH_FILES), sessions.MAX_FILES):
        if time.monotonic() >= deadline:
            stop = "processing_time_limit"
            break
        batches += 1
        for candidate in candidates[offset:min(offset + sessions.MAX_FILES, MAX_SEARCH_FILES)]:
            validate_scope()
            if time.monotonic() >= deadline:
                stop = "processing_time_limit"
                break
            if reader.bytes_read >= sessions.MAX_METADATA_TOTAL_BYTES:
                stop = "metadata_byte_limit"
                break
            # Reuse the existing first-record reader and matching/identity checks.
            page = sessions.match_metadata(root, opt_in_project=root, metadata_approval_project=root,
                codex_home=home, _inventory={"candidates": [candidate], "coverage": {}}, _reader=reader)
            validate_scope()
            candidate['is_active'] = reader.is_active
            inspected.append(candidate)
            counts.update(page["match_counts"])
            reasons.update(page["coverage"]["matching_reasons"])
            matches.extend(page["matching_sessions"])
            if candidate.get("match_reason") == "metadata_batch_byte_limit":
                stop = "metadata_byte_limit"
                break
        if stop != "catalogue_exhausted":
            break
    if stop == "catalogue_exhausted" and len(inspected) < len(candidates):
        stop = "session_limit"
    if time.monotonic() >= deadline:
        stop = "processing_time_limit"
    omissions = catalogue["coverage"]["omissions"]
    catalogue_gaps = any(omissions.get(reason) for reason in (
        "entry_limit", "depth_limit", "unreadable_entry", "unreadable_directory",
        "unavailable_or_linked_location", "linked_or_changed_entry"))
    # Preserve every confirmed match. Presentation chooses a chronological view,
    # not a content/usefulness ranking based on age, size or confidence.
    return {"schema_version": "1.0", "status": "body_approval_required" if matches else "no_matching_sessions",
            "project": ".", "locations": catalogue["locations"], "candidates": inspected,
            "matching_sessions": matches, "match_counts": dict(counts),
            "bodies_read": False, "metadata_records_only": True,
            "coverage": {"complete": False, "partial": stop != "catalogue_exhausted" or catalogue_gaps,
                "limits": search_limits(), "stop_reason": stop, "batches_processed": batches,
                "metadata_bytes_read": reader.bytes_read, "sessions_inspected": len(inspected),
                "uninspected_sessions": len(candidates) - len(inspected),
                "matching_reasons": dict(reasons), "catalogue": catalogue["coverage"]},
            "privacy_notice": "Only initial metadata records were read. Each selected session needs separate body approval. "
                              "Private metadata may be processed remotely by Codex. No uploads or persistence."}


def main(argv=None):
    try:
        parser = sessions.Parser(description=__doc__)
        parser.add_argument("action", choices=("plan", "search"))
        parser.add_argument("--project", required=True)
        parser.add_argument("--session-opt-in", metavar="PROJECT")
        parser.add_argument("--codex-home")
        parser.add_argument("--approve-search", metavar="SCOPE_ID")
        parser.add_argument('--active-session-id', help='Trusted host current-session ID; defaults to Codex host environment.')
        args = parser.parse_args(argv)
        if args.action == "plan":
            if args.approve_search:
                raise sessions.SessionError("planning_cannot_approve_search")
            result = plan_search(args.project, opt_in_project=args.session_opt_in, codex_home=args.codex_home)
        else:
            result = search_metadata(args.project, opt_in_project=args.session_opt_in,
                                     approval_id=args.approve_search, codex_home=args.codex_home,
                                     active_session_id=args.active_session_id)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except sessions.SessionError as error:
        print(json.dumps({"error": {"code": error.code}, "bodies_read": False}))
        return 2
    except (OSError, RuntimeError):
        print(json.dumps({"error": {"code": "metadata_search_unavailable"}, "bodies_read": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
