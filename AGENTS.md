# Repo Rescue development

These rules apply automatically to future tasks in this repository. They govern
development of Repo Rescue, not projects inspected by the installed skill.

1. After each user prompt that changes files, run relevant tests. For scanner
   changes, run `python -B -m unittest discover -s tests -v`.
2. Inspect Git status and the staged diff before each commit.
3. Check staged content and commit author metadata for secrets and personal data.
   This is a public repository. Use fictional fixtures only. Never publish local
   machine paths, OS usernames, private source, conversations, tokens, or reports.
4. Stage only intended files using explicit paths.
5. Commit each completed change with a descriptive message.
6. Push to `origin/main` after successful checks and existing publication
   authorization. Initial public creation requires account/repository confirmation.
7. Never force push or rewrite history.
8. Do not push if tests or privacy checks fail. Resolve or report the blocker.
9. Do not create empty commits.
10. Report changes, test results, commit hash, and push status.
11. Apply these rules automatically in future tasks.

Keep the scanner standard-library-only and read-only. Never execute discovered
project commands. Preserve explicit checkpoint approval in SKILL.md. Do not add
telemetry, network calls, or automatic report persistence. Optional v0.2 session
recovery must stay in its separate module, disabled by default, with project opt-in,
explicit approval for metadata-header matching, and a separate snapshot-bound
approval for selected transcript bodies. Test only generated synthetic
history; never inspect real Codex history during development or publish transcripts.
Use a public GitHub handle and a GitHub noreply email for commits after verifying
the account; do not change global Git identity.
