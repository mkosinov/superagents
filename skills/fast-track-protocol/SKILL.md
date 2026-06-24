---
name: fast-track-protocol
description: Use when handling small post-implementation fixes, polish, wiring, or refactors that don't justify the full brainstorming/planning/review pipeline — a lightweight code-only protocol with a separate Phase 2 handoff for procedural wrap-up (tests, docs, reviews, push)
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, skip this skill. FasTP is orchestrator logic — coder subagents receive their constraints via the dispatch prompt, they do not load this skill.
</SUBAGENT-STOP>

# Fast Track Protocol (FasTP)

## Overview

A lightweight protocol for making small code edits **without** the full SuperAgents procedural overhead (no full spec, no brainstorming, no plan doc). The architect (@architect) remains the orchestrator and dispatches coder subagents exactly as in the standard workflow, but the per-fix loop is trimmed to "code → visual check → repeat", and the full procedural package (tests, docs, reviews, push) is deferred to an explicit **Phase 2** triggered at the end of the editing session.

**Core principle:** Keep the architect-as-orchestrator discipline. Skip the procedural scaffolding, never skip the dispatching discipline. The architect dispatches; coders implement; the architect verifies and owns WIP commits.

**Announce at start:** "I'm using the fast-track-protocol skill for this editing session."

## When to use this skill

**Use for:**
- Small/medium UI tweaks, polish, copy changes
- Simple wiring of existing components
- Refactors of small/medium scope
- Single-file fixes (style, layout, type)
- Visual regression fixes (after identify + plan)

**Don't use for:**
- New features requiring user research
- Breaking API changes
- Anything needing real-time product decisions
- Backend schema or migration changes (use full protocol)

If a request starts as a FasTP fix and grows into a feature, **escalate out of FasTP** — return to the standard workflow (brainstorming → plan → worktree → subagent loop).

## How to invoke

The protocol uses three slash commands. They are **explicit, not legacy**:

| Command | Effect |
|---------|--------|
| `/fastp_start <description>` | Begin a FasTP session with explicit description. Equivalent to a chat fix request. |
| `/fastp_end` | End Phase 1, transition to Phase 2 (full procedural package). Equivalent to "коммитим" / "let's ship". |
| `/fastp_save` | Persist current todowwrite to scratchpad or GH issues (see "State Persistence" below). Triggered manually before session end or when user wants a checkpoint. |

**Without slash commands**, the user submits fix requests **directly in chat**. Each request is a single FasTP fix.

```
User: "Add a 'Notes' field to the modal"
User: "Fix the label alignment in the client header (mb-2 → mb-1)"
User: [screenshot] "the date picker overlaps the calendar icon on mobile"
```

**End of Phase 1:** when the user signals wrap-up ("коммитим", "let's commit", "Phase 2", "let's ship", or `/fastp_end`), the architect transitions to Phase 2 (the full procedural package).

---

## Session Workflow

The Architect (`@architect`) is the **orchestrator**. The user is in the loop for visual verification (default, MITL mode) or out of the loop (autonomous mode — see below).

```
1. User writes fix request in chat (or via /fastp_start)
        ↓
2. Architect runs Task Lifecycle (see below):
   - NEW task → dedup against todowwrite → add to todowwrite (status: pending)
   - DUPLICATE → notify user, resume existing entry
        ↓
3. Architect dispatches `frontend-coder` or `backend-coder`
   (RESUME if context is fresh and relevant, COLD START otherwise — see "Subagent Session Reuse")
        ↓
4. Coder reports back: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
        ↓
5. Architect writes BRIEF REPORT to user
        ↓
6. User verifies (MITL) or verifier subagent reports (autonomous)
        ↓
7. **On user OK ("ok", "✓", "yes mark done")**:
   - Architect marks todowwrite `completed`
   - **WIP commit** for this single task (see "WIP Commit Policy")
   - NEVER auto-mark or auto-commit without user OK
   - If user says "needs changes" → re-dispatch with clarifications
        ↓
8. If issues found → re-dispatch coder → loop (max 3 fix iterations)
        ↓
9. At `/fastp_end` or user signal: Phase 2 (full procedural package)
```

### Why TodoWrite?

User wants to see at a glance:
- What's been requested but not started (`pending`)
- What's currently being worked on (`in_progress`)
- What was completed and awaits user verification (`completed` — flagged in chat)
- What's blocked or needs decision (`pending` with comment)

**todowwrite is the only in-session task tracker** in FasTP. It must be updated after every step — user is always watching todowwrite in the opencode UI. For **cross-session persistence**, use `/fastp_save` (see "State Persistence" below).

### Task Lifecycle

For **every** user message, apply this algorithm before responding substantively:

```
1. Is this a NEW task?
   ├─ NO (smalltalk, question about state, meta-discussion) → respond normally, skip
   └─ YES → continue

2. DEDUP check:
   - Search todowwrite (current TodoWrite) only
   - Match by: action type, file/area, issue number, or subject

3. DUPLICATE found?
   ├─ YES → notify user ("Task X is already tracked in todowwrite"),
            resume the existing entry, do NOT create a new one
   └─ NO → continue

4. NEW task — add to:
   - todowrite (status: `pending`)

4a. **Construct dispatch prompt — verbatim from user description.**
   Copy the user's words into the dispatch prompt. Do NOT paraphrase,
   summarize, or add architect's hypothesis. The coder is implementing
   what the user asked, not what the architect thinks they asked.

   - User described symptom X → dispatch says symptom X
   - User described cause Y → dispatch says cause Y
   - If architect has a separate hypothesis, dispatch an **investigation
     pass first** ("find root cause for symptom X, report file:line,
     do NOT fix"), then implementation pass after user OK
   - Never substitute architect's understanding for user's words

5. After dispatch + report:
   - Receive coder status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
   - Write BRIEF REPORT to user
   - WAIT for explicit user OK before marking `completed`
   - On OK → mark `completed` + WIP commit (see "WIP Commit Policy")

6. If user adds NEW info mid-task (e.g. "wait, also fix X"):
   - Run dedup check again
   - Add to existing task's scope OR create new entry — decide and tell user
```

**Note:** FasTP uses todowwrite as the SOLE in-session task tracker. There is no scratchpad mirror, no GH-issues search, no META-INSTRUCTION classification. For cross-session persistence, use `/fastp_save` (see "State Persistence" below).

### Brief Report Format

After every dispatch completion, before asking for OK:

```markdown
## Brief Report — [task name]

**Status:** DONE | DONE_WITH_CONCERNS | BLOCKED
**Files changed:** [list]
**Evidence:** [screenshot path, file diff stat, console output]
**Open questions:** [if any]

---

OK пометить выполненной?
```

**Phase 1 caveat:** tests are forbidden in Phase 1 (see "Never in Phase 1"). Evidence comes from screenshots, diff stats, and console output — never from new test runs.

User responds with one of:
- "ok" / "✓" / "да" → mark `completed` + WIP commit
- "needs changes" → re-dispatch with clarifications
- "more info" → provide additional context, then re-ask

### State Persistence (cross-session)

`/fastp_save` checkpoints the current todowwrite so work can resume in a future session. The architect MUST ask the user where to save before writing:

```
Architect: "Where to save current todowwrite?
  1. scratchpad — local, in this repo's .opencode/scratchpad.md
  2. GitHub issues — one issue per task, labeled 'fasTP-saved'
  3. Both"

User: [choice]
```

**Format saved per task** (regardless of destination):

```markdown
- [status] [task title]
  - Agent: [current subagent type, e.g. frontend-coder]
  - Context: [brief description of the fix / what was happening]
  - Files: [list of files touched so far]
  - Resume instructions: [what to do in next session to pick this up]
```

**Why:** todowrite is per-session (UI element). Scratchpad and GH issues are durable. The save command bridges ephemeral and persistent state.

**When to trigger:**
- Before `/fastp_end` (Phase 1 wrap-up)
- Manually when user wants a checkpoint mid-session
- When user types `/fastp_save`, "сохрани статус", "save session", "save fasTP"

---

## Operation Modes

The Architect operates in one of two modes per session. The mode determines **who does visual verification** (everything else is identical).

| Mode | Who is in the loop | Who verifies UI | How detected |
|---|---|---|---|
| **Autonomous** (man out of the loop) | Architect alone | Architect dispatches `general` subagent with browserMCP (or Playwright fallback — see "Visual Verification") | User explicitly said "ухожу / автономно / I'm leaving" |
| **Man in the loop (MITL)** | User + Architect | **User themselves** — takes screenshots and writes report in chat | Default (user is responding) |

**Mode declaration:** in scratchpad as a single line: `Mode: autonomous | mitl`. This is the single source of truth. **Mode changes ONLY when the user explicitly switches** ("ухожу" / "вернулся"). Architectural silence or reading time is NOT a mode change trigger.

**Key principle:** in both modes, the **Architect remains orchestrator** — dispatches coder, marks TodoWrite, makes WIP commits. The only difference is **who provides visual feedback** (subagent vs user).

---

## Phase 1: Fast Track (Code Only)

The Architect launches `frontend-coder` or `backend-coder` with these constraints:

- **ONLY update the code according to the description.**
- No other actions are permitted.
- Edit only the specified code.
- DO NOT update tests.
- DO NOT update documentation (except the protocol doc itself, with user approval).
- DO NOT run linters / formatters / pre-commit hooks.
- DO NOT perform code-quality review or spec review.

### Coder report format (required)

Coder MUST report back with one of:
- **DONE** — implemented as requested, no concerns
- **DONE_WITH_CONCERNS** — implemented, but has observations (e.g. file getting large, design issue noticed)
- **BLOCKED** — cannot proceed (missing info, technical blocker)
- **NEEDS_CONTEXT** — needs clarification before proceeding

Plus: list of files changed, what implemented, self-review findings, open questions.

### Visual verification is MANDATORY in Phase 1

After **every** coder dispatch that touches UI (`.tsx`, `.css`, Tailwind config, etc.):
- Architect triggers visual verification (see "Visual Verification")
- Skip only for: type-only changes, doc-only changes, backend-only changes, trivial single-line style fixes (e.g. hex color swap)

**Why mandatory:** catching visual issues early is cheaper than fixing accumulated regressions at end of session.

Multiple fixes can be issued sequentially or in parallel if edits are independent.

---

## Phase 2: Procedural

Phase 2 is triggered when the user signals wrap-up ("коммитим", "Phase 2", "let's ship", `/fastp_end`). The architect runs the complete procedural package:

1. **Visual verification final pass** (whole branch, all changes since last Phase 2)
2. `code-quality-reviewer` — review the final code
3. `spec-reviewer` — verify compliance with **the original task description** (not a written spec — FasTP doesn't create one). Each commit's WIP message should match the task title.
4. **Tests** — run project's test suite, fix breakages
5. `docser` — update CHANGELOG, project docs, status
6. Commit (final, not WIP) / open or update PR

---

## Visual Verification

**Mandatory after every UI code change in Phase 1.** Max 3 fix iterations per visual issue, then escalate to scratchpad and move on.

### The `general` subagent (for autonomous verification)

In autonomous mode, the architect dispatches a `general` subagent to do visual verification. `general` is **opencode's built-in lightweight agent** (no project-specific knowledge, no skill tables, ~1-2 KB system prompt). It's the right choice because:
- Verification is mechanical (navigate, snapshot, click, screenshot)
- No domain knowledge of the codebase is needed
- Smaller system prompt = faster dispatch + cheaper tokens
- Project-specific agents like `frontend-coder` should NOT be used for verification (they'd burn their context on browser work, not the code)

### Tool preference (highest to lowest)

1. **browserMCP** — PRIMARY. Tools: `browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_click`, `browser_close`, etc.
2. **Playwright via Node script** — FALLBACK only when browserMCP unavailable.

### Algorithm for verifier subagent

```
Step 1: Try a browserMCP tool (e.g. browser_navigate)
  ├─ Works → continue with browserMCP
  └─ Tool not exposed / MCP not connected / timeout → Step 2

Step 2: Fallback to Playwright
  - Use `npx playwright test` (or `which playwright` to find path)
  - In report, MUST explicitly state:
    * "Playwright fallback used"
    * Reason (e.g. "browserMCP tools not loaded in subagent session")
```

### Verifier report — mandatory fields (autonomous mode)

```markdown
## Visual Verification Report

### Mode
- autonomous | mitl

### Tool used
- **Primary:** browserMCP
- **Fallback:** Playwright via Node script (if used)
  - Path: `npx playwright test` (or `which playwright` to find)
  - Reason: <why fallback was needed>

### Setup
- Dev server health: <OK/error>
- Activity/page opened: <yes/no>
- Console errors: <list or "none">

### Screenshots
- /tmp/opencode/<feature>/<name>.png

### Checklist
- [PASS/FAIL/WARN] <item> — <short description>

### Issues found
1. <HIGH/MED/LOW>: description + screenshot path

### Recommendation
- "all good, proceed" | "fixes needed: ..."
```

In **MITL** mode, the user fills in the equivalent report themselves — see "User Verification Report (MITL mode)" above for the template.

---

## WIP Commit Policy

WIP commits are **local-only checkpoints** during Phase 1. They are NOT pushed to remote and do not trigger tests/linters.

### When to commit

**One WIP commit per fix, when the user OKs the task and it is crossed off todowwrite.**

This is granular, clear, and unambiguous: each completed task in todowwrite has exactly one corresponding WIP commit. The commit is the durable artifact of "this task is done" — `todowrite` and `git log` stay in lockstep.

### Commit message format

```
<type>(<scope>): <summary>

<body — list of fix IDs and what each changed>

WIP — awaiting Phase 2.
```

- Types: `wip` (generic batch), `fix` (specific bug/issue), `feat` (new behavior), `docs` (doc only), `chore` (refactor/maintenance)
- Scope: usually the area touched (e.g. `admin` for frontend, `api` for backend)
- Body: enumerate changes — "Why" not "What" (the diff shows "What")
- Each per-task WIP commit is a single fix, so the body can be brief or omitted

### Exclusions from WIP commit

- E2E visual-regression snapshots (auto-generated, refresh in Phase 2)
- Any other auto-generated artifacts (build output, coverage reports)
- Secrets, `.env` files

---

## Subagent Session Reuse

The goal is **efficient use of tokens and time** — not "always reuse" or "always cold start". The right choice depends on context.

### Decision rule

| Context window used | Context relevant to new task? | Action |
|---------------------|-------------------------------|--------|
| **< 15%** | — | **RESUME** (almost always) |
| **15% – 50%** | Yes | **RESUME** |
| **15% – 50%** | No | **COLD START** (better than polluting reused context) |
| **> 50%** | — | **COLD START** (reused session is too full) |

**"Relevant"** = the new task operates on the same files, modules, or domain as the previous one in that session. A backend-coder session that fixed a payment API is NOT relevant for a frontend modal CSS fix.

### Parallel fixes with different coder types

A single `frontend-coder` session cannot do two fixes truly in parallel (one model instance, one context). However, you CAN run **a `frontend-coder` and a `backend-coder` in parallel** — they are independent sessions and can dispatch simultaneously.

Example: user asks "fix modal layout AND fix the payment endpoint it calls":
- Dispatch `frontend-coder` (resume or cold) for modal layout
- Dispatch `backend-coder` (resume or cold) for payment endpoint
- Wait for both to report
- Brief report covers both
- WIP commits per fix (per "WIP Commit Policy")

### How to track sessions

- Track open sessions in **scratchpad** (`.opencode/scratchpad.md`) under section "Open Subagent Sessions"
- Include: session ID, subagent type, last task, intended reuse area
- Pass `task_id` to the `task` tool to resume

### Scratchpad entry format

```markdown
## Open Subagent Sessions
| Session ID | Type | Last used for | Reuse for |
| `ses_xxx...` | frontend-coder | Task #N (description) | Same-area UI fixes |
| `ses_yyy...` | general | Task #N (description) | Visual verify tasks |
```

**Important:** Concrete session IDs live in **scratchpad** (state). This protocol describes the **approach**. The two should not be mixed.

---

## User Verification Report (MITL mode)

In MITL mode, the user does visual verification themselves. To capture evidence that the architect can use (e.g. for Phase 2's "final visual pass"), the user writes a short report after each fix:

```markdown
## User Verification — [task name]

**Tested on:** [browser / device / viewport]
**Result:** works | works with caveat | broken
**Screenshot:** [/tmp/opencode/<feature>/<name>.png or "inline"]
**Issues found:** [list, or "none"]
**Caveats:** [e.g. "looks fine on desktop, didn't test mobile"]
```

The architect records this in chat and uses it as the basis for the next dispatch or the OK gate. Without this report, MITL mode has no audit trail for Phase 2.

---

## Example Session (MITL mode)

```
# User: "Add a 'Notes' field to the modal"
# Architect:
  1. Task Lifecycle: NEW task → add to todowwrite (status: pending)
  2. Dispatch frontend-coder (cold start or resume per "Subagent Session Reuse")
  3. Coder reports DONE
  4. Brief report to user (what was done, files changed, evidence)
  5. User takes screenshot, writes User Verification Report in chat
  6. Report says: "field shows, but label misaligned" (issue found)
  7. Re-dispatch coder with "fix label alignment, mb-2 → mb-1"
  8. Coder reports DONE
  9. Brief report + User Verification Report → user says "ok"
 10. On user OK → mark todowrite completed + WIP commit
 11. Wait for next fix OR /fastp_end (Phase 2)
```

## Example Session (Autonomous mode)

Same as above, but step 5-9 are replaced with verifier subagent:

```
  5. Dispatch general verifier (resume ses_yyy... — see scratchpad "Open Subagent Sessions")
     with browserMCP: navigate to page, snapshot, screenshot, click around
  6. Verifier reports: "field shows, label misaligned (LOW). Screenshot: /tmp/...png"
  7. Re-dispatch coder with fix
  8. Re-dispatch verifier (resume SAME ses_yyy... session) — browserMCP context preserved
  9. Verifier reports: all good
 10. Brief report to user
 11. On user OK → mark todowwrite completed + WIP commit
```
 11. Brief report to user
 12. On user OK → mark todowrite completed + WIP commit
```

---

## Phase 1 Discipline

A single source of truth for what is and isn't allowed in Phase 1.

### Never

- **Edit code yourself** — the architect never edits code, even in FasTP. Always re-dispatch the coder, even for "trivial" fixes.
- **Run tests** in Phase 1 (can OOM, slow — covered in Phase 2)
- **Run linters / formatters / pre-commit hooks** (can OOM)
- **Bypass pre-commit hooks with --no-verify** (Phase 1 doesn't push anyway)
- **Push to remote** (wait for Phase 2)
- **Merge to main / update PR** (Phase 2)
- **Run `code-quality-reviewer`, `spec-reviewer`, or `docser`** in Phase 1
- **Modify tests** in Phase 1 (test changes go in Phase 2)
- **Update README / API docs / CHANGELOG** in Phase 1 (Phase 2 / docser)
- **Cold-start a subagent session** when reuse is appropriate (see "Subagent Session Reuse")
- **Cold-start browserMCP** when a verifier session already has the browser context
- **Auto-mark todowrite completed** without user OK
- **Edit this protocol doc** without first showing the plan and getting user approval — meta-documents need approval before changes

### Always

- **Dispatch coders** for every code change, even "trivial" ones
- **Verify UI visually** after every Phase 1 UI change (except trivial single-line style fixes)
- **Update todowwrite** after every dispatch and report
- **Mark `Mode: autonomous | mitl`** in scratchpad at session start
- **Track open subagent sessions** in scratchpad for reuse
- **Wait for user OK** before marking `completed` or making WIP commits
- **Use `/fastp_save`** to checkpoint state when user wants a snapshot
- **Transition to Phase 2** when the user signals wrap-up (`/fastp_end` or chat equivalent)

---

## Related skills

- **brainstorming** — FasTP explicitly skips this. If a "fix" grows into a feature, escalate out of FasTP and into brainstorming.
- **using-git-worktrees** — FasTP assumes work happens in an existing isolated worktree; create it before starting a FasTP session if you aren't already in one.
- **subagent-driven-development** — The full subagent loop with two-stage review; FasTP is a trimmed version of this for code-only edits. Phase 2 partially restores the full review pipeline.
- **finishing-a-development-branch** — Phase 2 of FasTP ends with the same merge/PR/keep/discard options as the standard workflow.
- **test-driven-development** — Skipped in Phase 1 by design; applied in Phase 2.
- **systematic-debugging** — When a FasTP fix becomes a "real" bug (e.g. architectural issue, repeated regression), switch to systematic debugging before continuing.
