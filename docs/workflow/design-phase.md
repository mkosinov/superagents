# DESIGN Phase — concept → spec → plan (interactive)

> **Audience:** humans — this is the human-readable reference for the DESIGN phase.
>
> **Where it runs:** an **interactive session** — it talks to the user where a gate requires a decision and dispatches review subagents (one level, no nesting). Current adapter: a ZCode host session (see [Executors](#executors-adapters)).
>
> **Input:** an issue picked from the GitHub Project board. **Output:** an approved spec + plan, **pushed to origin/main**, card at `Ready to IMPL`. The [IMPL phase](impl-phase.md) picks it up.
>
> **Version:** 3.12 · **Last aligned:** 2026-10-07 (gate model A/B/C — back-port of the live 2026-09-18 restructure)

## Executors (adapters)

The theory below names roles and artifacts, never tools. Adapters own the mechanics (dispatch tools, agent/skill formats, scripts, paths, model assignments) and reference this canon without re-telling it.

| Theory role | Current adapters |
|---|---|
| DESIGN session orchestration | zcode host session — skill `design-phase` |
| Scout (read-only explorer) | zcode built-in `Explore`; opencode `explorer` |
| Spec panel ×6 | agents `spec-panel-*` — currently run in the opencode container through a panel-runner script; host dispatch is the fallback |
| Plan reviewer | agent `plan-reviewer` — same container runner |
| Standalone brainstorm dialogue | skill `brainstorming` — explicit invocation only; **no gate routes through it** |
| Board | script `gh_board.py` (shipped with each adapter) |

## Gate model: A / B / C

Since 2026-09-18 (live practice, back-ported into this canon): the old interactive concept gate and the human plan-approval gate are replaced by **auto gates**; the panel-reviewed spec is the **single mandatory human gate**.

| Gate | Decides | Type | Stops the user only when | After the gate |
|---|---|---|---|---|
| **A — concept** | what we build / deliberately do NOT (scope boundaries) | auto | ≥2 concepts remain divergent after the [divergence filter](#gate-a--divergence-filter) | the spec is written; card stays `In Design` |
| **B — spec** | the spec — after the panel's consolidated report and fixes | **human — always** | always: the user's OK is mandatory | commit + **push** the spec; card stays `In Design` |
| **C — plan** | the plan — after the plan review | auto | the plan forces a spec change | fixes folded in; commit + **push** the plan; card → `Ready to IMPL`. The last point where the discussion may still return to Gate A |

The card sits in `In Design` for the whole design; the **pending ask is visible on the card** (the current board adapter implements it as a single-select `gate` field — `concept` / `spec` / `plan` — set with the stop message, cleared the moment the user answers). The only design flip is → `Ready to IMPL` at Gate C.

## Flow

```
╔══════════════════════════════════════════════════════════════╗
║  STEP 0: SCOUT + CONCEPT  (Gate A — auto)                     ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Session-start ritual: pre-flight git (fetch;
         │    behind → pull --ff-only; diverged → STOP + user),
         │    board pick-next-design proposal, user picks an issue
         │ 2. Card → "In Design"
         │ 3. Scout: read-only explorer subagents → compact
         │    fact sheet + issue-actuality verdict
         │    (stale → evidence comment + close, §Scout)
         │ 4. Step-0 report (the issue retold) → candidate
         │    approaches → divergence filter
         │
         ▼  [A: auto-OK → the spec is written]
         │  (divergence stop → user picks)
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 1: SPEC + PANEL  (Gate B — HUMAN, the main OK)          ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Write spec → docs/specs/YYYY-MM-DD-…-design.md
         │    (## User Scenarios + ## Behavioral Delta;
         │    self-contained BEFORE the panel: panelists get
         │    the spec path only — they do not read GitHub issues)
         │ 2. Self-review (placeholders, consistency, scope)
         │ 3. Spec Panel Review: 6 parallel independent agents
         │ 4. Consolidated report → user decides on fixes
         │ 5. Gate B message (§Gate B) → the user's OK
         │
         ▼  [B: USER APPROVES THE SPEC]
         │
         │    commit + PUSH the spec
         │
╔══════════════════════════════════════════════════════════════╗
║  STEP 2: PLAN + REVIEW  (Gate C — auto)                       ║
╚══════════════════════════════════════════════════════════════╝
         │ 1. Plan per the plan-writing conventions:
         │    Task anchors + classification (trivial/small/
         │    standard/large), Required Docs, E2E-in-DoD,
         │    no placeholders (the plan does not restate the
         │    Behavioral Delta — it lives in the spec)
         │ 2. Plan review by the plan reviewer (plan vs spec)
         │ 3. Review amendments folded INTO the plan text
         │
         ▼  [C: auto-OK → commit + PUSH plan; card → "Ready to IMPL"]
         │  (spec-changing findings → stop → user)
         │
         ▼  HANDOFF: user tells the IMPL session manager
             «start impl #NNN». Nothing else crosses.
```

## Scout (pre-design recon)

All fact gathering — the issue and its dependencies, the code under change, consumers, existing patterns — is done by **dispatched read-only explorer subagents** (each adapter provides an explorer; both current ones default to cheap models), never by the main session. Default is **one** scout; for wide scope dispatch several in parallel, one per zone. A scout returns a **compact fact sheet**: structure/size of key files vs the issue's claims (every claim confirmed/denied with `file:line`), dependency issues state, consumer inventory, patterns to reuse — plus an **actuality check**: is the gap the issue describes still there, claim-by-claim against live code and recently merged PRs, ending with a verdict `actual` / `partially stale` / `stale`.

**Stale-issue auto-close:** verdict `stale` (every load-bearing claim contradicted by the live tree, the gap verifiably gone — already implemented or superseded) → the session first re-verifies 1–2 load-bearing claims itself (scout reports err in paths), then comments the evidence on the issue, closes it as not planned, and the card goes to `Not planned`. A doubtful verdict never closes: comment what is off and keep designing. `partially stale` → correct the stale claims in an issue comment and bake the corrections into the concept and spec; the issue body itself is not edited.

The main session keeps: pre-flight git, board flips, reading the scout report — plus targeted single look-ups (one grep, one file section) when the Gate A dialogue asks for them. Bulk recon is scout-only: the main window is the expensive one and it has to stay lean from Gate A through Gate C (issue #14: an in-session recon cost ~10 tool calls and a 577-line file read to produce a ~40-line concept).

## Gate A — divergence filter

Candidate approaches are filtered before any user stop. The gate auto-OKs when one approach survives; it stops the user only when ≥2 remain divergent.

1. Eliminate an approach that violates a rule the repo already fixes — name the rule (domain rules, design system, layer invariant, board conventions).
2. Eliminate an approach that re-implements a mechanism the scout found in the live tree — reuse wins.
3. Approaches differing only in internals (file layout, naming, UI micro-layout, refactor shape) are one approach — auto-OK.
4. Approaches are **divergent** — the user picks — when they differ in any of: user-visible behavior; data model; API contract; scope (one of them deliberately does NOT build part of the issue); reversibility (breaking or one-way change).
5. Never present more than three; merge near-identical ones first. In doubt — stop for the user: a wasted stop is cheaper than a silently wrong choice.

There is **no interactive question-by-question brainstorm** inside the design flow; the design turn opens with a **step-0 report** — the issue retold for a reader who has not opened it (number; 3–5 keywords; the issue as a user scenario; the problem it solves) — followed by the candidate approaches. The full brainstorm dialogue exists as the standalone `brainstorming` skill, explicit invocation only.

## Gate B — the human gate

The message at Gate B is plain words, no jargon, self-contained (understandable without opening any file):

1. step-0 block (skip if already shown at Gate A);
2. chosen concept + why, briefly — stated even when auto-selected;
3. **Behavioral Delta**, from the spec;
4. technical summary of the finished spec — what changes, where, how it is tested;
5. premises of the issue that the recon corrected (if any);
6. panel outcome in one line;
7. remaining assumptions as open questions;
8. spec path.

## Spec Panel Review (Gate B)

Six **independent parallel** perspectives, one agent each: `completeness`, `consistency`, `feasibility`, `simplicity`, `best-practices`, `security` (the best-practices one does web research; a `Verdict: FAILED` from it is its designed no-network refusal — excluded from the verdict, not counted as a crash).

The session aggregates: deduplicate identical findings, rank **BLOCKER > MAJOR > MINOR**, present ONE consolidated report; the user decides which fixes to apply. Before trusting a finding, verify it against the code — panelists read a clean clone and err in paths. Availability policy: a panelist that fails to return is retried once, then marked `skipped` in the report — the verdict rests on the rest.

## Plan review (Gate C)

The plan reviewer verifies the plan faithfully and completely expands the approved spec; accepted amendments are folded into the plan text itself (not left in chat). No spec-changing findings → **auto-OK**: fold, commit + push, card → `Ready to IMPL` — no user stop; the closing report lists the plan's tasks one line each. Findings that change the spec (from the reviewer or from writing the plan itself) → **stop**: `gate N plan`; the user decides — this is the last point where the discussion may still return to Gate A.

## Board during DESIGN

The board is the project's state visualizer, not a context carrier. Statuses: `In Design` — ALL design work, gates A/B/C live here (the pending ask is the card's gate marker, set at a stop and cleared on the user's answer); `Ready to IMPL` — plan pushed, the IMPL start signal. The only design flip is → `Ready to IMPL` at Gate C, strictly at the gate moment. One writer per issue: DESIGN-stage flips belong to the DESIGN session; IMPL-stage flips to the IMPL session. The fast-track path branches straight to `In IMPL` (see [Fast-track](#fast-track-docs--harness-issues-no-impl-session)).

## Done means pushed (the seam)

- Every passed gate = commit + **push to origin/main**. A DESIGN session never ends holding local commits.
- **No closing keywords in direct-to-main commits**: spec/plan/harness commit messages must NOT contain `Closes/Fixes/Resolves #N` — GitHub auto-closes the issue the moment the commit lands, though no IMPL has started. Write "to be closed by the IMPL PR" instead; the closing keyword belongs only in the IMPL PR description.
- **All decisions live in the artifact texts**: review amendments, cross-trajectory constraints («#NNN strictly after #NNN — shared file») go into the spec/plan; a return-path problem goes into the issue comment. The board is not a carrier — it visualizes pipeline state; no session context crosses the DESIGN/IMPL boundary through it.
- **DESIGN DoD (Scratchpad Discipline v2)**: DESIGN writes zero scratchpad state, so the pushed spec/plan are the ONLY carrier of decisions and dependencies: fold them in before the phase closes.
- Explicitly NOT crossing the seam: the IMPL scratchpad file, worktrees, env state.

## Return path (re-entry from IMPL)

If IMPL hits a problem that invalidates the spec or the plan, the card returns to `In Design` with a GH issue comment describing the problem — see [impl-phase.md](impl-phase.md). A broken spec restarts the design (Gate A); a broken plan additionally marks a pending plan decision on the card — the new DESIGN session resumes at Gate C. Either way: read the issue comments first, re-run only the affected gates, not everything from scratch.

## Gates summary

```
A ─── Concept ──── auto ──── scope in/out; user only if approaches diverge
B ─── Spec ─────── Human ─── panel report reviewed; the phase's main OK
C ─── Plan ─────── auto ──── review folded in; user only if the plan changes the spec
```

## Fast-track: docs / harness issues (no IMPL session)

An issue that touches **only** documentation (`docs/`) or the harness/adapter
files (this repo: `.zcode/`, `.opencode/` — no application code) may skip the
IMPL session entirely and be implemented by the DESIGN session itself
(precedents in memo: #107, #287).

- **Trigger:** the user opts in at any gate; the session recommends the
  fast-track for a pure docs/harness issue by default.
- **Gates:** A and B unchanged — the concept filter and the spec (with the
  panel) still apply. **Gate C is collapsed by default:** no plan artifact for
  the fast-track; the implementation order and the verification design live
  in a `## Verification` section of the spec — mechanical checks (greps,
  path/line existence, coverage lists); the E2E-in-DoD rule does not apply
  (no app surface). Write the plan anyway when the change decomposes into
  ≥3 independent tasks or the verification itself needs design — the
  user decides at Gate B.
- **Seam:** gate pushes are replaced by the PR — the spec (and plan, if
  any) commit together with the change itself. The session still never
  ends holding local commits.
- **Board:** the card never sits in `Ready to IMPL` — the auto-impl
  pipeline has nothing to claim. While the PR is open the card goes to
  `In IMPL` (the DESIGN session acts as the executor); after merge →
  `In-main`.
- **Closing:** the PR description carries `Closes #N` — the only sanctioned
  place for the closing keyword; commit messages stay keyword-free.
- **Handoff:** none — do not say «start impl» for a fast-tracked
  issue.
