# DESIGN Phase — runs on the host in ZCode

> **Audience:** humans — this is the human-readable reference for the DESIGN phase.
>
> **Where it runs:** an interactive **host session in ZCode**. One session combines the manager and architect roles: it talks to the user at the gates and dispatches review subagents (one level, no nesting).
>
> **Input:** an issue picked from the GitHub Project board. **Output:** an approved spec + plan, **pushed to origin/main**. The [IMPL phase](impl-phase.md) picks it up in the opencode container.
>
> **Version:** 3.10 · **Last aligned:** 2026-09-17

Executors: the project's `.zcode/` — skills **`design-phase`** (the actual protocol this page summarizes) and **`brainstorming`** (the G1a dialogue: questions → approaches → concept; explicit-only trigger — dispatched by `design-phase`, or `/brainstorming`), agents **`spec-panel-*`** ×6 and **`plan-reviewer`**, script **`.zcode/scripts/gh_board.py`** (board). Seed source: this repo's [`.zcode/`](../../.zcode/).

## At a glance

| Step | Gate | Who decides | Executors |
|------|------|-------------|-----------|
| 0. Brainstorm the concept | G1a — concept | **Human** | host session |
| 1. Spec + panel review | G1b — spec | **Human** | host session + `spec-panel-*` ×6 |
| 2. Plan + plan review | G2 — plan | **Human** | host session + `plan-reviewer` |

Legend: **Human** = requires a user decision (pause); `▼` = automatic transition.

## Flow

```
╔══════════════════════════════════════════════════════════════╗
║  STEP 0: BRAINSTORMING  (host session + user, interactive)   ║
║  Human Gate G1a (design concept)                             ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Session-start ritual: pre-flight git (fetch;
         │    behind → pull --ff-only; diverged → STOP + user),
         │    board next-up, user picks an issue
         │ 2. Card → "In Design (G1a)"
         │ 3. Scout: dispatch read-only explorer subagent(s)
         │    (zcode: `Explore`; opencode: `explorer`) → compact
         │    fact sheet, every claim cited file:line
         │ 4. Session reads the scout report → clarifying
         │    questions → propose 2-3 approaches → present
         │    concept: what we build / what we deliberately do NOT
         │    (+ User Scenarios list, 3-7 tasks)
         │
         ▼  [G1a: USER APPROVES THE CONCEPT]
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 1: DESIGN SPEC  (Human Gate G1b)                        ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Write spec → docs/specs/YYYY-MM-DD-<feature>-design.md
         │    (self-contained BEFORE the panel: panelists get the
         │    spec path only — they do not read GitHub issues)
         │    Must include ## User Scenarios — 3-7 tasks, each → E2E
         │ 2. Self-review (placeholders, consistency, scope)
         │ 3. Spec Panel Review: 6 parallel independent agents
         │ 4. Consolidated report → user decides on fixes
         │
         ▼  [G1b: USER APPROVES THE SPEC]
         │
         │    commit + PUSH spec; board → "Spec OK (G1b)"
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 2: WRITING PLANS  (Human Gate G2)                       ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Plan per the writing-plans skill conventions:
         │    Task anchors + classification (trivial/small/
         │    standard/large), Behavioral Delta, Required Docs,
         │    E2E-in-DoD, no placeholders
         │ 2. Plan review by `plan-reviewer` (plan vs spec)
         │ 3. Review amendments folded INTO the plan text
         │
         ▼  [G2: USER APPROVES THE PLAN]
         │
         │    commit + PUSH plan; board → "Ready to IMPL (G2)"
         │
         ▼  HANDOFF: user tells the container manager
             «продолжаем траекторию #NNN». Nothing else crosses.
```

## Scout (pre-G1a recon)

All fact gathering before G1a — the issue and its dependencies, the code under change, consumers, existing patterns — is done by **dispatched read-only explorer subagents** (zcode built-in `Explore`; the opencode counterpart is `explorer`; both default to cheap models), never by the main session. Default is **one** scout; for wide scope (many subsystems or dependency issues) dispatch several in parallel, one per zone — each returns the same compact contract for its zone, and the session reads the reports as-is, no raw merging. A scout returns a **compact fact sheet**: current file size/structure vs the issue's claims, every finding confirmed/denied with `file:line`, dependency issues state (open/closed + one-line delta), consumer inventory, patterns to reuse.

The main session keeps: pre-flight git, board flips, reading the scout report — plus targeted single look-ups (one grep, one file section) when the G1a dialogue asks for them. Bulk recon is scout-only: the main window is the expensive one and it has to stay lean from G1a through G2 (issue #14: an in-session recon cost ~10 tool calls and a 577-line file read to produce a ~40-line concept — the raw output then rode the window for the rest of the session).

## Board during DESIGN

The GitHub Project card walks `In Design (G1a) → Spec OK (G1b) → Ready to IMPL (G2)`; the fast-track path branches off after G1b straight to `In IMPL` (see [Fast-track](#fast-track-docsharness-issues-no-impl-session)). Flip strictly at the gate moment, never by feel. One writer per issue: DESIGN-stage flips belong to the host session; IMPL-stage flips to the container manager.

## Spec Panel Review (G1b)

Six **independent parallel** perspectives, one agent each: `completeness`, `consistency`, `feasibility`, `simplicity`, `best-practices`, `security` (the best-practices one does web research; a `Verdict: FAILED` from it is its designed no-network refusal — excluded from the verdict, not counted as a crash).

The session aggregates: deduplicate identical findings, rank **BLOCKER > MAJOR > MINOR**, present ONE consolidated report; the user decides which fixes to apply. Availability policy: a panelist that fails to return is retried once, then marked `skipped` in the report — the verdict rests on the rest.

## Plan review (G2)

`plan-reviewer` verifies the plan faithfully and completely expands the approved spec. Its report goes to the user; accepted amendments and constraints are folded into the plan text itself (not left in chat).

## Done means pushed (the seam)

- Every passed gate = commit + **push to origin/main**. A DESIGN session never ends holding local commits.
- **All decisions live in the artifact texts**: review amendments, cross-trajectory constraints («#NNN strictly after #NNN — shared file») go into the spec/plan. Git and the board carry no session context across the host/container boundary.
- **Host-DESIGN DoD (Scratchpad Discipline v2)**: DESIGN — host and container — writes zero scratchpad state, so the pushed spec/plan are the ONLY carrier of decisions and dependencies: fold them in before the phase closes.
- Explicitly NOT crossing the seam: `.opencode/scratchpad.md` (no exception section, even for an in-flight container DESIGN — crash recovery is manual from the DB/board/spec), worktrees, env state.

## Return path (re-entry from IMPL)

If IMPL hits a problem that invalidates the spec or the plan, the card bounces back (`In Design (G1a)` for a broken spec, `Spec OK (G1b)` for a broken plan) with a GH issue comment describing the problem — see [impl-phase.md](impl-phase.md). A **new** DESIGN session starts from that point: read the issue comments first, re-run only the affected gates, not everything from scratch.

## Gates summary

```
G1a ─── Design Concept Approval ─── Human ── Concept approved, scope in/out
G1b ─── Written Spec Approval ───── Human ── Spec + panel report reviewed
G2 ─── Plan Approval ─────────── Human ── Plan + review, pushed to main
```

## Fast-track: docs/harness issues (no IMPL session)

An issue that touches **only** documentation (`docs/`) or the harness
(`.zcode/`, `.opencode/` — no application code) may skip the container IMPL
session entirely and be implemented by the host DESIGN session itself
(precedents in memo: #107, #287).

- **Trigger:** the user opts in at any gate; the session recommends the
  fast-track for a pure docs/harness issue by default.
- **Gates:** G1a and G1b unchanged — the concept and the spec (with the
  panel) still apply. **G2 is collapsed by default:** no plan artifact for
  the fast-track; the implementation order and the verification design live
  in a `## Verification` section of the spec — mechanical checks (greps,
  path/line existence, coverage lists); the E2E-in-DoD rule does not apply
  (no app surface). Write the plan anyway when the change decomposes into
  ≥3 independent tasks or the verification itself needs design — the
  user decides at G1b.
- **Seam:** gate pushes are replaced by the PR — the spec (and plan, if
  any) commit together with the change itself. The session still never
  ends holding local commits.
- **Board:** the card never sits in `Ready to IMPL (G2)` — the auto-impl
  pipeline has nothing to claim. While the PR is open the card goes to
  `In IMPL` (the host session acts as the executor); after merge →
  `In-main`.
- **Closing:** the PR description carries `Closes #N` — the only sanctioned
  place for the closing keyword; commit messages stay keyword-free.
- **Handoff:** none — do not say «продолжаем траекторию» for a fast-tracked
  issue.
