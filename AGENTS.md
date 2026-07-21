# SuperAgents — Shared Agent Rules

Cross-cutting rules auto-loaded for every agent.

---

## User input types

Message ending with `?` → text answer only (no tools, commits, edits). Exception: read-only gather if needed (`read`, `git log`), then answer.

---

## Response Pattern: Work Results First

A new message does **not** cancel a pending report. Show work outcome **before** the new topic.

1. **Work results** — you or a dispatched subagent since the user's last turn (tools, dispatch return, commits, failures). Lead even if the new message is unrelated.
2. **Then** answer or continue the new request.

Never open with only the latest question while deliverables are still unreported.

**First report** (user has not seen the outcome): status (DONE | DONE_WITH_CONCERNS | BLOCKED | awaiting user OK), what changed, file paths, evidence (no full FasTP Phase 1 test runs), blockers, "OK пометить выполненной?" if needed — as long as clarity needs; not capped at 3 lines.

**Reminder** (outcome already shown): 1–3 lines, then answer.

**Same turn:** tools/edits in this turn → final message must summarize them, not only a side-answer.

Avoid: new topic first with pending work; repeating a full first report after acknowledgment; full diffs (paths + short outcome enough).
