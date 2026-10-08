---
name: design-phase
description: DESIGN phase on the host (zcode) in the host/container split topology — scout + issue-actuality check → concept gate A (auto) → spec + 6-reviewer panel → spec gate B (the user's main OK) → plan + plan-reviewer → plan gate C (auto), DoD = push to origin, board = the gh_board.py script shipped in this repo, handoff to IMPL is «start impl #NNN». Use when the user writes «design #NNN», «продолжаем design», «вернулся #NNN», or asks for a spec/plan for an issue in a host session.
---

# DESIGN phase on the host (split host/container)

## 0. Topology and role

DESIGN (gates A/B/C — restructured 2026-09-18; board: `In Design` → `Ready to IMPL` + the `gate` field, §2) is this interactive zcode host session. IMPL (G3–G7) is the opencode container (@manager/@architect) — we do not go there. The session merges the manager+architect roles for DESIGN: talks to the user at the gates and dispatches subagents **one level deep** (the scout; the spec panel and the plan reviewer are host-agent dispatches in this seed — a consuming project may swap them for a container panel runner, as memo does; the canon gate flow does not change).

Only what is pushed/flipped crosses the seam (git + board). Workflow canon: `docs/workflow/design-phase.md` (gate model, divergence filter, Gate B message format, fast-track) + `impl-phase.md` — this file carries the host mechanics only.

## 1. Session start (ritual)

1. Card returned from IMPL? First `gh issue view N --comments` (read-only) — a comment is the input: re-run the affected gates, not everything from scratch.
2. Git pre-flight (in the project repo): `git fetch origin && git status -sb`
   - behind → `git pull --ff-only`, continue;
   - **diverged (ahead+behind) → STOP**: show the user, reset nothing.
3. Board: the design kickoff is `pick-next-design` (§7) → an issue number (the best OPEN `Backlog` card by priority) or `NONE (reason)`. `NONE (design slot busy: …)` — another design is in flight: one design at a time, take nothing new. Show the picked card to the user.
4. The user picks an issue → `status N "In Design"`. Entering `In Design` stamps the host field automatically (arg > `GH_BOARD_HOST` env > container label file — on the host pass the arg explicitly; this host is `imac`). Guard: the issue must not sit in `In IMPL` — one issue lives in one phase at a time.
5. **Scout (pre-design recon) — by dispatch, not by hand.** Right after the issue is picked, dispatch built-in read-only subagents to gather facts (zcode — `Explore`; a cheap model is these agents' default). Default is **one**; wide scope (many subsystems / dependency issues) — several in parallel, one per zone, in a single Agent-tool message. The prompt: issue number, what the issue claims, what to verify against the live tree (dependencies, consumers, patterns) — plus an **actuality check**: is the gap the issue describes still there, claim-by-claim against live code and recently merged PRs.
   - Back comes a **compact fact sheet**: key files' structure/size vs the issue's claims; every claim confirmed/denied with `file:line`; dependency issues' state (open/closed + a one-line delta); consumer inventory; ready patterns to reuse; ending with the **actuality verdict**: `actual` / `partially stale` / `stale`.
   - **Stale-issue auto-close (2026-09-18, user decision):** verdict `stale` — every load-bearing claim of the issue contradicted by the live tree AND the described gap verifiably gone (already implemented or fully superseded; cite `file:line` and the PR/merge that closed it). The main session FIRST re-verifies 1–2 load-bearing claims itself against the code (scout reports err in paths); confirmed → comment the evidence on the issue, `gh issue close N --reason "not planned"`, board card → `Not planned`, report in this session. A wrong close is one click to reopen. A doubtful verdict never closes: comment what is off and keep designing. `partially stale` → correct the stale claims in an issue comment and bake the corrections into the concept and spec; the issue body itself is not edited.
   - Until Gate A the main session reads **only scout reports** — as-is, no raw merging. No raw file bodies or grep dumps into its context (`gh issue view` on dependencies goes to the scout too). Rationale: the main session's context is expensive and lives the whole session (Gate A → Gate C); recon garbage in it is dead weight (issue #14: ~10 tool calls and a 577-line file read to produce a ~40-line concept).
   - A spot check during the Gate A dialogue (one grep / one file section) is fine by hand; bulk recon — scout only.
6. **Step-0 report + Gate A.** The design turn's first user-facing message opens with the **step-0 block** — the issue retold for a reader who has not opened it. Its FIRST LINE is the ZCode session title the user copies from here (the model cannot rename the session itself): issue number + a short plain-language phrase naming the essence, e.g. «296 лишний запрос отмененного поиска». Then: the issue as a user scenario (who does what, what changes for them — plain words, no jargon); the problem it solves. No keywords list — dropped 2026-10-08 by user decision (the title line replaced it). Then Gate A (§2): candidate approaches → auto-OK, or the divergence stop. There is no separate interactive question-by-question dialogue.

## 1.5 Session rules (talking to the user)

- A message ending in `?` is a question: answer in text, **no actions** (tools, commits, file edits). Exception: the answer needs data not in context — read-only gathering (read a file, `git log`), then an immediate text answer.
- **Report before answer**: a new message does not cancel an unread work result. First the result as a status block — a **markdown list**, one item per line (bold items on adjacent lines without blank lines collapse into a single rendered line; "Files changed" / "Evidence" items dropped 2026-09-18 by user decision, as in `~/.zcode/AGENTS.md`):
  - **Status:** `DONE | DONE_WITH_CONCERNS | BLOCKED | awaiting user OK`
  - **Open questions** or an explicit "OK to mark this done?"
  Then the answer to the new message. If no dispatches happened since the user's last message and nothing awaits their decision — say "no outstanding tasks" and answer immediately. Edits in the current turn — the final message must summarize them.

## 2. Gates (A and C auto by default; B always the user's; the card sits in `In Design` for the whole design — the `gate` field marks the pending ask; the only design flip is → `Ready to IMPL` at Gate C)

Restructured 2026-09-18 by user decision: the old interactive concept gate and the plan-approval gate are replaced by auto gates; the panel-reviewed spec at Gate B is the main human gate. Board statuses: `In Design` — ALL design work, gates A/B/C live here; `Ready to IMPL` — plan pushed, the IMPL start signal. Board shape (statuses, fields, option lists): `docs/board/board-etalon.md`.

| Gate | Decides | User stop only when | After the gate |
|---|---|---|---|
| A — concept | what we build / deliberately do NOT (scope boundaries) | ≥2 concepts remain divergent after the filter below | auto-OK → the spec is written, no stop. Divergence stop → `gate N concept` |
| B — spec | the spec — after the panel's consolidated report and fixes | always — the user's OK is mandatory | `gate N none`; commit + **push** the spec; the card stays `In Design` |
| C — plan | the plan — after plan-reviewer | the plan forces a spec change | auto-OK: fixes folded in; commit + **push** the plan; card → `Ready to IMPL` — the flip clears the gate and the host automatically. Stop → `gate N plan`. Gate C is the last point where the discussion may still return to Gate A |

### The gate field (the pending ask is a single-select field on the board card, not a label and not a board status)

- Exactly one value may sit in the field: `concept` / `spec` / `plan` (a design stop) or `blocked` (an IMPL blocker awaiting the user — set by the container manager); set together with the stop message via `gh_board.py gate N <value>`, cleared (`gate N none`) the moment the user answers (a new stop replaces the old value). Empty + `In Design` = the agent is working, nothing awaits the user. Leaving `In Design`/`In IMPL` via `status` clears the gate (and the host) automatically — entering `PR (G7)` clears the gate but keeps the host — so no manual clear is needed before a flip.
- One writer: only the design session of that issue touches its gate value.
- Read–check–repair: on any session start and on return from IMPL, cross-check (status × gate) against git — the spec on main = Gate B passed, the plan on main = Gate C passed. On mismatch git wins: repair the gate/status and say so out loud.
- `gh_board.py status` matches option names exactly (`In Design`, `Ready to IMPL`); pickers match by prefix. Agents never rename or add board options (2026-09-09 incident).

### Gate A divergence filter (run before any user stop)

1. Eliminate an approach that violates a rule the repo already fixes — name the rule (domain-rules, design-system, the layer invariant, board conventions).
2. Eliminate an approach that re-implements a mechanism the scout found in the live tree — reuse wins.
3. Approaches differing only in internals (file layout, naming, UI micro-layout, refactor shape) are one approach — auto-OK.
4. Approaches are **divergent** — the user picks — when they differ in any of: user-visible behavior; data model (tables, columns, migrations); API contract (endpoints, payloads, semantics); scope (one of them deliberately does NOT build part of the issue); reversibility (breaking or one-way change).
5. Never present more than three; merge near-identical ones first. In doubt — stop for the user: a wasted stop is cheaper than a silently wrong choice.

**Gate B message format** — plain words, no jargon, no unexplained abbreviations; self-contained (understandable without opening any file):
1. step-0 block (skip if already shown at Gate A);
2. chosen concept + why, briefly — stated even when auto-selected;
3. **Behavioral Delta**, from the spec (§3);
4. technical summary of the finished spec — what changes, where, how it is tested;
5. premises of the issue that the recon corrected (if any) — what differs from the issue text and why;
6. panel outcome in one line;
7. remaining assumptions as open questions;
8. spec path.

**Fast-track exception (docs-only issues):** an issue whose diff touches only docs/prose may skip the container IMPL session entirely; a diff touching anything executable — `scripts/`, `.github/workflows/`, agent or skill bodies, site build — disqualifies fast-track and forces the normal plan-reviewed path (the watcher auto-pulls main every cycle and executes harness files from it, so a fast-tracked merge must never carry executable changes that skipped plan review). Gates A/B unchanged, Gate C collapsed by default — the spec carries a `## Verification` section (mechanical checks) instead of a plan artifact; keep the plan only for ≥3-task decompositions or verification that needs design (user decides at Gate B). The host session implements right after the gates; spec/plan (if any) land in the change PR; the card goes `In IMPL` while the PR is open → `In-main` on merge and never sits in `Ready to IMPL`; `Closes #N` belongs in the PR description only; no handoff message. Full details: `docs/workflow/design-phase.md` §Fast-track.

## 3. Artifacts

- Spec: `docs/specs/YYYY-MM-DD-<feature>-design.md`. Must include a `## User Scenarios` section — 3–7 user tasks the feature enables, each mapping to an E2E test (anchors the plan's E2E-in-DoD rule; the completeness panelist checks it) — and a `## Behavioral Delta` section — what changes for the user, before → after (written at spec time, so the panel reviews it and Gate B prints it). **Self-contained BEFORE the panel**: the panel does not read GH issues — the scope check against the issue is done by the main session itself, with findings baked into the spec text.
- Fast-track specs additionally carry a `## Verification` section (mechanical checks instead of E2E — see §2 fast-track exception).
- Plan: `docs/plans/YYYY-MM-DD-<feature>-plan.md` per the writing-plans conventions (canon: `.opencode/skills/writing-plans/SKILL.md`):
  - header: Goal / Architecture / Tech Stack; the behavioral delta lives in the spec's `## Behavioral Delta` (2026-09-18) — a plan task implements a User Scenario, it does not restate behavior;
  - every task anchor: `## Task N: <name>` + `### Classification: trivial|small|standard|large`; after commit, never renumber anchors;
  - every task carries `### Required Docs` (domain-rules for entities, design-system for UI);
  - a task implements a User Scenario (from the spec's `## User Scenarios`) → its DoD line: "E2E test for scenario N passes (RED-GREEN-REFACTOR)";
  - no placeholders ("TBD", "add validation" — that is a plan failure).
- Domain rules changed → `docs/domain-rules/` is committed together with the spec.

## 4. Panel (host dispatch of the spec-panel agents)

1. Dispatch: **6 agents in parallel**, in a single Agent-tool message: `spec-panel-completeness`, `spec-panel-consistency`, `spec-panel-feasibility`, `spec-panel-simplicity`, `spec-panel-best-practices`, `spec-panel-security` (files in the repo's `.zcode/agents/`, models per their headers).
2. Each prompt: the **spec path** (+ the previous spec revision's path, if there was one). No `gh issue view`, no network — except best-practices, whose design includes WebSearch/WebFetch.
3. Aggregation: dedupe identical findings → rank **BLOCKER > MAJOR > MINOR** → one consolidated report to the user for the fix decision. Before trusting a finding, verify it against the code — panelists err in paths.
4. **Availability policy:** a panelist did not return / crashed / returned an empty report → **one** rerun of that agent alone; second failure → mark it `skipped` in the consolidated report, verdict on the rest.
5. best-practices returned `Verdict: FAILED` (web research unavailable) → note it in the report and exclude it from the verdict — that is its designed refusal, not a crash.
6. The agent registry is seeded only at session start: `Agent tool: not found` while `.zcode/agents/` files exist → restart the session.
7. A consuming project that runs the panel in the opencode container (as memo does) replaces this section with its panel-runner mechanics; the aggregation rules are unchanged.

## 5. Gate C — plan review

Dispatch `plan-reviewer` (files in `.zcode/agents/`): the prompt carries the spec path + the plan path; the reviewer reads both itself. No spec-changing findings → Gate C auto-OK: fold the fixes into the plan text, commit + push, board → `Ready to IMPL` (the flip clears the gate and the host automatically) — no user stop. The closing report lists the plan's tasks, one line each, plus the spec/plan paths. Findings that change the spec (from the reviewer or from writing the plan itself) → STOP: `gate N plan`; what was found, why the spec changes, the proposed fix — the user decides; this is the last point where the discussion can still return to Gate A.

## 6. DESIGN session DoD (the seam contract)

- Only **git and the board** cross the seam. The session does NOT end holding local commits: every passed gate = commit + push to origin/main.
- **No closing keywords in direct-to-main commits.** Spec/plan/harness commit messages must NOT contain `Closes/Fixes/Resolves #N` — GitHub auto-closes the issue the moment the commit lands, though no IMPL has started. Write "to be closed by the IMPL PR" instead. The closing keyword belongs only in the IMPL PR description.
- **Issue bodies declare hard dependencies as a `depends-on: #N, #M` line** — empty for independent tasks; examples only inline in backticks, because any line-start `depends-on:` is parsed as a real declaration (`gh_board.py` parses it in both harness copies) and the pickers skip the card while a referenced issue is OPEN.
- **All decisions are folded into the artifact texts**: review amendments, constraints like "#NNN strictly after #NNN — shared file" go into the spec/plan, not the chat. Git and the board carry no session context across the seam. This is the DESIGN DoD under Scratchpad Discipline v2: DESIGN writes zero scratchpad state, so the pushed spec/plan are the ONLY carrier — fold every decision and dependency in **before the phase closes**.
- After Gate C tell the user: «скажи менеджеру в opencode: start impl #NNN». The container needs nothing else.
- Does NOT cross the seam: `.opencode/scratchpad.md` (the container seeds its section at IMPL start — DESIGN itself writes nothing, v2), worktrees, env. In this seed there are no container operations during DESIGN at all — the panel and the plan reviewer run as host dispatches.

## 7. Board (the script ships with the adapters)

```bash
python3 .zcode/scripts/gh_board.py show 247                     # read one card; `show all` = whole board
python3 .zcode/scripts/gh_board.py pick-next-design             # kickoff token: <issue> | NONE (reason)
python3 .zcode/scripts/gh_board.py status 176 "Ready to IMPL"   # leaving In Design/In IMPL clears the host and gate fields automatically
python3 .zcode/scripts/gh_board.py gate 176 plan                # set the pending-ask marker; `none` clears
```

- The script ships with the adapters: `.zcode/scripts/` (host copy) and `.opencode/scripts/` (container copy) in the project repo, kept byte-identical. Project identity is NOT baked into the script: it comes from `docs/board/board_config.json` (generated by `board_bootstrap.py adopt`, never hand-set). No extra copies outside the harness folders.
- **No raw-GraphQL fallback.** ALL board interaction — reads and writes — goes through the script; never hand-write `gh api graphql` against the project. Field-definition mutations (`updateProjectV2Field`: adding/renaming status options) are forbidden for agents: the mutation replaces the whole option list and detaches every card's value (2026-09-09: 65/69 cards lost Status this way). A new status is added by the user in the GitHub web UI, which appends safely. Exception: `board_bootstrap.py` is the rollout-time board writer (create/link/seed during repo setup only).
- One writer per issue: DESIGN flips (`In Design` → `Ready to IMPL`; inside the design the pending gate is the `gate` field value, §2; fast-track goes straight to `In IMPL`) — this session; IMPL flips — the container manager. The script adds an issue to the board on first contact.

## 8. Rules

- One issue = one phase at a time; the board is the guard. DESIGN on X + IMPL on Y in parallel — allowed.
- One DESIGN session = one issue.
- Parallel DESIGN sessions (different issues, different host sessions): simultaneous push → `git pull --rebase`.
- Return from IMPL: the card goes to `In Design` + an issue comment — a broken spec restarts the design, a broken plan additionally sets `gate N plan` (decision needed); that is a new DESIGN session's starting point (§1).
- DESIGN-phase agents and skills live **in this repo**: `.zcode/agents/` + `.zcode/skills/` — `design-phase` (the phase protocol) and `brainstorming` (standalone explicit-invocation dialogue — «побрейнштормим»; since the 2026-09-18 gate restructure no design gate routes through it). Superagents canon: agent bodies — `.opencode/agents/`, reference seed of host ports — `.zcode/agents/`; a canon change is ported by editing the files in `.zcode/agents/` (the port is marked in each file's header). The omniroute model catalog is the local `~/.zcode/v2/config.json` (with keys — never committed).
