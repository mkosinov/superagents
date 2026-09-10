---
description: Sanitize .opencode/scratchpad.md per Scratchpad Discipline v2 — report first, then apply the auto-safe collapses with a backup; needs-user items stay the user's call
---

Handle a scratchpad sanitize request (Scratchpad Discipline v2). First action: call `get-session` and print the returned id.

1. **Run the audit — report-only** (default mode):
   `python3 .opencode/scripts/scratchpad_audit.py`
2. **Present the report to the user**: line count, the AUTO_SAFE findings, the NEEDS_USER list, and what was skipped (concurrency guard). Keep the message compact — the command output carries the detail.
3. **Apply AUTO_SAFE only on the user's confirmation** — re-run with `--apply` after they say so. The script writes `.opencode/scratchpad.md.bak-<YYYYMMDD-HHMM>` before any change; report the backup path and the new line count.
4. **NEEDS_USER items** — walk them with the user and apply their decision per item (edit/delete by hand or drop). Nothing there is applied automatically.
5. **Never touch a non-Idle session section** — not automatically (the script enforces it) and not by hand without the user's explicit sanction; a live session may be writing there.

Context:
- Routine path: the manager's Session Start Ritual runs this audit automatically when the scratchpad exceeds 150 lines (apply AUTO_SAFE there too, escalate NEEDS_USER).
- Discipline rules: the manager's `## Scratchpad Discipline` section; finishing flow: `docs/workflow/impl-phase.md`.
