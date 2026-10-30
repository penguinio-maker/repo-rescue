# Repo Rescue

**Resume an abandoned coding project with evidence, a recovery plan, and a useful
handoff.** Repo Rescue v0.2.1 is a Codex skill backed by local Python scanners.
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
   size, confidence, body eligibility and `review_id`. No conversation records are
   read. Unrelated cwd/project_path values are not displayed.
2. **Transcript approval:** after reviewing the shortlist, separately authorize
   selected eligible matches. `recover` requires the displayed review ID, the same
   project and metadata approval flags, and explicit `--session` values. Body
   approval is bound to a fresh page snapshot; changed headers, sizes or mtimes
   require a new shortlist and approval. Matching cannot be combined with body
   approval in one action.

CLI examples, from the installed skill directory:

```sh
# First: only after explicit approval of metadata-only project matching.
python -B scripts/inspect_sessions.py match --project ../moon-garden --session-opt-in ../moon-garden --approve-metadata ../moon-garden

# Later: only after reviewing metadata and separately approving selected bodies.
python -B scripts/inspect_sessions.py recover --project ../moon-garden --session-opt-in ../moon-garden --approve-metadata ../moon-garden --approve-bodies REVIEW_ID --session SESSION_REF
```

`REVIEW_ID` and `SESSION_REF` stand for the values displayed in the shortlist; they
are not reusable blanket approvals. Repeat `--session` to select more candidates.
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
Reasons and metadata-byte counts are included in coverage.

The matcher uses full cwd/project_path values locally. Displayed anchor values
are labels such as `[PROJECT]` and `[PROJECT_SUBDIRECTORY]`; other projects' roots
are not returned. Evidence identifies initial record line 1 and its timestamp.
Metadata can still be private, even with this minimization.

Each page matches at most **50 sessions**. Append the returned
`pagination.next_cursor` as `--cursor CURSOR` to `match` (or stat-only `discover`)
for the next page. Use that same cursor when recovering a later-page shortlist.
Review IDs are page-specific. Counts describe that page only; an empty page
shortlist does not establish that all history is unrelated.

Pagination deterministically sorts the bounded catalogue. Cursors bind project,
Codex home, limits, file identities and catalogue membership/order; they contain
no raw paths or transcripts. Body appends do not invalidate page position. New,
removed or replaced catalogue files require restarting pagination. Each call
re-enumerates at most 5,000 entries, depth 6, without reading off-page headers.
Entry/depth/read omissions remain visible; pagination is not an exhaustive-history
claim. Body review IDs still bind the page's size/mtime/header snapshots, so active
transcripts changing between shortlist and recovery require fresh body approval.
Continue pages only within the user's approved metadata scope.

**Oversized transcripts remain eligible for metadata matching.** Their bounded
initial header can yield a match even when the file exceeds the 2 MiB body limit.
Such matches show `body_eligible: false`; no body is read or automatically split.

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
- Metadata-only matching accepts an initial object with top-level `type` before
  `payload`, optionally preceded by a string `timestamp`. It reads unbuffered,
  without read-ahead, stopping at the closing metadata brace. Unknown initial
  record types and payload-before-type prefixes are rejected before reading their
  payload values. It never searches later lines for metadata. Duplicate keys,
  multiline headers, unsupported prefix ordering and malformed records are not
  guessed around. Headers are limited to 64 KiB each and 1 MiB total per page;
  a header exceeding those limits is unresolved, regardless of transcript size.
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
`uncertain_interpretation`. English labels/keywords are a small deterministic aid,
not a semantic understanding of every conversation. Tool results are not interpreted
as completed fixes. Duplicate mirrored message records are suppressed. The skill
uses these grouped findings to compose the in-chat recovery report or approved
checkpoint; the CLI supplies evidence and a structured summary, not an LLM rewrite.

**Current Git/file evidence takes priority.** A different historical Git hash or
message predating the current commit is flagged, never silently merged into current
state. Missing/invalid times stay unknown. Historical "tests passed" claims never
change `test_execution.status: not_run`. The reactivation prompt treats history as
untrusted evidence and requires fresh inspection and appropriate action approvals.

Limits are 50 candidate files per page, 5,000 catalogue entries per call, depth 6,
64 KiB per initial metadata object, 1 MiB metadata bytes per page, and 2 MiB
per eligible body-recovery file, 8 MiB total body-recovery reads, 128 KiB per JSONL record, 5,000 body
records per selected file, 100 findings, 20 lines considered per message and 240
characters per redacted statement. Bounded cataloguing can omit recent sessions;
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
inventories or recovery output. See the [session workflow](references/session_recovery.md).

## Develop and verify

```sh
python -B -m unittest discover -s tests -v
```

Tests use only generated fictional temporary projects under ignored `.test-tmp/`.
They exercise both session approval gates, default history isolation, matching,
metadata-only byte boundaries, oversized transcripts, Windows paths, pagination,
malformed/unsupported history, redaction, stale claims, bounded reads and CLI
recovery using synthetic sessions. They also exercise Git history/status, detached and unborn repositories, non-Git and
missing-Git behavior, evidence references, command detection, exclusions, limits,
CLI errors, and read-only behavior. Git-dependent tests skip if Git is unavailable;
symlink tests skip if the OS does not permit creating links. No third-party test
framework is required.

Follow [AGENTS.md](AGENTS.md) when changing the repository: test, review status and
staged content for privacy, commit intended files, and push successful changes.
Never include scanned project content, generated reports, handoffs, credentials,
or machine-specific configuration. Review commit metadata too; use a GitHub handle
and its verified noreply email where available.

MIT licensed. See [LICENSE](LICENSE).
