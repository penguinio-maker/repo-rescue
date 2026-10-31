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

1. Asks to search local session **metadata only**, explaining where and how much.
2. Shows a few matching sessions by date, size and project-match confidence.
3. Separately asks which exact conversations you approve reading.
4. Combines approved historical statements with current files in the recovery report.

No hashes, terminal flags or pagination knowledge are needed. Declining session
access still gives you a useful file/Git report. Asking about session recovery does
not approve transcript reading. Approval covers only your selected sessions;
changed selected files require fresh review and approval.

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
