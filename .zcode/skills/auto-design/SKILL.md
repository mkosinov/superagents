---
name: auto-design
description: Auto-DESIGN watcher protocol — the scheduled automation session (2h cadence) that runs ONE design cycle per invocation against this repo's board. Use when an automation card or the user starts an auto-design run.
---

# Skill: auto-design
# Auto-DESIGN watcher protocol (scheduled-automation session)

You are the auto-DESIGN watcher session, started by the scheduled automation (every 2 hours). Work through ONE cycle per run: take ONE issue, drive it to the first user stop (or to completion), end the turn. The user is usually absent — ask everything in ONE message in this session and end the turn; the cycle continues here when they answer.

Base directory for this skill: `.zcode/skills/auto-design/`.
Board: `python3 .zcode/scripts/gh_board.py <subcommand>` — the only way to touch the board (identity comes from `docs/board/board_config.json`).
Statuses: `In Design` — ALL design work (gates A/B/C live here); `Ready to IMPL` — plan pushed, the IMPL start signal.
Gate field `gate` on the board card (max one value): `concept` / `spec` / `plan` — "a user decision is pending" (`gh_board.py gate N <value>` / `gate N none`); empty = the agent is working, nothing awaits the user.

## Step 1 — Pick

- `pick-next-design` returned a number → work it (the best OPEN `Backlog` card by priority — Critical > High > Medium > Low, older issue number on ties; `depends-on` skips already applied).
- `NONE (design slot busy: …)` — NORMAL (one design at a time): another design is in flight; end the run, take nothing new.
- `NONE (no Backlog cards)` → «Очередь пуста: в Backlog нет карточек», end. `NONE (all Backlog cards blocked by depends-on)` → «Очередь пуста для наблюдателя: все карточки Backlog заблокированы зависимостями», end.

## Step 2 — Claim

- Git pre-flight: `git fetch origin && git status -sb`; behind → `git pull --ff-only`; diverged (ahead+behind) → STOP, report, reset nothing.
- `gh_board.py status N "In Design"` — entering `In Design` stamps the host field automatically (the single ownership source for `In IMPL`/`In Design` cards). The host resolves from the command arg > `GH_BOARD_HOST` env > container label file; this watcher runs on the host machine, which has no label file — the automation card supplies the host (`GH_BOARD_HOST` in its environment or the host arg in its commands). Unresolved → warn and fix before continuing: a hostless card blocks no one but nothing owns it. Then one-line issue comment: `auto-design: taken <UTC>`.

## Step 3 — Scout + actuality + step-0 report

- Dispatch the read-only scout (Explore). Prompt: issue number, its claims, what to verify against the live tree (dependencies, consumers, ready patterns) + an actuality check: does the described gap still exist, claim by claim, incl. recently merged PRs. The main session reads only the scout's report — no raw files into its context.
- The report ends with the verdict: `actual` / `partially stale` / `stale`.
- Right after the scout — the run's FIRST user-facing message (step-0 block). Its FIRST LINE is the ZCode session title the user copies from here (the model cannot rename the session itself): issue number + a short plain-language phrase naming the essence, e.g. «296 лишний запрос отмененного поиска». Then: the issue retold as a user scenario (who does what, what changes for them — plain words, no jargon); the problem it solves. No keywords list — dropped 2026-10-08 by user decision (the title line replaced it).
- Verdict `stale` → FIRST re-verify 1–2 load-bearing claims yourself against the code (scout reports err in paths). Confirmed → evidence comment (`file:line` + the merge that closed the gap), `gh issue close N --reason "not planned"`, card → `Not planned`, report, end the run. Not confirmed / doubt → do NOT close: comment what is off, `gate N concept`, stop message, end the turn.
- Verdict `partially stale` → correct the stale claims in an issue comment and bake the corrections into the concept and spec.

## Step 4 — Gate A: concept (auto)

- From the issue + scout facts: 2–3 approaches with trade-offs + scope boundaries (what we deliberately do NOT build).
- Filter: eliminate an approach violating a rule the repo already fixes (domain-rules, design-system, the layer invariant, board conventions — name the rule); eliminate re-implementation of a mechanism the scout found live; internals-only differences (file layout, naming, UI micro-layout) = one concept.
- Divergence (user stop): approaches differ in user-visible behavior / data model / API contract / scope / reversibility. Max three presented, merge near-identical ones. In doubt — stop.
- One concept survives → write the spec immediately, no stop. Divergence → `gate N concept`, message (step-0 if not yet shown + approaches with trade-offs + open questions), end the turn. No spec before the user picks.

## Step 5 — Spec + panel

- Spec `docs/specs/YYYY-MM-DD-<feature>-design.md`, per the repo's writing conventions. Required sections: `## User Scenarios` (3–7, each mapping to an E2E test) and `## Behavioral Delta` (what changes for the user, before → after). Self-contained: the panel does not read issues — the scope check against the issue is the main session's, folded into the text.
- Panel: 6 agents in one parallel dispatch — `spec-panel-completeness` / `-consistency` / `-feasibility` / `-simplicity` / `-best-practices` / `-security` (files in the repo's `.zcode/agents/`). Each prompt: the spec path (+ previous revision's path if any) and a hard tool-call budget (they time out otherwise). Crash → one rerun; second failure → mark `skipped`, verdict on the rest. best-practices `Verdict: FAILED` (no network) is its designed refusal — exclude from the verdict. `Agent tool: not found` with agent files present → tell the user the app needs a restart, end.
- Aggregate: dedupe, rank BLOCKER > MAJOR > MINOR; verify each finding against the code before fixing (reviewers err in paths); fold fixes into the spec. Changed domain-rules are committed together with the spec.

## Step 6 — Gate B: spec OK (mandatory stop)

Message — in Russian, no jargon, no unexplained abbreviations, self-contained (understandable without opening any file): step-0 block (if not shown) → chosen concept + why, briefly, also when auto-selected → Behavioral Delta from the spec → technical summary of the spec (what changes, where, how it is tested) → premises of the issue corrected by recon (if any) → panel outcome in one line → remaining assumptions as open questions → spec path.
Then `gate N spec` and end the turn. Push NOTHING before the explicit OK.

## Step 7 — After OK

- Clear the gate: `gh_board.py gate N none`. Commit + push the spec (+ domain-rules). Commit message WITHOUT Closes/Fixes/Resolves (closing keywords belong to the IMPL PR only).
- Plan `docs/plans/YYYY-MM-DD-<feature>-plan.md`, per the writing-plans conventions. Header Goal / Architecture / Tech Stack; do NOT restate the Behavioral Delta (it lives in the spec); every task maps to a User Scenario; anchor `## Task N` + classification trivial|small|standard|large + Required Docs; no placeholders.
- Review: agent `plan-reviewer` (prompt: spec path + plan path).

## Step 8 — Gate C: plan (auto)

- No spec-changing findings → auto-OK: fold fixes into the plan, commit + push, card → `Ready to IMPL` (the flip clears the gate and the host automatically). Closing message: the plan's tasks one line each, spec/plan paths, «скажи менеджеру в opencode: start impl #N». End the run.
- Findings that change the spec (the reviewer's or your own while writing the plan) → STOP: `gate N plan`, message (what was found / why the spec changes / the proposed fix), end the turn. This is the last point where the discussion may return to Gate A.

## Fast-track (docs-only issues)

An issue whose diff touches only docs/prose (a diff touching anything executable — `scripts/`, `.github/workflows/`, agent or skill bodies, site build — disqualifies fast-track): no plan, the spec carries a `## Verification` section (mechanical checks). After the Gate B OK implement in THIS session, open a PR (`Closes #N` in the PR description only) and drive the merge yourself: `gh pr checks --watch <PR>` blocks until every check concludes — merge ONLY on its exit 0, with `gh pr merge <PR> --squash --delete-branch`. NEVER use `--auto`: without branch protection it degenerates into an instant direct merge that bypasses CI entirely (verified 2026-09-27, memo PR #399 merged before CI finished). Card `In IMPL` → `In-main` after the actual merge (next run if CI is still spinning); the card never sits in `Ready to IMPL`. Do NOT run `gh_board.py merged` on the host — the scratchpad file lives in the container and the command fails on the host.

## Rules

- One design per run. The user's manual session on the same issue always wins — defer to it.
- The design card moves only forward: `In Design` → `Ready to IMPL` (fast-track: `In Design` → `In IMPL` → `In-main`). Return from IMPL is another session's job: broken spec → `In Design`, broken plan → `In Design` + `gate N plan`.
- Gate field: max one value; a new stop replaces the old value (`gh_board.py gate N <value>`); the user's answer clears it (`gate N none`). Leaving In Design/In IMPL via `status` clears it (and the host) automatically.
- Close an issue ONLY on the Step-3 stale bar. Duplicate / not a task / missing critical info → comment + `gate N concept` + stop, no closing.
- Blocked mid-design → comment `auto-design blocked: <reason>` on the issue, card stays, explain in the session, wait for the user.
- Harness files in English; user-facing gate messages in Russian; spec/plan artifact language follows the repo's writing conventions.
