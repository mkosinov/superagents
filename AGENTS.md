# SuperAgents — Shared Agent Rules

This file is auto-loaded by all agents in the superagents framework.
It defines cross-cutting rules that apply regardless of the specific agent role.

---

## User input types

A message ending with `?` is a question. The agent answers with text and **takes no actions** (no tools, commits, file edits).

**Exception:** if the answer needs info not in context — read-only gathering (read a file, `git log`). After gathering — text answer immediately.

---

## Response Pattern: Work Results First

A new message does **not** cancel a pending report. Show work outcome **before** the new topic.

1. **Work results** — you or a dispatched subagent since the user's last turn (tools, dispatch return, commits, failures). Lead even if the new message is unrelated.
2. **Then** answer the user's actual question or proceed with the request.

Never open with only the latest question while deliverables are still unreported.

**First report** (user has not seen the outcome) — include:
- Status (DONE | DONE_WITH_CONCERNS | BLOCKED | awaiting user OK)
- File(s) changed (paths only, not diffs)
- Evidence (type-check, smoke test, etc. — but NOT test runs in Phase 1 of FasTP)
- Blockers, open questions or "OK пометить выполненной?" prompt

As long as clarity needs — not capped at 3 lines.

**Reminder** (outcome already shown): 1–3 lines, then answer.

**When to skip:** if no dispatch happened since the user's last message and no in-flight task is awaiting user action, the report is a 1-line "no in-flight tasks" and you can go straight to the answer.

**Same turn:** tools/edits in this turn → final message must summarize them, not only a side-answer.

**What NOT to do:** don't repeat the full report from earlier turns; don't paste diffs into the report; don't make the report longer than the answer to the actual question.

---

## Subagents: report your session ID first

**First action in every subtask:** call `get-session`, then print its returned id as the FIRST line of your reply, literally:

    task_id: ses_xxxxxxxxxxxxxxxx

No preamble ("I'll start by…"). The id line IS the preamble. Don't start other work before printing it textually — the orchestrator needs it as text to resume your session.
