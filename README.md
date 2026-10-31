# Repo Rescue

**Your code is still there. The context isn't.**

Come back to a project after weeks away and remember why you made those choices,
what is unfinished, and where to start next.

Repo Rescue is a **Codex skill** for recovering past project decisions and
unfinished work from local files, Git history and—with your permission—past Codex
sessions. It separates historical intentions from what current files actually
establish, then gives you three practical next steps.

[Public beta v0.2.7](https://github.com/penguinio-maker/repo-rescue/releases/tag/v0.2.7)
· Python standard library · Read-only by default · [MIT](LICENSE)

## Install and use

You need **Codex, Python 3.11+ and Git** to install. The project you rescue does
not need Git history. There are no pip dependencies or cloud services to set up.

1. Run this in a terminal (macOS/Linux or PowerShell):

```sh
git clone https://github.com/penguinio-maker/repo-rescue.git "$HOME/.codex/skills/repo-rescue"
```

2. Open your unfinished project's folder in Codex and start a new chat.
3. Paste:

```text
Use $repo-rescue to rescue the project at '.'.
```

The explicit path `'.'` means that project folder. Replace it with a quoted path
to inspect another project. With a custom `CODEX_HOME`, install under its
`skills/repo-rescue` directory instead. Already installed? See [Update](#update).

Basic rescue inspects files and Git only. It does not read conversations, run
project commands or change project files.

## Recover the decisions behind the code

Files show the current state. Past sessions can explain the plan behind it:

```text
Use $repo-rescue to rescue '.' with optional past Codex session context.
```

The standard history workflow has **two skill-level approvals**:

1. Approve a bounded, project-specific metadata search across all available batches.
2. Choose one or several named sessions and separately approve reading their bodies.

You see all matches up to ten; larger lists include oldest and newest choices,
with “show all” available. Dates and sizes do not reveal contents or usefulness.
Known active sessions are excluded; unavailable active status is marked unknown.
Declining history access still gives you the file/Git report. Codex host permission
prompts remain separate and are never bypassed.

## Demo

> **Real screenshot placeholder**
>
> A privacy-reviewed screenshot of a real recovery will go here. No product
> screenshot has been added yet.

Example output using **fictional project context**:

> **Tiny Harbor** — A small fishing game about building a harbor.
>
> **Where you left off**
> You planned timing-based fishing. Implementation is not established by the recovered context.
>
> **Previous decisions**
> A seven-minute day/night cycle; at most three boats.
>
> **Unresolved**
> Boats were reported to disappear after reloading.
>
> **Next steps**
> 1. Reproduce the reload problem with a saved boat.
> 2. Check how saved boats are restored.
> 3. Verify that a fix keeps boats across a reload.

Normal reports aim for fewer than 200 words. Ask **“show details”** for evidence
and confidence. Partial recovery adds: “Some historical context may be missing.”

## Privacy first

- **Read-only by default.** No automatic edits, installs, project tests or commits.
- **Separate consent.** Metadata approval never grants transcript access. Changed
  scope or selected files require renewed approval; tokens are not saved.
- **Local scripts, informed model access.** Scripts make no network calls and do
  not upload or persist transcripts. Approved context may be processed remotely
  by Codex. Redaction is best effort; keep reports private.
- **Sensitive files excluded.** Secrets, `.env` files, credentials, dependencies,
  symlinks and large/binary project files are excluded from inspection.

## Beta limitations

Recovery is scoped and may be partial. Unsupported records or streaming limits
can stop it before recent messages. Moved projects and unsupported formats may
not match. Historical statements do not prove implementation or passing tests;
current file/Git evidence takes priority.

[Session consent and read limits](references/session_recovery.md) ·
[Format compatibility](references/transcript_compatibility.md) ·
[CLI and scanner details](references/technical-guide.md)

## Leave a handoff

Ask `Use $repo-rescue to checkpoint '.'.` Codex previews the exact destination and
full Markdown, including a reactivation prompt, then asks before writing. Session
consent never approves that write; nothing is automatically committed or published.

## Update

```sh
git -C "$HOME/.codex/skills/repo-rescue" pull --ff-only
```

Use your custom installation path if applicable, then start a new Codex chat.

## Development

```sh
python -B -m unittest discover -s tests -v
```

The [test workflow](https://github.com/penguinio-maker/repo-rescue/actions/workflows/tests.yml)
is configured for Windows, Linux and macOS with Python 3.11 and the latest stable
Python 3. Follow the link for actual CI results.

Use generated synthetic history only; never inspect real private sessions during
development. Follow [AGENTS.md](AGENTS.md) for tests, privacy review and publication.
