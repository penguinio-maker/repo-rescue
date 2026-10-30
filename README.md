# Repo Rescue

**Resume an abandoned coding project with evidence, a recovery plan, and a useful
handoff.** Repo Rescue v0.1.1 is a Codex skill backed by a local Python scanner.
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
submodule contents are outside v0.1. A shallow history may be incomplete. Recent
commits are the selected HEAD history, not all branches. File modification times
can reflect extraction or tooling rather than the developer's last action.

No dependency resolution, code correctness audit, session-history parsing, or
automatic repair is included. Optional Codex session recovery is planned for a
later version and requires a separate privacy design.

## Develop and verify

```sh
python -B -m unittest discover -s tests -v
```

Tests use only generated fictional temporary projects under ignored `.test-tmp/`.
They exercise Git history/status, detached and unborn repositories, non-Git and
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
