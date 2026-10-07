---
name: github-board
description: Manage GitHub Project board — read the Next Up trajectory, check card statuses, move issue status when starting/finishing work, shift the queue on completion. Invoke whenever the board comes up — session start, the user pastes a board/issue link or picks an issue, workflow finishing.
---

In the container the board is the **@manager's** responsibility, same as the scratchpad. On the host (zcode), the DESIGN session owns its board flips (design-phase §7) — and any other host session that touches the board follows this skill.

**Project:** configure per project — set `PROJECT_ID`/`OWNER`/`NEXT_UP_FIELD` constants in the script (get IDs via `gh api graphql` projectsV2 query).
**Script:** the script lives **in the project repo** (host `.zcode/scripts/gh_board.py`, container `.opencode/scripts/gh_board.py`) — the board is part of the host/container seam and travels via git. Both canon harness folders ship identical copies (`.zcode/scripts/` + `.opencode/scripts/`); adjust the constants in both when seeding a new project.
**Board shape** (statuses, fields, option order): `docs/board/board-etalon.md` — the declarative definition `board_bootstrap.py` creates boards from.

## Model

The board = the development trajectory (durable, cross-session). The scratchpad = context of the work chosen in the current session. Do not mix them.

- **Status** — lifecycle stage: `Hold → Backlog → In Design → Ready to IMPL → In IMPL → PR (G7) → In-main → deployed`; `Not planned` = closed without plans
- **Priority** — importance (Critical/High/Medium/Low)
- **Next Up** (1/2/3) — the user's explicit queue: which task to take next. Only the manager changes it, on the user's word.
- **host** — which machine owns the card (single-select per the etalon). Ownership marker for `In IMPL` / `In Design` cards; stamping and per-host budgets are project-local script mechanics (memo's live script implements them; the seed script does not manage this field).
- **gate** — the pending-ask marker (`concept` / `spec` / `plan` / `blocked`): a design gate stop (concept = Gate A, spec = Gate B, plan = Gate C) or an IMPL blocker awaiting the user. Set via `gh_board.py gate N <value>`, cleared at the user's answer (`gate N none`). Empty = nothing awaits the user. Machine-stamped values (e.g. the hang monitor's `hang`) may also appear when that tooling is enabled. The option list itself is user-managed in the web UI.

Statuses are coarse positions; inside `In Design` the pending design gate is the **gate field** on the card, set at the stop and cleared at the user's answer. Empty gate + `In Design` = the agent is working, nothing awaits the user. The design card flips only once: `In Design` → `Ready to IMPL` at Gate C (fast-track skips `Ready to IMPL` entirely). Single exception: `In IMPL` flips at IMPL dispatch, before G3 evidence exists — a flip placed after the blocking dispatch lands hours late or never (see touchpoint below). (In Review and Staging / QA were removed — never used.)

| Status | Gate | Meaning | Set by |
|---|---|---|---|
| Hold | — | paused | user |
| Backlog | — | not in the trajectory | user |
| In Design | A/B/C | design in progress — gates live here; the gate field names the pending ask (concept pick / spec OK / plan forces a spec change) | DESIGN session |
| Ready to IMPL | C | Gate C passed (auto unless the plan forced a spec change): plan reviewed and pushed — the signal for IMPL start (plan-only start) | DESIGN session |
| In IMPL | G3 | IMPL dispatched (plan-only start); worktree + baseline green follow as the architect's first steps | container manager |
| PR (G7) | G7 | finishing: PR open, CI/merge pending | container |
| In-main | — | merged to main | manager, mandatory |
| deployed | — | released to production | user |
| Not planned | — | closed without plans (stale-issue auto-close lands here too) | DESIGN session / user |

## Commands

```bash
python3 .opencode/scripts/gh_board.py next-up                    # show the trajectory (queue 1→3)
python3 .opencode/scripts/gh_board.py show 176                    # read one card: status + queue position
python3 .opencode/scripts/gh_board.py show all                    # the whole board as a table
python3 .opencode/scripts/gh_board.py set-next-up 176 1          # put an issue in the queue (1|2|3); "none" — remove
python3 .opencode/scripts/gh_board.py shift                      # after Next Up 1 completes: clear it, shift 2→1, 3→2
python3 .opencode/scripts/gh_board.py status 176 "In IMPL"       # move a card's status
python3 .opencode/scripts/gh_board.py gate 176 spec               # pending-ask marker: concept|spec|plan|blocked; none clears; idempotent
python3 .opencode/scripts/gh_board.py merged 176 177 "short title" # v2: append the "Recently merged" scratchpad line
```

An issue is automatically added to the board on the first set/status call if it wasn't there.

## Workflow touchpoints

| Moment | Action | Who |
|---|---|---|
| **Session start, no active workflow** | `gh_board.py next-up` → show the user the trajectory, ask what to take | manager, automatic |
| **Card status check (pre-flight, triage, "can X run in parallel?")** | `gh_board.py show N` (or `show all`) | manager |
| **User picked a task** | `status N "In Design"` | whoever runs DESIGN — manager in-container; host DESIGN session after the split |
| **Design stop / gate passed (A/B/C)** | stop → `gate N concept\|spec\|plan`; user answered → `gate N none`; Gate C passed → `gate N none` + `status N "Ready to IMPL"` (this script variant does not auto-clear the gate on a status flip — clear it explicitly) | whoever runs DESIGN |
| **New issue created (gh issue create)** | add the card in the same breath: `status N "Backlog"` — the user tracks work in the project board and does not see card-less issues; discuss Next Up only when it is upcoming work | manager |
| **User changes the trajectory** | `set-next-up` per their words | manager |
| **Plan-only IMPL entry (split): user says «start impl #N», card at `Ready to IMPL`** | verify card + plan on fetched main → `status N "In IMPL"` → dispatch IMPL (plan-only start, no worktree yet — architect's first action). Flip BEFORE the dispatch: the dispatch blocks for the whole marathon (2026-09-13: #262 sat on `Ready to IMPL` through a 15-hour run) | manager, container |
| **IMPL blocked: spec/plan invalid (return path)** | architect reports BLOCKED → user decides → issue comment + `status N` back to `In Design`; a broken plan additionally sets `gate N plan` (the new DESIGN session resumes at Gate C); scratchpad (v2): section removed if the worktree is discarded, kept while a kept worktree lives — the durable record is the issue comment; worktree keep-vs-discard — user decides | manager, after user decision |
| **Finishing: PR created** | `status N "PR (G7)"` at the architect's `PR_CREATED` report (finishing Dispatch 1 ends right after PR creation) → immediately re-dispatch the architect for CI watch + merge | manager |
| **Workflow finished, PR merged** | `status N "In-main"`; if the issue was Next Up 1 → `shift`; close the issue if still open (`gh issue close N --reason completed` — the PR's `Closes #N` normally auto-closed it at merge; tolerate "already closed"); then `merged N <pr> "<short title>"` (v2 — appends the `## Recently merged` line) and remove your scratchpad section | manager, mandatory finishing step (architect reports `## Board Update Needed`) |

## Rules

- ALL board interaction — reads AND writes — goes through this script only. NEVER hand-write `gh api graphql` against the project: reads waste calls and have historically gone wrong (wrong owner type, nonexistent fields), and field-definition mutations destroy data. Exception: `board_bootstrap.py` is the rollout-time board writer (create/link/seed during repo setup only); everyday board writes remain exclusively this script's.
- Changing the Status or gate option list (adding/renaming options) is **user-only, via the GitHub web UI**. The agent never runs `updateProjectV2Field`: the mutation replaces the whole option list and detaches every card's value (2026-09-09: 65/69 cards lost Status this way). Need a new status → ask the user to add it in the web UI.
- Next Up — max 3 positions, no duplicates (the script frees an occupied position automatically).
- Every new issue gets its board card (Status=Backlog) immediately at creation — the board mirrors ALL open issues; an off-board issue is invisible to the user.
- Don't move Status on every micro-task — only when the whole task's stage changes.
- FasTP fixes without an issue: don't touch the board. FasTP on an issue: Status In IMPL → In-main as usual.
