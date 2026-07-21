# SuperAgents — Shared Agent Rules

This file is auto-loaded by all agents in the superagents framework.
It defines cross-cutting rules that apply regardless of the specific agent role.

---

## User input types

A message ending with `?` is a question. The agent answers with text and **takes no actions** (no tools, commits, file edits).

**Exception:** if the answer needs info not in context — read-only gathering (read a file, `git log`). After gathering — text answer immediately.

---

## Response Pattern: Status First

When the user sends a new message, structure your response as:

1. **Brief on previous task** — 1-3 lines max. Status of the most recent in-flight or just-completed task (DONE / BLOCKED / awaiting user OK), files changed in the last dispatch, what's pending from the user.
2. **Then** answer the user's actual question or proceed with the request.

**When to skip the brief:** if no dispatch happened since the user's last message and no in-flight task is awaiting user action, the brief is a 1-line "no in-flight tasks" and you can go straight to the answer.

**Why:** the user often reads the architect's last message and asks a new question before the next coder dispatch returns. When the dispatch DOES return between turns, the user sees a fresh question without context. The brief closes that loop and keeps the session state visible.

**What to put in the brief:**
- Status (DONE | DONE_WITH_CONCERNS | BLOCKED | awaiting user OK)
- File(s) changed (paths only, not diffs)
- Evidence (type-check, smoke test, etc. — but NOT test runs in Phase 1 of FasTP)
- Open questions or "OK пометить выполненной?" prompt

**What NOT to do:** don't repeat the full brief from earlier turns; don't paste diffs into the brief; don't make the brief longer than the answer to the actual question.

---

## Subagents: report your session ID first

**First action in every subtask:** call `get-session`, then print its returned id as the FIRST line of your reply, literally:

    task_id: ses_xxxxxxxxxxxxxxxx

No preamble ("I'll start by…"). The id line IS the preamble. Don't start other work before printing it textually — the orchestrator needs it as text to resume your session.
