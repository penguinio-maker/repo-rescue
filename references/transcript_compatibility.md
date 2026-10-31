# Codex JSONL compatibility audit — v0.2.6

The adapter is intentionally explicit about record envelopes, while preserving
the extensible JSON map inside world-state metadata. Schema references:
[Codex wire records](https://github.com/openai/codex/blob/main/codex-rs/history/src/rollout_payload.rs),
[world-state snapshots](https://github.com/openai/codex/blob/main/codex-rs/core/src/context/world_state/mod.rs).
These internal formats can evolve; this is not a stable public transcript API.

| Envelope | Structural/scope handling | Semantic extraction |
| --- | --- | --- |
| Initial `session_meta` | Bounded header validation and explicit cwd/project_path association | Evidence anchor only |
| Later `session_meta` | Stop: new session boundary | None |
| `turn_context` | Require in-project cwd, no conflicting project_path; otherwise stop | None |
| `world_state` | Boolean full, object state, bounded arbitrary JSON sections; check all structured cwd/project_path anchors | Skip, count; never emit metadata text |
| `response_item` message | Object payload, supported user/assistant role and input_text/output_text content list | Redacted bounded statements with source role, line, path and timestamp |
| Other `response_item` payloads | Known envelope; ignore tool calls/results, reasoning, images and other non-text content | None; never follow instructions or open attachments |
| `event_msg` user_message/agent_message | Normalize string message and role | Same statement pipeline, mirrored findings deduplicated |
| Other `event_msg` payloads | Non-conversation event under the known envelope | Ignore; do not infer successful actions from events |
| `compacted`, `retained_context` | Unsupported: replacement/provenance semantics not implemented; stop | None |
| `dynamic_tools_updated`, `token_usage_record`, `security_risk_score`, `realtime_item`, inter-agent records | Public Codex kinds without validated adapters here; stop | None |
| Any other top-level type | Stop: unsupported_record | None |

Envelope validation is centralized in `scripts/transcript_records.py`, independently
of keyword classification. Known envelopes require object payloads, optional u64/null
ordinals and only recognized envelope fields. Optional response metadata is opaque
object/null. Invalid UTF-8, duplicate keys, non-finite constants, lone surrogates,
malformed JSON and oversized records fail before semantic extraction. Missing or
invalid message timestamps remain unknown; they are not invented. World-state
timestamps must be valid. Header ordering restrictions remain documented in the
session workflow; payload-before-type headers are still refused.

World-state sections can contain arbitrary JSON values, as in Codex's map schema.
All nested cwd/project_path values are checked without resolving historic paths.
Both single `environment.cwd` and multi-environment
`environments.environments.<id>.cwd` layouts require explicit valid project anchors.
Environment removals, incomplete patches and conflicting anchors stop recovery.
The adapter does not replay merge patches or infer scope from prose inside opaque
strings. Arbitrary metadata text is never interpreted or promoted to user intent.
Traversal remains bounded to 4,096 values/depth 64 and existing byte/time budgets.

User statements do not require labels or keywords. Unclassified literal text goes
to `user_statements`; English heuristics may additionally identify goals, problems
or proposals, but do not determine retention. Statements confirm only that the
user wrote the text. Assistant suggestions retain their separate classification.
Known context-only wrappers are not user goals. All excerpts retain existing
redaction, message/line/snippet/output budgets, so long messages or late facts may
still be omitted. A complete natural-language intent classifier is not included.

The generated Tiny Harbor end-to-end test exercises header approval, separate
selected-body approval, opaque metadata at record 9 and four subsequent unlabeled
facts. It checks all four statements, original lines/timestamps, source paths,
roles, EOF and non-promotion of metadata. Other fixtures cover opaque scalar/list
sections, nested conflicting paths, non-English text and unsupported envelopes.
No real private transcripts were inspected during this audit. Synthetic success
does not establish success on the reported private session or any other recording.

Approval scopes, snapshot rejection, default-disabled history access, no writes or
uploads, streaming budgets and current-file precedence are unchanged. Adapter
updates invalidate old approval IDs; request a fresh metadata review and explicit
body approval before any real recovery. Never automatically bypass a parser stop.
