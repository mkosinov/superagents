---
name: github-board
description: Manage GitHub Project board — check card statuses, pick the next card (priority-ordered), move issue status when starting/finishing work. Invoke whenever the board comes up — session start, the user pastes a board/issue link or picks an issue, workflow finishing.
---

In the container the board is the **@manager's** responsibility, same as the scratchpad. On the host (zcode), the DESIGN session owns its board flips (design-phase §7) — and any other host session that touches the board follows this skill.

**Project identity:** comes from `docs/board/board_config.json` (format v1) — generated once by `board_bootstrap.py adopt` and committed as repo content. Never hand-set ids in the script: the script is byte-identical across repos, only the config is per-repo (the script resolves the repo root from its own path, so both copies read the same file).
**Script:** the script lives **in the project repo** (host `.zcode/scripts/gh_board.py`, container `.opencode/scripts/gh_board.py`) — the board is part of the host/container seam and travels via git. Both canon harness folders ship byte-identical copies; edit one, copy over the other.
**Board shape** (statuses, fields, option order): `docs/board/board-etalon.md` — the declarative definition `board_bootstrap.py` creates boards from. Status/host/gate option ids are read live from the board at write time — the option list is user-managed in the web UI, never hardcode.

## Model

The board = the development trajectory (durable, cross-session). The scratchpad = context of the work chosen in the current session. Do not mix them.

- **Status** — lifecycle stage: `Hold → Backlog → In Design → Ready to IMPL → In IMPL → PR (G7) → In-main → deployed`; `Not planned` = closed without plans
- **Priority** — importance (Critical/High/Medium/Low). Both pick commands order status-eligible cards Critical > High > Medium > Low (unset last; ties by the older issue number) — priority never overrides status eligibility: a `Backlog` Critical card is not visible to `pick-next`, and a `Ready to IMPL` Low card loses only to other `Ready to IMPL` cards.
- **host** — which machine owns the card (single-select per the etalon: `imac` / `macbook` / `hk` / `gcp`). Single ownership source for `In IMPL` / `In Design` cards: stamped automatically on entering those statuses (host arg > `GH_BOARD_HOST` env > container label file), cleared automatically on leaving them — except the label survives `PR (G7)`: a card on CI stays visibly owned by its machine (and returns to it if CI is red) while occupying no IMPL slot; the label clears when the card leaves `PR (G7)`. Per-host budgets (`host_budgets` in `board_config.json`; etalon: imac 2, macbook 1, hk 1, gcp 1; default 1 for unknown hosts) count **`In IMPL` cards only** — design capacity is the one-design-at-a-time invariant, and an `In IMPL` card with an empty host blocks no one.
- **gate** — the pending-ask marker (`concept` / `spec` / `plan` / `blocked`): a design gate stop (concept = Gate A, spec = Gate B, plan = Gate C) or an IMPL blocker awaiting the user. Set via `gh_board.py gate N <value>`, cleared at the user's answer (`gate N none`) and automatically when the card leaves `In Design`/`In IMPL` via `status`; entering `PR (G7)` clears the gate but keeps the host. Empty = nothing awaits the user. Machine-stamped values (e.g. the hang monitor's `hang`) may also appear when that tooling is enabled. The option list itself is user-managed in the web UI.

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

## Pick protocol (token commands)

- `pick-next [host]` — the auto-impl watcher's token: prints `NONE` or an issue number. Needs a resolved host (arg > `GH_BOARD_HOST` env > container label file; unresolved → error). Budget first: cards `In IMPL` on this host at `host_budgets[host]` → `NONE` (manual IMPL sessions count too — they stamp the host as well). Candidates: OPEN issues at `Ready to IMPL`, priority order. Skips: cards whose auto-impl log comment's last entry is a fresh (≤ 1 h) CLAIM/BLOCKED, and cards whose body declares `depends-on: #N` with N still OPEN.
- `pick-next-design` — the DESIGN kickoff token: prints an issue number or `NONE (reason)`. One design at a time: any card in `In Design` → `NONE (design slot busy: …)`. Candidates: OPEN `Backlog` cards, priority order, `depends-on` skips → `NONE (all Backlog cards blocked by depends-on)` when nothing is eligible.

## Commands

```bash
python3 .opencode/scripts/gh_board.py show 176                      # read one card: status, host, gate; `show all` = whole board as a table
python3 .opencode/scripts/gh_board.py pick-next imac                # watcher token: NONE | <issue> (budget, freshness, depends-on honored)
python3 .opencode/scripts/gh_board.py pick-next-design              # design kickoff token: <issue> | NONE (reason)
python3 .opencode/scripts/gh_board.py status 176 "In IMPL"          # move a card; optional 3rd arg = host value (imac/macbook/hk/gcp)
python3 .opencode/scripts/gh_board.py host 176                      # read the card's host field (empty when unset)
python3 .opencode/scripts/gh_board.py gate 176 spec                 # pending-ask marker: concept|spec|plan|blocked; none clears; idempotent
python3 .opencode/scripts/gh_board.py auto-log 176 "BLOCKED …"      # append to the issue's auto-impl log comment (watcher/manager channel)
python3 .opencode/scripts/gh_board.py auto-state 176                # last auto-impl log entry (diagnostics)
python3 .opencode/scripts/gh_board.py reconcile [host] [--dry-run]  # stale-card sweep (top of every watcher loop); --dry-run prints the plan, mutates nothing
python3 .opencode/scripts/gh_board.py issue 176                     # standard issue view: state, labels, body (≤120 lines)
python3 .opencode/scripts/gh_board.py merged 176 177 "short title"  # append the "Recently merged" scratchpad line (container-side — never on the host)
```

An issue is automatically added to the board on the first set/status call if it wasn't there.

## Fast-track (docs-only, not a command)

An issue whose diff touches only docs/prose may skip the container IMPL session entirely; a diff touching anything executable — `scripts/`, `.github/workflows/`, agent or skill bodies, site build — disqualifies fast-track and forces the normal plan-reviewed path (the watcher auto-pulls main every cycle and executes harness files from it, so a fast-tracked merge must never carry executable changes that skipped plan review). Flow: the card goes `In Design` → `In IMPL` while the change PR is open → `In-main` on merge — it never sits in `Ready to IMPL`; the spec carries `## Verification` instead of a plan. Full protocol: design-phase §2. The `merged` scratchpad line is container-side; the host records nothing.

## Workflow touchpoints

| Moment | Action | Who |
|---|---|---|
| **Session start, no active workflow** | `show all` → the board as a table; what to work on is the user's call, the board mirrors it | manager, automatic |
| **Auto-impl watcher loop (container)** | `reconcile <host>` → `pick-next <host>` → a number → claim `status N "In IMPL"` (stamps host) → after 6 s re-read `host N` — still this machine? → dispatch/resume the IMPL run; `NONE` → next cycle | container watcher |
| **Card status check (pre-flight, triage, "can X run in parallel?")** | `gh_board.py show N` (or `show all`) | manager |
| **Design kickoff (host DESIGN session, scheduled or interactive)** | `pick-next-design` → a number → `status N "In Design"` | DESIGN session |
| **User picked a task** | `status N "In Design"` (host stamps from arg/`GH_BOARD_HOST`/label file — pass it explicitly on the host) | whoever runs DESIGN — manager in-container; host DESIGN session after the split |
| **Design stop / gate passed (A/B/C)** | stop → `gate N concept\|spec\|plan`; user answered → `gate N none`; Gate C passed → `status N "Ready to IMPL"` (the flip clears the gate and the host automatically) | whoever runs DESIGN |
| **New issue created (gh issue create)** | add the card in the same breath: `status N "Backlog"` — the user tracks work in the project board and does not see card-less issues | manager |
| **Plan-only IMPL entry (split): user says «start impl #N», card at `Ready to IMPL`** | verify card + plan on fetched main → `status N "In IMPL"` → dispatch IMPL (plan-only start, no worktree yet — architect's first action). Flip BEFORE the dispatch: the dispatch blocks for the whole marathon (2026-09-13: #262 sat on `Ready to IMPL` through a 15-hour run) | manager, container |
| **IMPL blocked: spec/plan invalid (return path)** | architect reports BLOCKED → user decides → issue comment + `status N` back to `In Design`; a broken plan additionally sets `gate N plan` (the new DESIGN session resumes at Gate C); scratchpad (v2): section removed if the worktree is discarded, kept while a kept worktree lives — the durable record is the issue comment; worktree keep-vs-discard — user decides | manager, after user decision |
| **Finishing: PR created** | `status N "PR (G7)"` at the architect's `PR_CREATED` report (finishing Dispatch 1 ends right after PR creation) → immediately re-dispatch the architect for CI watch + merge | manager |
| **Workflow finished, PR merged** | `status N "In-main"`; close the issue if still open (`gh issue close N --reason completed` — the PR's `Closes #N` normally auto-closed it at merge; tolerate "already closed"); then `merged N <pr> "<short title>"` (container-side — appends the `## Recently merged` line) and remove your scratchpad section | manager, mandatory finishing step (architect reports `## Board Update Needed`) |

## Rules

- ALL board interaction — reads AND writes — goes through this script only. NEVER hand-write `gh api graphql` against the project: reads waste calls and have historically gone wrong (wrong owner type, nonexistent fields), and field-definition mutations destroy data. Exception: `board_bootstrap.py` is the rollout-time board writer (create/link/seed during repo setup only); everyday board writes remain exclusively this script's.
- Changing the Status or gate option list (adding/renaming options) is **user-only, via the GitHub web UI**. The agent never runs `updateProjectV2Field`: the mutation replaces the whole option list and detaches every card's value (2026-09-09: 65/69 cards lost Status this way). Need a new status → ask the user to add it in the web UI.
- Project identity (`docs/board/board_config.json`) is written only by `board_bootstrap.py adopt` — never hand-edit the config, never bake ids into the script.
- Every new issue gets its board card (Status=Backlog) immediately at creation — the board mirrors ALL open issues; an off-board issue is invisible to the user.
- Don't move Status on every micro-task — only when the whole task's stage changes.
- Declare hard dependencies in the issue body as a `depends-on: #N, #M` line — the pickers skip a card while a referenced issue is OPEN. Examples only inline in backticks: any line-start `depends-on:` is parsed as a real declaration.
- The auto-impl watcher sweeps stale cards every loop (`reconcile`): a closed issue sitting in `In IMPL`/`PR (G7)` gets the lost finishing flip (`In-main`/`Not planned` + the `merged` line when the closing PR is found); a dead `In IMPL` run on the watcher's own host (sessions silent over an hour — the run CLI is not a liveness marker) gets a BLOCKED auto-log entry and returns to `Ready to IMPL`. `reconcile --dry-run` prints the plan without mutations.
- Fast-track fixes without an issue: do NOT create an issue or a board card — don't touch the board. A PR is still required (green-CI merge gate). Fast-track on an existing issue: Status In IMPL → In-main as usual.
