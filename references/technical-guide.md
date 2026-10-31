# Repo Rescue technical guide

Advanced CLI/schema reference. For normal use, start with [README.md](../README.md)
and follow the consent and presentation flow in [SKILL.md](../SKILL.md). Raw JSON,
approval tokens, cursor mechanics and diagnostic tables below are backend details;
they need not be shown during ordinary recovery. The v0.2.7 beta adds presentation
only; the v0.2.6 session adapter and parser contract are unchanged.

**Resume an abandoned coding project with evidence, a recovery plan, and a useful
handoff.** Repo Rescue v0.2.7 is a Codex skill backed by local Python scanners.
It has no website, service, telemetry, or runtime dependencies beyond Python and
optional Git.

## Install

Requires **Python 3.11+**. Install Git to include local history. Clone the public
repository into a skill directory named `repo-rescue`:

```sh
git clone https://github.com/penguinio-maker/repo-rescue.git ~/.codex/skills/repo-rescue
```

PowerShell:

```powershell
git clone https://github.com/penguinio-maker/repo-rescue.git "$HOME/.codex/skills/repo-rescue"
```

If `CODEX_HOME` is customized, use its `skills/repo-rescue` directory instead.
Start a new Codex session and invoke `$repo-rescue`. No pip install is needed.
Installing or cloning the skill writes the chosen installation directory;
inspecting a project does not.

## Use in Codex

Always provide the project path explicitly. These examples use a fictional project:

```text
Use $repo-rescue to rescue the project at ./examples/moon-garden.
Explain what is confirmed, what is uncertain, and the next 3-7 actions.
```

```text
Use $repo-rescue to checkpoint ./examples/moon-garden.
Prepare a handoff and reactivation prompt. Show me the destination and complete
document, and ask before writing it.
```

The example project is illustrative and is not bundled. Relative project paths
resolve from the command's current directory. Quote paths containing spaces.

**rescue** inspects and returns an in-chat report: apparent purpose, branch/HEAD,
recent activity, working changes, documentation, markers, test candidates, gaps,
and 3-7 ordered actions. Every concrete claim should cite scanner evidence.

**checkpoint** prepares a Markdown handoff with current state, known problems and
unknowns, evidence-backed decisions, validation status, next steps, and a
reactivation prompt. Codex must preview the destination and full document, then
obtain approval for that write. It does not automatically commit or upload it.
The scanner itself has no write mode. Workflow reports are composed by Codex;
the standalone CLI produces evidence JSON only.

## Standalone scanner

From the installed skill directory:

```sh
python -B scripts/inspect_project.py --project ../moon-garden
python -B scripts/inspect_project.py --project ../moon-garden --commits 5
python -B scripts/inspect_project.py --help
python -B scripts/inspect_project.py --version
```

JSON goes to stdout. Exit **0** means the scan completed; inspect `warnings` and
`coverage` for gaps. Exit **2** returns a JSON error for invalid arguments,
excluded project roots, or inaccessible paths. `--help` and `--version` return
plain text. `--commits` accepts 1-30 (default 10). No shell or project command is
executed. Git calls have a 10-second timeout and a 1 MiB output limit per call.

The JSON contract uses `schema_version: "1.0"` and includes:

| Field | Meaning |
| --- | --- |
| `git` | State, branch, HEAD, recent commit hashes/dates/subjects, scoped status, recently committed paths |
| `recently_modified_files` | Up to 30 eligible text files ordered by filesystem mtime |
| `documentation` | Up to 30 documents with bounded excerpts, including README and docs |
| `markers` | Up to 200 observed TODO/FIXME lines with file and line references |
| `test_commands` | Argument arrays, relative working directory, certainty, rationale, evidence; always `executed: false` |
| `test_execution` | Always `status: "not_run"` |
| `hypotheses` | Explicit inferences that require verification |
| `evidence` | IDs referenced by findings; relative file/line or Git command/hash sources |
| `coverage`, `warnings` | Intentional/heuristic exclusions, read failures, truncation reasons, counts, limits and diagnostic codes |

For example, a fictional finding might be:

```json
{
  "argv": ["npm", "run", "test"],
  "cwd": ".",
  "certainty": "confirmed",
  "reason": "package.json script 'test' is configured; implementation not executed",
  "executed": false,
  "evidence": ["e4"]
}
```

`confirmed` means an observation was made. It does not certify that a README is
correct, a marker describes a defect, or a command is safe, installed, or passing.
Never infer a passing test run from this output.

Test discovery recognizes npm `test`/`test:*` scripts, Make `test` targets, pytest
configuration, Python `test_*.py` filenames, Cargo manifests, and Go modules.
Python filenames, pytest configuration, Cargo, and Go commands are hypotheses;
they do not establish runner availability or test compatibility. Package scripts
and Make targets are confirmed declarations only. Dependencies are never installed.
Each command carries its own working directory for nested packages.

README files also supply **unverified candidates** from simple command lines or
inline code: Python unittest/pytest invocations, pytest, package-manager test
scripts, Make test targets, Cargo and Go tests. These carry `origin: documentation`,
`certainty: hypothesis`, `verification: unverified`, the exact `source_text`, and
file/line/column evidence (columns are one-based, with an inclusive `end_column`).
Repeated mentions retain each source reference. A documentation candidate does not
replace a configured-command finding. Its working directory is inferred from the
README directory and marked `cwd_certainty: hypothesis`; documentation may describe
another directory or environment. No candidate is executed.

This is deliberately limited discovery: shell chains, redirects, multiline
continuations, complex shell syntax and snippets containing redacted sensitive
values are skipped. The scanner does not interpret README instructions as shell
programs. Review a candidate before authorizing execution.

Coverage is scoped, never a claim that the entire project was scanned:

- `exclusions.intentional`: policy exclusions such as sensitive paths, dependency
  directories, unsupported file types, links and nested repositories. Counts do
  not expose excluded filenames or contents.
- `exclusions.heuristic`: content-based omissions such as key-header matches,
  disguised binaries and non-UTF-8 text. These can include false positives.
- `read_failures`: files or directory entries that could not be read.
- `truncation`: whether resource or result limits were hit, with reasons including
  large files, depth, entry/file/byte budgets and capped result lists.
  `scan_limits` separates those read/query limits from `result_limits`, such as
  shortened documentation excerpts and capped command references. A README can
  be fully read for command discovery while its displayed excerpt is shortened.
- `partial`: operational warnings, heuristic gaps or truncation were detected.
  **False does not mean complete**; intentional exclusions can still exist.
  `complete_project_scan` is always false. Inspect Git's own scoped status and
  excluded-entry count separately before describing the working tree as clean.

The original `skipped` counts remain available for compatibility. Documentation
excerpts remain bounded even when command discovery examines later README lines.

## Safety and privacy

- Scanner operations are read-only: bounded UTF-8 file reads and Git metadata
  queries. No deletion, reset, clean, commit, hooks, project imports, or automatic
  test execution. Git filesystem-monitor helpers and optional index writes are
  disabled. Ambient Git repository overrides and global/system Git config are
  ignored. Configured Git clean/process/smudge filters are disabled in-memory
  before status checks; local repository metadata still must be trustworthy.
- Sensitive names are excluded even when tracked: `.env` and `.env.*`, credentials,
  secret/token/password files, private keys, common credential configuration, local
  reports/handoffs, and session directories. Symlinks, Windows reparse points,
  nested repositories and submodule contents are skipped.
- Dependency/build trees such as `node_modules`, `vendor`, virtual environments,
  `target`, and `dist` are excluded. Only allowlisted text extensions/names are
  read. NUL-containing, non-UTF-8 and control-character text is discarded; embedded
  syntactically valid PEM-style private-key headers cause the entire file to be
  omitted, even in examples. Header matching allows uppercase alphanumeric label
  words, so a quoted source concatenation is not mistaken for a key. This remains
  a conservative heuristic, not key validation. Detecting disguised
  binaries or embedded keys requires reading a bounded candidate file first.
- Files are limited to 128 KiB each; reads to 8 MiB total, 2,000 candidate files,
  20,000 directory entries and depth 12. Limits and unreadable entries are reported.
  Traversal order can affect which files are included when limits are reached.
- Git status is restricted to eligible, successfully scanned text paths (and
  eligible deleted paths). It does not ask Git to hash excluded contents. A clean
  flag is `null` when excluded entries prevent a clean-tree conclusion. Status
  and changed-path lists are capped at 200. Git history reads metadata, never
  historical file blobs, remote URLs, author names, or author emails.
- No network requests or automatic uploads. File references are relative to the
  explicit project; root paths are omitted. Common token, email and home-path
  patterns in excerpts are redacted as a best effort. Ordinary URL spans are
  preserved by local-path masking; secret values and URL credentials are still
  redacted. **Output can still contain
  private code, business context, branch names or commit subjects. Keep it local
  and review before sharing.** Using a Codex model follows that environment's
  data handling; the skill does not make model processing offline.

## Limitations

This is an evidence collector, not a sandbox or exhaustive secret detector. Do not
use it against actively hostile or concurrently changing filesystems. Symlink and
file checks do not eliminate every race or hard-link case. Git and the operating
system may read their own configuration and metadata. Read access can update
filesystem access times. Ignored files are still scanned if eligible and not
explicitly excluded; Git ignore rules alone are not a privacy boundary.

Git is optional. Non-Git folders, empty repositories, detached HEAD, missing Git
and failed queries yield file evidence with explicit state/warnings. For a
subdirectory of a repository, file scanning stays within that path and Git history
is omitted; pass the worktree root to inspect Git. Bare repositories and Git
submodule contents are outside the current scope. A shallow history may be incomplete. Recent
commits are the selected HEAD history, not all branches. File modification times
can reflect extraction or tooling rather than the developer's last action.

No dependency resolution, code correctness audit or automatic repair is included.
Optional local session recovery is separate from the default scanner and follows
the two approval gates below. The original scanner command and JSON schema remain
compatible; no history is discovered, imported or read by default.

## Optional Codex Session Recovery and Smart Discovery

Session recovery is **off by default**, including for checkpoint. To request it:

```text
Use $repo-rescue to rescue ./examples/moon-garden with optional local Codex
session recovery. I approve bounded initial session_meta matching for this
project. Show matching references, dates, sizes and confidence before asking
separately to read selected transcript bodies.
```

The project here is fictional. This request authorizes initial metadata matching only.
The skill still asks separately about selected conversation bodies after showing
the matching shortlist. A request to implement or test this feature never authorizes reading
real developer history. All development tests use generated synthetic files.

`scripts/inspect_sessions.py` is a separate standard-library module. It never
changes a project, writes reports, imports session code or makes network requests.
The ordinary `scripts/inspect_project.py` does not invoke or import it.

1. **Metadata approval:** after explaining the locations, bounds and possible
   remote model processing, obtain explicit approval for this project's initial
   metadata records. `match` requires both `--session-opt-in` and
   `--approve-metadata`, each naming the same explicit project. It returns a
   matching shortlist with `session_ref`, relative path, start/modification dates,
   size, confidence, body eligibility and per-session `approval_id`. No conversation records are
   read. Unrelated cwd/project_path values are not displayed.
2. **Transcript approval:** after reviewing the shortlist, separately authorize
   each selected eligible match. `recover` requires its displayed approval ID, the same
   project and metadata approval flags, and explicit `--session` values. Body
   approval is bound to that session's reviewed snapshot; changed headers, sizes or mtimes
   require a new shortlist and approval. Matching cannot be combined with body
   approval in one action.

CLI examples, from the installed skill directory:

```sh
# First: only after explicit approval of metadata-only project matching.
python -B scripts/inspect_sessions.py match --project ../moon-garden --session-opt-in ../moon-garden --approve-metadata ../moon-garden

# Later: only after reviewing metadata and separately approving selected bodies.
python -B scripts/inspect_sessions.py recover --project ../moon-garden --session-opt-in ../moon-garden --approve-metadata ../moon-garden --approve-bodies APPROVAL_ID --session SESSION_REF
```

`APPROVAL_ID` and `SESSION_REF` are the values for one selected session, not blanket
approvals. Repeat both `--approve-bodies` and `--session` for separately approved
sessions, including sessions discovered on different pages. The `review_id` field
remains a compatibility bundle of independent entries; only explicitly selected
entries are validated. v0.2.4 page hashes are not accepted by this release.
All session commands accept `--codex-home <selected-directory>` for a user-selected home.
Otherwise they use an absolute `CODEX_HOME` or `~/.codex`; no other profiles, drives
or home directories are searched. Supplying only `--project` to this module
returns `status: disabled`, without detecting history locations. Exit 0 indicates
a completed operation, not complete coverage; exit 2 returns a sanitized JSON error.

The original `discover --project ... --session-opt-in ...` action remains a
**stat-only** inventory: it never opens headers or bodies, and `project_match`
remains `not_read`. The v0.2 stat-only discovery/body-recovery CLI remains compatible,
including its existing separate body approval. Normal skill use now follows
metadata approval → matching shortlist → transcript approval → context recovery.
Do not switch to legacy body recovery to bypass a metadata refusal or missing
approval.

These flags assert operator consent; software cannot prove a human approved them.
The skill instructions enforce the separate conversational gates. No consent cache,
inventory file or transcript copy is saved. Output is intended for local in-memory
use; do not redirect it into a repository, report, debug log or upload.

### Matching confidence and bounded pages

`match_counts` reports **matched, unmatched, unresolved and unsupported** counts
for the current page. `matching_sessions` contains only matches. Exact normalized
cwd matches receive `confidence: high`. Descendant cwd matches receive `medium`,
or `high` when reinforced by an exact `project_path`. Confidence describes declared
path association, not authenticity, current behavior or recovered goals. Valid
conflicting anchors are unmatched; missing/relative/invalid anchors and read/byte
limits are unresolved. Malformed or unsupported initial records are unsupported.
Reasons and metadata-byte counts are included in coverage. In particular:

| `match_reason` | Meaning |
| --- | --- |
| `metadata_header_oversized` | The first record exceeded its 1 MiB budget; unresolved. |
| `metadata_batch_byte_limit` | The page exhausted its 8 MiB metadata budget; unresolved. |
| `truncated_metadata` | EOF before the first metadata record was complete. |
| `malformed_initial_metadata` | Invalid JSON/schema, duplicates, depth or line structure. |
| `malformed_metadata_encoding` | Invalid UTF-8/BOM or lone escaped Unicode surrogate. |
| `unsupported_metadata_encoding` | Unsupported encoding, such as UTF-16/32. |
| `unsupported_initial_format` / `unsupported_initial_record` | Non-object format or a first record other than session metadata. |
| `unsupported_metadata_field` / `unsupported_untyped_metadata_payload` | Unknown envelope field or payload before type; refused before its value. |

Malformed/truncated/unsupported records contribute to the unsupported count but
retain their distinct reasons. Nothing falls back to reading later records.

The matcher uses full cwd/project_path values locally. Displayed anchor values
are labels such as `[PROJECT]` and `[PROJECT_SUBDIRECTORY]`; other projects' roots
are not returned. Evidence identifies initial record line 1 and its timestamp.
Metadata can still be private, even with this minimization.

Each page matches at most **50 sessions**. Append the returned
`pagination.next_cursor` as `--cursor CURSOR` to `match` (or stat-only `discover`)
for the next page. Recovery does not replay pagination: omit its cursor; an old
`--cursor` is accepted but ignored by recovery. Counts describe that page only; an empty page
shortlist does not establish that all history is unrelated.

Pagination deterministically sorts the bounded catalogue. Cursors bind project,
Codex home, limits, file identities and catalogue membership/order; they contain
no raw paths or transcripts. Body appends do not invalidate page position. New,
removed or replaced catalogue files require restarting pagination. Each call
re-enumerates at most 5,000 entries, depth 6, without reading off-page headers.
Entry/depth/read omissions remain visible; pagination is not an exhaustive-history
claim. Body approval IDs bind each selected file's identity, path, size/mtime and
reviewed metadata; unrelated catalogue changes do not invalidate them. Selected
transcripts changing between shortlist and recovery require fresh body approval.
Continue pages only within the user's approved metadata scope.

**Large transcripts support separately approved bounded streaming recovery.**
File size no longer disqualifies a regular candidate. `body_eligible: true` means
eligible for the bounded reader, not approved or guaranteed complete. Shortlists
show `recovery_mode: bounded_stream`, `body_read_budget_bytes` and
`body_may_be_truncated`. The metadata approval still reads only initial headers.
Each transcript body needs explicit selection and approval after the shortlist.
Review IDs and cursors bind the new limits, so upgrades require a fresh shortlist
and body approval. Earlier small-file approvals do not authorize larger reads.

### Bounded large-session recovery

v0.2.5 approval validation is independent of discovery membership, page size,
cursor, ordering and unrelated timestamps. Tokens bind the resolved project and
Codex-home paths and directory identities (as digests), selected relative path and
session reference, device/file identity, size/mtime, metadata digest/project-match
evidence, adapter version and read limits. Recovery opens only selected headers
for revalidation; aggregate metadata/body budgets remain bounded. A replaced
project directory or Codex home, replay against another session, or changed read
limits is rejected. Selected-file growth is rejected under the strict snapshot
policy, even if only an append occurred.

`selected_session_changed_rediscover_and_reapprove` names the affected `session_ref`
and a reason: `grown`, `modified`, `replaced`, `missing_or_unavailable`, or
`metadata_or_project_match_changed`. Scope/limit changes have separate
`approval_project_or_home_changed` / `approval_read_limits_changed` errors. No
body is read when preflight fails. Changes during streaming still discard findings.

Tokens are bounded base64 JSON, not encrypted, signed or authenticated. They contain
relative history filenames and private metadata digests; do not publish or persist
them. Flags still assert operator consent, enforced conversationally by the skill.
Stat-only legacy approvals bind the reviewed `not_read` association and snapshot;
they cannot attest unread headers. Normal recovery requires metadata matching and
its separate body approval, which binds the reviewed header and project match.
Snapshots do not authenticate same-size body edits with restored timestamps;
metadata digests cover headers only. Actively hostile filesystems remain out of scope.

The reader processes one JSONL record at a time from the beginning, without
collecting the transcript or reading ahead past record boundaries. It can recover
a multi-megabyte file while holding only bounded record/metadata objects and
bounded extracted findings. No raw transcript, continuation file, cache or log is
written. No discovered instruction or command is executed.

Body limits must be explained before approval:

| Limit | Default per recovery call unless specified |
| --- | --- |
| Bytes read per selected file | 8 MiB, including the initial header |
| Total bytes read across selected files | 16 MiB, including selected headers |
| Record size | 1 MiB for the header; 128 KiB for later records |
| Body records | 5,000 per selected file |
| Eligible message text | 16 Ki characters per message; larger messages omitted whole |
| Eligible text considered | 256 Ki characters total |
| Extracted text | 16 Ki characters total, 100 findings maximum |
| Finding excerpts | First 20 message lines; 240 characters per statement |
| Processing time | Cooperative 30-second body-processing deadline |

The timer starts after metadata revalidation and the current file/Git scan. Checks
occur before/after record reads and during processing. Blocking filesystem reads
cannot be interrupted by this timer; it is not a hard whole-command timeout.
If any global budget is exhausted, remaining selected files are reported as
`not_read_budget_exhausted`; limits do not reset per file. The per-file byte budget
limits reads, not eligibility. Files larger than the budget can yield a prefix.

Malformed JSON, duplicate keys, invalid UTF-8, oversized records, unknown record
types and project boundaries stop that file. The reader never skips a damaged or
huge record, since it could hide a `turn_context` or new session. Known tool outputs,
reasoning and system messages within supported envelopes are ignored as evidence.
The explicitly recognized `world_state` subset below is skipped as comparison
metadata. It consumes the same record, byte and time budgets.
An oversized known message is omitted whole, with its omission reported. Redaction
precedes excerpt truncation; sensitive values are not sliced before masking.

Each `sessions[].coverage` reports `source_size_bytes`, `bytes_read`, `unread_bytes`,
`records_read`, `reached_eof`, `stop_reason`, `truncated`, `partial`, text counts and
omissions. `eof` means the selected snapshot's byte range was consumed; it does not
mean every record produced context. A prefix has an explicit byte/record/time/text
stop reason. Changed files lose all recovered findings. Global coverage summarizes
partial/truncated sessions and keeps `complete: false`. Text/snippet exclusions can
make `partial: true` even at EOF. Extraction-budget counts include discarded work;
`extracted_chars` counts returned statements only.

Recovery is chronological and can miss recent goals or reversals beyond the
prefix. Explain these gaps in the resume summary and reactivation prompt; never
claim full recovery, silently seek to the tail, raise limits, retry automatically,
or persist raw history. Current Git/file evidence continues to take priority.

### Transcript compatibility audit (v0.2.6)

The audit found two independent defects: the old world-state section allowlist
confused structural compatibility with knowledge of metadata semantics; extraction
also silently lost user statements lacking English labels or keywords. The
[compatibility matrix](transcript_compatibility.md) enumerates supported
and rejected envelopes and remaining gaps.

`scripts/transcript_records.py` owns envelope dispatch and metadata structure
validation. `RecordReader` owns bounded JSONL decoding; separate project-anchor
checks own isolation; `message` normalizes supported conversation content, and
`extract` classifies redacted statements. Semantic classification never decides
whether a metadata envelope can be safely skipped.

### Extensible world-state metadata

The public Codex [wire envelope](https://github.com/openai/codex/blob/main/codex-rs/history/src/rollout_payload.rs)
and [WorldStateItem definition](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs)
describe `type: world_state` with `payload: {full: boolean, state: object}`.
This adapter validates the envelope separately from opaque section contents:

- The envelope contains only `type`, a valid timezone-aware `timestamp`, `payload`
  and optional unsigned 64-bit `ordinal` (or null).
- Payload contains exactly `full` and `state`. Section names are extensible, and
  section values may be any valid bounded JSON, including arrays, strings, scalars
  and null. Empty states and full/patch snapshots are supported. Opaque sections
  are never interpreted as messages, commands or permission to widen project scope.
- An `environments` update must explicitly carry a nonempty `environments` map,
  with an in-project `cwd` on every entry. Null removals or partial environment
  patches without cwd stop recovery. This adapter does not reconstruct merge patches.
- The single-environment shape `environment: {cwd: ...}` is also checked; unknown
  or removed environment anchors stop rather than inheriting an assumed path.
- All nested `cwd` and `project_path` anchors are checked lexically. A conflicting,
  invalid or removed anchor stops with `cross_project_or_unknown_world_state`.
- Unknown envelope/payload fields and structures beyond 4,096 visited values or
  depth 64 stop with `unsupported_world_state`. Existing JSON/record limits still
  apply first. Other unknown record types still stop with `unsupported_record`.

Recognized records increment `recognized_world_state_skipped` in coverage. No
world-state content becomes a goal, decision, historical claim, prompt instruction
or returned excerpt. Metadata text is never executed. Byte/record/time accounting
is unchanged; evidence for subsequent messages retains its original JSONL line
and timestamp. This does not authenticate metadata or expand a project's scope.

Session adapter version is bound into review IDs/cursors, so upgrading requires a
fresh metadata shortlist and separate approval for each selected body. No recovery
is retried automatically. Tests use generated fixtures only; compatibility with a
particular private recording remains unverified until separately approved recovery.

### Locations and format boundary

OpenAI documents local state under `CODEX_HOME` (default `~/.codex`) and optional
history persistence. See [official configuration documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#config-and-state-locations).
This module implements a deliberately narrow rollout compatibility adapter, not
a guarantee of a stable public transcript API or all Codex desktop/CLI versions.

- Inventory only `sessions/` and `archived_sessions/`, recursively within limits,
  for regular `rollout-*.jsonl` or `session-*.jsonl` files. Symlinks, junctions,
  reparse points, unsupported names and sensitive filenames are skipped.
- Support UTF-8, one-object-per-line typed rollouts beginning with
  `type: session_meta` and `payload.cwd`. Optional `payload.project_path` must not
  conflict; `payload.git.commit_hash` provides a historical revision signal.
- Metadata-only matching accepts the Codex envelope's string `timestamp`, optional
  unsigned 64-bit `ordinal`, `type: session_meta` and object `payload`. Timestamp
  and ordinal may appear before or after type; type must precede payload. Older
  records without ordinal remain supported. UTF-8 with or without an initial BOM,
  escaped Unicode, LF/CRLF and a final record ending at EOF are supported.
- The first-record reader reads unbuffered, one byte at a time through the record's
  line terminator or EOF, rather than a fixed prefix. It never reads ahead into
  the next record. Unknown types, unknown envelope fields and payload-before-type
  records are refused before their payload/field values. Metadata payload fields
  such as base instructions and tool definitions are validated within the header
  budget, then discarded; they are never interpreted or returned. It never
  searches later lines. Duplicate keys, multiline headers, malformed JSON,
  invalid UTF-8, lone Unicode surrogates and non-finite numbers are rejected.
- Headers are limited to **1 MiB each and 8 MiB total per page**, counting BOM,
  whitespace and terminators. This is larger than v0.2.1's 64 KiB / 1 MiB bounds:
  disclose the new bounds before approval; previous consent to smaller bounds
  does not authorize larger reads. Oversized headers remain unresolved, even when
  anchors occur early. Metadata matching is not proof of metadata authenticity.
- Read human/assistant text from `response_item` message records (`input_text` or
  `output_text`) and legacy `event_msg` user/agent messages. Ignore system/developer
  messages, reasoning, tool calls/outputs and unknown records. Do not evaluate
  embedded code or commands. Malformed records and unsupported headers are reported.
- `turn_context.payload.cwd` must remain within the selected project. The first
  cross-project or unknown turn boundary stops that session's read. No unrelated
  later bodies are read. Historical path matching is lexical and component-based;
  Windows drives and UNC paths normalize slash/case variants and standard extended
  prefixes. Device, drive-relative, alternate-stream and control-character paths
  are not anchors. POSIX paths remain case-sensitive. Renamed
  projects, different worktrees, relative cwd values and unresolvable associations
  are not guessed from names, remote URLs or conversation text.
- `history.jsonl` is shown as an unsupported location when present, without opening
  it. The generic prompt-history index lacks a supported reliable project anchor.
  SQLite, compressed files, legacy untyped arrays, authentication/configuration
  files and unknown formats are not mined as fallbacks.

### Evidence, summaries and privacy

Recovery returns fresh `current_project` scanner JSON, selected-session statuses,
category-grouped `context`, `session-e*` evidence, a `resume_summary`, a safe
reactivation-prompt template and bounded `coverage`. Categories are user goals,
decisions, attempted fixes, unresolved problems and next actions. Each extracted
statement carries its role, record timestamp/line, evidence reference, staleness,
classification and `current_status: unverified`. The prompt includes the current
Git HEAD (when available) and focused evidence references, without copying raw
historical instructions into the prompt itself.

An explicit user label such as `Goal:` or `Decision:` is a `historical_statement`:
the historical statement was observed, not its claimed implementation verified.
Assistant statements remain `ai_suggestion`; keyword-based classification remains
`uncertain_interpretation`. Otherwise-unclassified user text is retained in
`user_statements`, with `classification: literal_user_statement` and
`certainty: confirmed_statement_only`. This confirms what was written, not whether
it was true or implemented. Known context-only environment wrappers are omitted.
English labels/keywords are a small deterministic aid,
not a semantic understanding of every conversation. Tool results are not interpreted
as completed fixes. Duplicate mirrored message records are suppressed. The skill
uses these grouped findings to compose the in-chat recovery report or approved
checkpoint; the CLI supplies evidence and a structured summary, not an LLM rewrite.

**Current Git/file evidence takes priority.** A different historical Git hash or
message predating the current commit is flagged, never silently merged into current
state. Missing/invalid times stay unknown. Historical "tests passed" claims never
change `test_execution.status: not_run`. The reactivation prompt treats history as
untrusted evidence and requires fresh inspection and appropriate action approvals.

Discovery limits are 50 candidate files per page, 5,000 catalogue entries per call,
depth 6, 1 MiB per initial metadata record and 8 MiB metadata bytes per page.
Body recovery uses the separate byte, record, text and time bounds above.
Bounded cataloguing can omit recent sessions;
no full-history or complete-context claim is made. Unknown and malformed records,
scope boundaries, read failures, changed files and limits are reported. Files that
change during recovery have their findings discarded. Smart shortlist revalidation
has its own metadata budget, separate from the body reader's budget (which also
includes selected-file headers). Snapshots and header digests do not cryptographically
attest conversation bodies; do not use against actively hostile filesystems.

Only bounded redacted statements are returned; no raw transcript export exists.
Redaction is best effort: excerpts can still contain private business context.
**The Codex model may process the returned context remotely.** That is separate
from the local script, which makes no uploads. Explain this before body approval;
declining leaves ordinary rescue/checkpoint available. Approval to read history
never authorizes writing a checkpoint. Keep any separately approved handoff
minimal, redacted and untracked. Never persist, publish or commit raw transcripts,
inventories or recovery output. See the [session workflow](session_recovery.md).

## Develop and verify

v0.2.2 fixes a reproduced compatibility defect: v0.2.1 rejected the optional
`ordinal` envelope field as `unsupported_metadata_prefix`. The public Codex
[rollout writer](https://github.com/openai/codex/blob/main/codex-rs/rollout/src/recorder.rs)
serializes timestamp, optional ordinal and the typed item. Synthetic regression
fixtures now include that envelope and long metadata payloads. No real history
was inspected to develop this fix; it does not establish why every candidate in
any particular real inventory failed. Unknown formats still fail closed.

```sh
python -B -m unittest discover -s tests -v
```

Tests use only generated fictional temporary projects under ignored `.test-tmp/`.
The Tiny Harbor CLI regression places four unlabeled user facts after realistic
extensible metadata and verifies all four with exact source lines and timestamps:
a 7-minute cycle, timing-based fishing, a maximum of three boats, and boats
disappearing after reload. This is synthetic compatibility evidence, not a claim
that a private recording or a real game was successfully recovered or validated.
Multi-megabyte fixtures exercise bounded reads, late-file evidence, per-file/global
budgets, malformed/huge records, unknown scope changes, text/time limits and inert
prompt-injection examples. No real Codex history is inspected during development.
They exercise both session approval gates, default history isolation, matching,
metadata-only byte boundaries, oversized transcripts, Windows paths, pagination,
malformed/unsupported history, redaction, stale claims, bounded reads and CLI
recovery using synthetic sessions. They also exercise Git history/status, detached and unborn repositories, non-Git and
missing-Git behavior, evidence references, command detection, exclusions, limits,
CLI errors, and read-only behavior. Git-dependent tests skip if Git is unavailable;
symlink tests skip if the OS does not permit creating links. No third-party test
framework is required.

Follow [AGENTS.md](../AGENTS.md) when changing the repository: test, review status and
staged content for privacy, commit intended files, and push successful changes.
Never include scanned project content, generated reports, handoffs, credentials,
or machine-specific configuration. Review commit metadata too; use a GitHub handle
and its verified noreply email where available.

MIT licensed. See [LICENSE](../LICENSE).
