# Board Etalon — Declarative Board Definition

**Date:** 2026-09-26
**Source:** `docs/specs/2026-09-21-board-bootstrap-design.md` (issue #24)
**Purpose:** Single source of truth for board shape (the machine block below) and field meaning (the prose). `board_bootstrap.py` reads the fenced `board-etalon` block; humans read the prose.

Option order in the block is the option order on the created field. Field/option values match the live boards #4 and #3 verbatim (verified 2026-09-22). Etalon resolution: `--etalon <path>`, else `docs/board/board-etalon.md` (repo root resolved from the script's path). Missing file or malformed block → refuse **before any network call**, naming the path and the parse error. The dry-run plan always prints which etalon path was used.

## Status

Lifecycle stage; merged names (no gate suffixes): `Hold` (paused) → `Backlog` (not in trajectory) → `In Design` (design underway, gates G1a–G2 pass inside it) → `Ready to IMPL` (plan approved, waiting for dispatch) → `In IMPL` (implementation running) → `PR (G7)` (pull request on CI) → `In-main` (merged) → `deployed`; `Not planned` = closed without plans. Gate stops are tracked in the `gate` field, not in status names. Note: a single-select's first option is what a freshly added item may get — the workflow rule «created an issue → set its status explicitly» (github-board skill) covers this; `init` sets every seeded card explicitly.

## Priority

Importance (Critical/High/Medium/Low). Behavioral rule (pick-priority, implemented in #23's `pick-next` / `pick-next-design`): among status-eligible cards, an elevated-priority card is taken first — order Critical > High > Medium > Low; a card with **no priority sorts last**; priority breaks ties among equals and does NOT override readiness (a `Backlog` card never jumps a `Ready to IMPL` card).

## host

Which machine owns the card (`imac` / `macbook` / `hk` / `gcp`). Single ownership source for `In IMPL` / `In Design`: stamped on entering those statuses, cleared on leaving — except the label survives `PR (G7)` (a card on CI stays visibly owned) and clears when it leaves `PR (G7)`. Per-host budget (host_budgets): imac 2, macbook 1, hk 1, gcp 1 — `In IMPL` cards count against their machine's budget; an `In IMPL` card with empty host blocks no one.

## gate

The pending-ask marker (`concept` / `spec` / `plan` / `blocked`): a design gate stop (concept = G1a, spec = G1b, plan = G2) or an IMPL blocker awaiting the user (`blocked`). Stamped when the question is asked, cleared at the user's answer and automatically when the card leaves `In Design` / `In IMPL`. Empty = nothing awaits the user.

## Machine block

```board-etalon
{
  "version": 1,
  "fields": [
    {"name": "Status", "type": "single_select", "options": ["Hold", "Backlog", "In Design", "Ready to IMPL", "In IMPL", "PR (G7)", "In-main", "deployed", "Not planned"]},
    {"name": "Priority", "type": "single_select", "options": ["Critical", "High", "Medium", "Low"]},
    {"name": "host", "type": "single_select", "options": ["imac", "macbook", "hk", "gcp"]},
    {"name": "gate", "type": "single_select", "options": ["concept", "spec", "plan", "blocked"]}
  ],
  "host_budgets": {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1}
}
```

## Drift contract (statuses)

The etalon is the intent, the web UI is the fact (the option list is user-managed there, e.g. `Not planned` was added on 2026-09-09). `adopt` compares and warns on any difference; it never writes options anywhere.
