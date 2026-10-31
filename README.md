# Repo Rescue

Pick up an unfinished coding project with a clear next step.

**Public beta v0.2.7.** Repo Rescue is a local Codex skill. It reads project files
and Git history, optionally adds context from approved past Codex sessions, and
gives you a short recovery report. No cloud backend or pip dependencies.

## Install and use

You need Codex, Python 3.11+ and Git for installation. The inspected project does
not need Git. Already installed? See [Update](#update).

1. Run this in a terminal (macOS/Linux or PowerShell):

```sh
git clone https://github.com/penguinio-maker/repo-rescue.git "$HOME/.codex/skills/repo-rescue"
```

2. Open your unfinished project's folder in Codex and start a new chat.
3. Paste this, with `'.'` explicitly selecting that project folder:

```text
Use $repo-rescue to rescue the project at '.'.
```

For another folder, replace `'.'` with its quoted path. With a custom `CODEX_HOME`,
install in its `skills/repo-rescue` folder instead of the default above.

You get a short report: the project, where you left off, previous decisions,
meaningful unresolved problems and **three practical next steps**. Evidence stays
available through details. The normal report aims for fewer than 200 words.
Unknowns stay unknown. Nothing is installed, tested or edited by a rescue request.

For example, with fictional project context:

> **Tiny Harbor** — A small fishing game about building a harbor.
>
> **Where you left off**
> You planned timing-based fishing. The recovered context does not establish
> whether it was implemented.
>
> **Previous decisions**
> - A seven-minute day/night cycle.
> - A maximum of three boats.
>
> **Unresolved**
> Boats were reported to disappear after reloading.
>
> **Next steps**
> 1. Reproduce the reload problem with a saved boat.
> 2. Check how saved boats are restored.
> 3. Verify that a fix keeps boats across a reload.

If recovery is partial, the report adds just: “Some historical context may be missing.”

## Optional past-session context

```text
Use $repo-rescue to rescue '.' with optional past Codex session context.
```

The skill first inspects the project, then:

1. Asks **once** to search local session metadata for this project across all batches,
   explaining locations and the total budget. Conversations stay unread.
2. Searches within that approval automatically and shows matching historical sessions.
3. Asks **once more** to read your exact selection: one session or several named together.
4. Combines approved historical statements with current files in the recovery report.

No hashes, terminal flags or pagination knowledge are needed. Declining session
access still gives you a useful file/Git report. Asking about session recovery does
not approve transcript reading. Approval covers only your selected sessions;
changed selected files require fresh review and approval.

The shortlist shows **all matches up to ten**. With more, it includes both the
oldest and newest sessions and offers “show all.” Each numbered row contains only
an approximate date, size and active status. Dates and sizes cannot tell us what
was discussed or which session is useful; no conversation is read to rank choices.
The current active session is excluded when identified by host/header metadata.
If that identity is unavailable, the status is shown as unknown so you can choose
sessions you know are historical. “Show all” keeps known active sessions excluded
and does not read bodies or restart discovery. You can approve several choices
together, such as “Read sessions 1, 4 and 7.”

There is no extra skill-level confirmation to run the ordinary read-only scanner.
Codex may still require host permission prompts; Repo Rescue never bypasses them.
Metadata search covers up to 500 sessions in one directory snapshot, 1 MiB per
header and **8 MiB total across all batches**, with a cooperative 30-second budget.
The inventory itself is capped at 5,000 entries and six directory levels. It stops
at those bounds; it never silently restarts or adds newly appearing sessions.
Changing the project, history location or budgets requires renewed consent.
Body access remains a separate approval, up to 50 named sessions, 8 MiB each and
16 MiB total per recovery. No approval tokens are saved.

Past requests and replies may contain private code, personal details or business
context. Metadata and redacted excerpts may be processed remotely by the Codex
model. The local scripts make no network requests or automatic uploads, and save
no transcripts or reports. Local scanning does not mean offline model processing.

## Save a handoff

```text
Use $repo-rescue to checkpoint '.'.
```

Codex previews the exact Markdown destination and full handoff, including a
reactivation prompt, then asks before writing. No automatic overwrite, commit or
publication. Reading session context does not grant permission to save a handoff.

## More detail when you need it

```text
Use $repo-rescue to rescue '.' in verbose mode.
```

You can also ask “show details.” Details add source references, confidence,
coverage, limits and diagnostic reasons without cluttering the normal report.
It never grants additional access or bypasses approvals. Internal approval tokens
can contain private metadata; keep diagnostic output local.

For CLI users, existing scanners still return their full JSON contract. A separate
read-only presenter accepts already-collected JSON on stdin and returns a compact
view; `--verbose` (or `--details`) includes the original evidence and diagnostics.
For a matching-session report, `--all-sessions` expands only the safe metadata
shortlist. Numbering stays stable and technical identifiers remain hidden.
It does not scan, recover,
write files or execute anything. Codex composes the final prose from the evidence.

## Beta limits

- Inspection is scoped, not a complete audit. Secrets, `.env` files, credentials,
  dependency trees, links and large/binary files are excluded.
- Session search uses structured project-path evidence. Renamed/moved projects or
  unsupported formats may not match; the skill does not guess from message text.
- Recovery streams a bounded chronological prefix. Unsupported records, scope
  changes, size/text/time limits or active-file changes can leave context incomplete.
  It reads from the beginning, so the latest messages may be missing. Unsupported
  or unsafe records stop recovery; the skill does not silently skip unknown content
  or increase limits. The report must explain meaningful gaps. Old “tests passed”
  claims are not current tests.
- Redaction is best effort. Reports may still contain private context. Keep them local.
- The synthetic Tiny Harbor regression recovers four known facts with source
  evidence. Synthetic tests do not establish compatibility with every real recording.

Details: [session access and limits](references/session_recovery.md),
[format compatibility](references/transcript_compatibility.md),
[scanner/CLI technical guide](references/technical-guide.md).

## Update

```sh
git -C "$HOME/.codex/skills/repo-rescue" pull --ff-only
```

Use your custom installation path if applicable, then start a new Codex chat.

## Development

```sh
python -B -m unittest discover -s tests -v
```

Use generated synthetic fixtures only; never inspect real history during development.
Follow [AGENTS.md](AGENTS.md): test, privacy-review, commit intended source changes
and push successful checks. MIT licensed; see [LICENSE](LICENSE).
