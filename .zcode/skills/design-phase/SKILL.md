---
name: design-phase
description: DESIGN phase on the host (zcode) in the host/container split topology — brainstorm G1a → spec + 5-reviewer panel G1b → plan + review G2, DoD = push to origin, board = the scripts/gh_board.py script living in memo itself, handoff to the container is «продолжаем траекторию #NNN». Use when the user writes «design #NNN», «продолжаем design», «вернулся #NNN», or asks for a spec/plan for an issue in a host session.
---

# DESIGN phase on the host (split host/container)

## 0. Topology and role

DESIGN (gates G1a/G1b/G2) is this interactive zcode host session. IMPL (G3–G7) is the opencode container (@manager/@architect) — we do not go there. The session merges the manager+architect roles for DESIGN: talks to the user at the gates and dispatches subagents **one level deep** (panel, plan reviewer) — nested dispatch is unnecessary and unavailable (depth limit).

Only what is pushed/flipped crosses the seam (git + board). Workflow canon: `~/dev/superagents/docs/workflow/design-phase.md` (this phase) + `impl-phase.md`; migration plan: `~/dev/superagents/docs/plans/2026-09-05-host-design-container-impl-split-plan.md`.

## 1. Session start (ritual)

1. Card returned from IMPL? First `gh issue view N --comments` (read-only) — a comment is the input: re-run the affected gates, not everything from scratch.
2. Git pre-flight (in `~/dev/memo`): `git fetch origin && git status -sb`
   - behind → `git pull --ff-only`, continue;
   - **diverged (ahead+behind) → STOP**: show the user, reset nothing (precedent — passenger commit cc8bc52).
3. Board: `next-up` (§7) → show the trajectory to the user.
4. The user picks an issue → `status N "In Design (G1a)"`. Guard: the issue must not sit in `In IMPL` — one issue lives in one phase at a time.
5. **Scout (pre-G1a recon) — by dispatch, not by hand.** Right after the issue is picked, dispatch built-in read-only subagents to gather facts (zcode — `Explore`, opencode — `explorer`; a cheap model is these agents' default). Default is **one**; wide scope (many subsystems / dependency issues) — several in parallel, one per zone, in a single Agent-tool message. The prompt: issue number, what the issue claims, what to verify against the live tree (dependencies, consumers, patterns).
   - Back comes a **compact fact sheet**: key files' structure/size vs the issue's claims; every claim confirmed/denied with `file:line`; dependency issues' state (open/closed + a one-line delta); consumer inventory; ready patterns to reuse.
   - Until G1a the main session reads **only scout reports** — as-is, no raw merging. No raw file bodies or grep dumps into its context (`gh issue view` on dependencies goes to the scout too). Rationale: the main session's context is expensive and lives the whole session (G1a → G2); recon garbage in it is dead weight (issue #14: ~10 tool calls and a 577-line file read to produce a ~40-line concept).
   - A spot check during the G1a dialogue (one grep / one file section) is fine by hand; bulk recon — scout only.
6. **G1a — brainstorm:** invoke the `brainstorming` skill (Skill tool); pass it the scout fact sheet + issue number. The skill runs the dialogue (questions one at a time → 2–3 approaches → concept); its finish is the build / deliberately-NOT-build concept presented for user approval = gate G1a. The board already sits at `In Design (G1a)` — no flip; after approval — the spec (§3).

## 1.5 Session rules (talking to the user)

- A message ending in `?` is a question: answer in text, **no actions** (tools, commits, file edits). Exception: the answer needs data not in context — read-only gathering (read a file, `git log`), then an immediate text answer.
- **Report before answer**: a new message does not cancel an unread work result. First the result (status DONE | DONE_WITH_CONCERNS | BLOCKED | awaiting user OK; changed files as paths; evidence; blockers/questions), then the answer to the new message. If no dispatches happened since the user's last message and nothing awaits their decision — say "no outstanding tasks" and answer immediately. Edits in the current turn — the final message must summarize them.

## 2. Gates (all three human; board flips strictly at the gate moment)

| Gate | The user approves | After approval |
|---|---|---|
| G1a | the concept: what we do / what we do NOT (scope boundaries) | the spec is written |
| G1b | the spec — after the panel's consolidated report and fixes | commit + **push** the spec; board → `Spec OK (G1b)` |
| G2 | the plan — UI features by **Behavioral Delta** (behavior, not code); the engineering part is the reviewer's guarantee | amendments and constraints **baked into the plan text**; commit + **push**; board → `Ready to IMPL (G2)` |

## 3. Artifacts

- Spec: `docs/specs/YYYY-MM-DD-<feature>-design.md`. Must include a `## User Scenarios` section — 3–7 user tasks the feature enables, each mapping to an E2E test (anchors the plan's E2E-in-DoD rule; the completeness panelist checks it). **Self-contained BEFORE the panel**: the panel does not read GH issues — the scope check against the issue is done by the main session itself, with findings baked into the spec text.
- Plan: `docs/plans/YYYY-MM-DD-<feature>-plan.md` per the writing-plans conventions (canon: `~/dev/superagents/.opencode/skills/writing-plans/SKILL.md`):
  - header: Goal / Architecture / Tech Stack; immediately after it a `## Behavioral Delta` section;
  - every task anchor: `## Task N: <name>` + `### Classification: trivial|small|standard|large`; after commit, never renumber anchors;
  - every task carries `### Required Docs` (domain-rules for entities, design-system for UI);
  - a task implements a User Scenario (from the spec's `## User Scenarios`) → its DoD line: "E2E test for scenario N passes (RED-GREEN-REFACTOR)";
  - no placeholders ("TBD", "add validation" — that is a plan failure).
- Domain rules changed → `docs/domain-rules/` is committed together with the spec.

## 4. Panel (host port — body from `.opencode/skills/panel-spec-review`)

1. Dispatch: **5 agents in parallel**, in a single Agent-tool message:
   `spec-panel-completeness`, `spec-panel-consistency`, `spec-panel-feasibility`, `spec-panel-simplicity`, `spec-panel-best-practices` (files in the repo's `.zcode/agents/`, models `omniroute/panel-*`).
2. Each prompt: the **spec path** (+ the previous spec revision's path, if there was one). No `gh issue view`, no network — except best-practices, whose design includes WebSearch/WebFetch.
3. Aggregation: collect the 5 reports → dedupe identical findings → rank **BLOCKER > MAJOR > MINOR** → one consolidated report to the user for the fix decision.
4. **Availability policy (host adaptation, no subagent audit):** a panelist did not return / crashed → **one** rerun; second failure → mark it `skipped` in the consolidated report, verdict on the rest.
5. best-practices returned `Verdict: FAILED` (web research unavailable) → note it in the report and exclude it from the verdict — that is its designed refusal, not a crash.
6. The agent registry is seeded only at session start: `Agent tool: not found` while `.zcode/agents/` files exist → restart the session.

## 5. Plan review

Dispatch `plan-reviewer` (verifies the plan faithfully and completely expands the approved spec): the prompt carries the spec path + plan path. Report → fixes by the user's decision → folded into the plan.

## 6. DESIGN session DoD (the seam contract)

- Only **git and the board** cross the seam. The session does NOT end holding local commits: every passed gate = commit + push to origin/main.
- **All decisions are folded into the artifact texts**: review amendments, constraints like "#NNN strictly after #NNN — shared file" go into the spec/plan, not the chat. Git and the board carry no session context across the seam. This is the DESIGN DoD under Scratchpad Discipline v2: DESIGN writes zero scratchpad state, so the pushed spec/plan are the ONLY carrier — fold every decision and dependency in **before the phase closes**.
- After G2 tell the user: «скажи менеджеру в opencode: продолжаем траекторию #NNN». The container needs nothing else.
- Does NOT cross the seam: `.opencode/scratchpad.md` (the container seeds its section at IMPL start — DESIGN itself writes nothing, v2), worktrees, env. The host **never writes or reads** the scratchpad — there are no container operations during the DESIGN phase at all.

## 7. Board (the script lives in memo, run locally)

```bash
python3 .zcode/scripts/gh_board.py next-up
python3 .zcode/scripts/gh_board.py show 247                # read one card; `show all` = whole board
python3 .zcode/scripts/gh_board.py status 176 "Spec OK (G1b)"
python3 .zcode/scripts/gh_board.py set-next-up 176 1   # only on the user's word
```

- The script's golden source is **the memo repo itself** (`.zcode/scripts/gh_board.py`, Project #3 constants baked in). The script is part of the seam: it lives in git, so both the host and the container have it after a pull; the container copy is `.opencode/scripts/gh_board.py`. No extra copies outside the harness folders.
- **No raw-GraphQL fallback.** ALL board interaction — reads and writes — goes through the script; never hand-write `gh api graphql` against the project. Field-definition mutations (`updateProjectV2Field`: adding/renaming status options) are forbidden for agents: the mutation replaces the whole option list and detaches every card's value (2026-09-09: 65/69 cards lost Status this way). A new status is added by the user in the GitHub web UI, which appends safely.
- One writer per issue: DESIGN flips (`In Design (G1a)` → `Spec OK (G1b)` → `Ready to IMPL (G2)`) — this session; IMPL flips — the container manager. The script adds an issue to the board on first contact.

## 8. Rules

- One issue = one phase at a time; the board is the guard. DESIGN on X + IMPL on Y in parallel — allowed.
- One DESIGN session = one issue.
- Parallel DESIGN sessions (different issues, different host sessions): simultaneous push → `git pull --rebase`.
- Return from IMPL: the card goes to `In Design (G1a)` (broken spec) or `Spec OK (G1b)` (broken plan) + an issue comment — that is a new DESIGN session's starting point (§1.1).
- DESIGN-phase agents and skills live **in this repo**: `.zcode/agents/` + `.zcode/skills/` — `design-phase` (the phase protocol) and `brainstorming` (the G1a dialogue; invoked from here, never fires on its own) (git = source of truth for the memo port). Superagents canon: bodies — `~/dev/superagents/.opencode/agents/`, reference seed of host ports — `~/dev/superagents/.zcode/agents/`; a canon change is ported by editing the files in `.zcode/agents/` (the port is marked in each file's header). Canon v3.4 (2026-09-06): panel `spec-review-*` → `spec-panel-*`; `spec-reviewer` split into `plan-reviewer` (G2, host) + `code-compliance-reviewer` (G5, container-only). The omniroute model catalog is the local `~/.zcode/v2/config.json` (with keys — never committed).
