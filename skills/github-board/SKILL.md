---
name: github-board
description: Manage GitHub Project board — read the Next Up trajectory at session start, move issue status when starting/finishing work, shift the queue on completion. Invoke at session start (empty scratchpad), when user picks an issue, and at workflow finishing.
---

Managing the GitHub Project board is the **@manager's responsibility**, same as the scratchpad.

**Project:** configure per project — set `PROJECT_ID`/`OWNER`/`NEXT_UP_FIELD` constants in `scripts/gh_board.py` (get IDs via `gh api graphql` projectsV2 query).
**Script:** `python3 .opencode/skills/github-board/scripts/gh_board.py <cmd>`

## Model

The board = the development trajectory (durable, cross-session). The scratchpad = context of the work chosen in the current session. Do not mix them.

- **Status** — lifecycle stage: `Backlog → In Design (G1a) → Spec OK (G1b) → Ready to IMPL (G2) → In IMPL → PR (G7) → In-main → deployed`
- **Priority** — importance (Critical/High/Medium/Low)
- **Next Up** (1/2/3) — the user's explicit queue: which task to take next. Only the manager changes it, on the user's word.

Status is gate-anchored: each status names the last workflow gate passed. Flip it at gate approval, not by feel. (In Review and Staging / QA were removed — never used.)

| Status | Gate | Meaning | Set by |
|---|---|---|---|
| Backlog | — | not in the trajectory | user |
| In Design (G1a) | G1a | concept approved in brainstorm; spec work underway | DESIGN session |
| Spec OK (G1b) | G1b | panel review done, spec fixes folded, spec pushed to main | DESIGN session |
| Ready to IMPL (G2) | G2 | plan reviewed and pushed — the signal for IMPL start (plan-only start) | DESIGN session |
| In IMPL | G3 | worktree + baseline green, dev loop running | container manager |
| PR (G7) | G7 | finishing: PR open, CI/merge pending | container |
| In-main | — | merged to main | manager, mandatory |
| deployed | — | released to production | user |

## Commands

```bash
python3 .opencode/skills/github-board/scripts/gh_board.py next-up                    # show the trajectory (queue 1→3)
python3 .opencode/skills/github-board/scripts/gh_board.py set-next-up 176 1          # put an issue in the queue (1|2|3); "none" — remove
python3 .opencode/skills/github-board/scripts/gh_board.py shift                      # after Next Up 1 completes: clear it, shift 2→1, 3→2
python3 .opencode/skills/github-board/scripts/gh_board.py status 176 "In IMPL"         # move a card's status
```

An issue is automatically added to the board on the first set/status call if it wasn't there.

## Workflow touchpoints

| Moment | Action | Who |
|---|---|---|
| **Session start, scratchpad = Idle** | `gh_board.py next-up` → show the user the trajectory, ask what to take | manager, automatic |
| **User picked a task** | `status N "In Design (G1a)"` | whoever runs DESIGN — manager in-container; host DESIGN session after the split |
| **Design gate passed (G1a/G1b/G2)** | flip status per the gate table above | whoever runs DESIGN |
| **New issue created (gh issue create)** | ask the user whether to put it in Next Up (and where) | manager |
| **User changes the trajectory** | `set-next-up` per their words | manager |
| **Plan-only IMPL entry (split): user says «продолжаем траекторию #N», card at `Ready to IMPL (G2)`** | verify plan on fetched main → dispatch IMPL (plan-only start, no worktree yet — architect's first action) → `status N "In IMPL"` | manager, container |
| **IMPL blocked: spec/plan invalid (return path)** | architect reports BLOCKED → user decides → issue comment + `status N` back to `In Design (G1a)` / `Spec OK (G1b)`; scratchpad section → Idle line (reason, status, comment URL); worktree keep-vs-discard — user decides | manager, after user decision |
| **Finishing: PR created** | `status N "PR (G7)"` | manager, at the architect's finishing report |
| **Workflow finished, PR merged** | `status N "In-main"`; if the issue was Next Up 1 → `shift` | manager, mandatory finishing step (architect reports `## Board Update Needed`) |

## Rules

- Next Up — max 3 positions, no duplicates (the script frees an occupied position automatically).
- Don't move Status on every micro-task — only when the whole task's stage changes.
- FasTP fixes without an issue: don't touch the board. FasTP on an issue: Status In IMPL → In-main as usual.
