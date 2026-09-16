# Panel Security Reviewer (6th Panelist) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 6th spec-review panelist `spec-panel-security` (application security perspective) to the G1b panel: create the canon body, update every roster/count carrier 5→6, drop the stale "one of 5" clauses from all 10 existing panelist bodies, and push the sweep-verified result.

**Architecture:** Text-only harness change in the superagents canon repo (issue #16). The host-port twin `.zcode/agents/spec-panel-security.md` already exists (committed in cfeae9f). The canon body transcribes the spec's Appendix A verbatim. Six carrier files get mechanical count edits. No code, no build step; verification = grep sweeps + the already-passed smoke.

**Tech Stack:** Markdown only. Live dispatch verification (already done for scenario 1) runs on the host zcode Agent tool; routing goes through the omniroute combo `panel-security` (user-side, configured and verified).

**Spec:** `docs/specs/2026-09-16-panel-security-design.md` (approved at G1b, commit cfeae9f).

---

## Behavioral Delta

How this feature behaves for the user, mapped to the spec's User Scenarios:

- **Scenario 1 (every spec run, no-attack-surface case)** → on a spec with no application attack surface, the security report is exactly `(none — no application attack surface: <one sentence>)` + `Verdict: SOUND`; the consolidated panel report carries no invented security findings. **[Validated: smoke passed 2026-09-16 against this very spec — see Verification status below.]**
- **Scenario 2 (auth-bearing spec)** → on a spec that adds roles/permissions or changes identification, the security report names concrete findings with spec section/quote references, ranked into the consolidated report like any other perspective.
- **Scenario 3 (security-model breakage)** → breakage findings (bypass, cross-role/tenant leak, trust of unvalidated input) rank BLOCKER, appear first, and are fixed before G1b.
- **Scenario 4 (panelist unavailable)** → failure follows the shared availability policy: one rerun, then the perspective is marked `skipped` in the consolidated report with the reason; a missing `panel-security` combo is named explicitly as a user-side fix.
- **Scenario 5 (weak reports)** → the user re-targets the `panel-security` combo chain in the omniroute dashboard; no repo file changes.

**Scenario → E2E anchor note (deliberate deviation):** this is a host-harness feature — there is no app E2E harness for agent dispatches. The spec's own `## Testing` section defines the acceptance mechanism: a live panel dispatch (smoke = scenario 1, already passed), field acceptance on the next auth-bearing spec (scenarios 2–3), and routing/no-regression checks below. Plan DoD anchors to those, not to app E2E tests.

---

## File Structure

| File | Action | Task |
|---|---|---|
| `.opencode/agents/spec-panel-security.md` | **create** (Appendix A verbatim) | 1 |
| `.opencode/skills/panel-spec-review/SKILL.md` | modify (roster + 2 count lines) | 2 |
| `.opencode/agents/architect.md` | modify (permission entry + dispatch line + skip rule) | 3 |
| `.zcode/skills/design-phase/SKILL.md` | modify (description + §4 counts/roster) | 4 |
| `docs/workflow/design-phase.md` | modify (3 count sites) | 5 |
| `docs/setup/new-project-setup.md` | modify (perspective count + model table row) | 5 |
| `README.md` | modify (5 count sites) | 5 |
| `.opencode/agents/spec-panel-{completeness,consistency,feasibility,simplicity,best-practices}.md` | modify (count-clause removal) | 6 |
| `.zcode/agents/spec-panel-{completeness,consistency,feasibility,simplicity,best-practices}.md` | modify (count-clause removal) | 6 |

Not touched: `.zcode/agents/spec-panel-security.md` (twin already committed, wording already count-clause-free), `.opencode/skills/panel-spec-review/` researcher wiring, G2/container workflow files (Non-Goal per spec).

---

## Task 1: Create canon body spec-panel-security
### Classification: trivial
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — **Appendix A is the authoritative file content** (transcribe verbatim, strip the outer ```` ```markdown ```` fence)
- `.opencode/agents/spec-panel-feasibility.md` — frontmatter shape reference (opencode canon shape: key set must match)

### Task Description
Create the canon agent file so the 6th panelist is dispatchable from the container.

### Files
- create: `.opencode/agents/spec-panel-security.md`

### Steps
- [ ] Write `.opencode/agents/spec-panel-security.md` with the exact content of the spec's Appendix A code block (frontmatter + body, no fence markers, no added header comment — canon bodies start with frontmatter, same as `spec-panel-feasibility.md`)
- [ ] Verify frontmatter key set matches the feasibility canon pattern: `description`, `mode: subagent`, `model: omniroute/panel-security`, `temperature: 0.1`, `permission:` (read/grep/glob allow, `edit: deny`, bash `"*": deny` with the read-only allowlist, `task: "*": deny`), and the body carries the mandatory filter section + the shared report format
- [ ] Verify no count clause in the intro: `grep -n "one of 5" .opencode/agents/spec-panel-security.md` → no output
- [ ] Commit: `git add .opencode/agents/spec-panel-security.md && git commit -m "feat(agents): spec-panel-security canon body (6th panelist, Appendix A)"`

---

## Task 2: Roster in panel-spec-review skill
### Classification: small
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — Workflow integration table row for `.opencode/skills/panel-spec-review/SKILL.md`

### Task Description
Grow the panel roster 5→6 in the container-side panel protocol skill.

### Files
- modify: `.opencode/skills/panel-spec-review/SKILL.md`

### Steps
- [ ] In the `## Panel Agent Roles` table, after the `spec-panel-best-practices` row add:
  `| `spec-panel-security` | Application security: authn, authz/roles, security-model breakage; explicit no-attack-surface verdict | read/grep/glob/git-read |`
- [ ] `All 5 are read-only leaf agents.` → `All 6 are read-only leaf agents.` (line 42)
- [ ] `After all 5 return:` → `After all 6 return:` (line 47)
- [ ] Sweep the file for stragglers: `grep -n -E "\b5\b|five" .opencode/skills/panel-spec-review/SKILL.md` — every remaining hit must be non-panel-related or fixed
- [ ] Commit: `git add .opencode/skills/panel-spec-review/SKILL.md && git commit -m "feat(workflow): panel-spec-review roster 5→6 (security row, aggregation trigger)"`

---

## Task 3: Architect dispatch list and skip rule
### Classification: small
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — Workflow integration table row for `.opencode/agents/architect.md` (notes the ALL-5→6 line is semantic, not cosmetic)

### Task Description
The container architect is the IMPL-side dispatcher of the spec panel; it must know the roster is 6.

### Files
- modify: `.opencode/agents/architect.md`

### Steps
- [ ] In the frontmatter permission block, after the line `    "spec-panel-best-practices": allow` add `    "spec-panel-security": allow` (line 31)
- [ ] Replace the dispatch line (line 276): `Dispatch all 5 panelists (...) in parallel — single message, 5 Task calls.` → `Dispatch all 6 panelists (`spec-panel-completeness`, `spec-panel-feasibility`, `spec-panel-consistency`, `spec-panel-simplicity`, `spec-panel-best-practices`, `spec-panel-security`) in parallel — single message, 6 Task calls.` (keep the trailing "Each prompt MUST contain the spec file path..." unchanged)
- [ ] Replace (line 280): `ALL 5 unavailable → skip the panel entirely` → `ALL 6 unavailable → skip the panel entirely`
- [ ] Sweep: `grep -n -E "all 5|All 5|ALL 5|\b5 panelists|five" .opencode/agents/architect.md` — every remaining hit must be non-panel-related or fixed
- [ ] Commit: `git add .opencode/agents/architect.md && git commit -m "feat(agents): architect panel dispatch 5→6 + security permission entry"`

---

## Task 4: Host design-phase skill counts
### Classification: small
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — Workflow integration table row for `.zcode/skills/design-phase/SKILL.md`

### Task Description
The host session's phase protocol is the dispatch side of the panel during DESIGN.

### Files
- modify: `.zcode/skills/design-phase/SKILL.md`

### Steps
- [ ] Frontmatter description: `spec + 5-reviewer panel G1b` → `spec + 6-reviewer panel G1b`
- [ ] §4 step 1: `Dispatch: **5 agents in parallel**, in a single Agent-tool message:` → `Dispatch: **6 agents in parallel**, in a single Agent-tool message:`
- [ ] §4 step 1 roster list: append `, `spec-panel-security`` after `spec-panel-best-practices` (keeping the trailing "(files in the repo's `.zcode/agents/`, models `omniroute/panel-*`)" unchanged)
- [ ] §4 step 3: `collect the 5 reports` → `collect the 6 reports`
- [ ] Commit: `git add .zcode/skills/design-phase/SKILL.md && git commit -m "feat(workflow): design-phase §4 panel 5→6"`

---

## Task 5: Docs and README carriers
### Classification: standard
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — Workflow integration table rows for the three docs files (with exact line numbers known at spec time)

### Task Description
The human-facing workflow/setup/README texts carry the panel count in 10 places.

### Files
- modify: `docs/workflow/design-phase.md`, `docs/setup/new-project-setup.md`, `README.md`

### Steps
- [ ] `docs/workflow/design-phase.md` line 11: `agents **`spec-panel-*`** ×5` → `×6`
- [ ] `docs/workflow/design-phase.md` line 18 (gate table): `host session + `spec-panel-*` ×5` → `×6`
- [ ] `docs/workflow/design-phase.md` line 52 (diagram): `Spec Panel Review: 5 parallel independent agents` → `Spec Panel Review: 6 parallel independent agents`
- [ ] `README.md` line 15: `spec + 5-perspective review panel` → `spec + 6-perspective review panel`
- [ ] `README.md` line 33: `5 parallel free-model perspectives` → `6 parallel free-model perspectives`
- [ ] `README.md` line 60: `host session + `spec-panel-*` ×5` → `×6`
- [ ] `README.md` line 87: `# Spec review panel (5 perspectives, G1b)` → `(6 perspectives, G1b)`
- [ ] `README.md` line 110: `spec-panel-* ×5` → `×6`
- [ ] `docs/setup/new-project-setup.md` line 64: `runs a 5-perspective **Spec Panel Review**` → `runs a 6-perspective **Spec Panel Review**`
- [ ] `docs/setup/new-project-setup.md` model table: after the `spec-panel-best-practices` row add `| spec-panel-security | `omniroute/panel-security` |`
- [ ] Commit: `git add docs/workflow/design-phase.md docs/setup/new-project-setup.md README.md && git commit -m "docs(workflow): panel count 5→6 in workflow doc, setup doc, README"`

---

## Task 6: Count-clause removal in 10 panelist bodies
### Classification: small
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — Workflow integration table last row (intro-sentence count-clause removal; perspective wording already identifies each panelist)
- `.zcode/agents/spec-panel-security.md` — the target wording reference (`You are a parallel reviewer analyzing a spec document before implementation begins.`)

### Task Description
Ten bodies still say "You are one of 5 parallel reviewers" — the count is now wrong and would churn again on the next panelist.

### Files
- modify: `.opencode/agents/spec-panel-completeness.md`, `spec-panel-consistency.md`, `spec-panel-feasibility.md`, `spec-panel-simplicity.md`, `spec-panel-best-practices.md`
- modify: `.zcode/agents/spec-panel-completeness.md`, `spec-panel-consistency.md`, `spec-panel-feasibility.md`, `spec-panel-simplicity.md`, `spec-panel-best-practices.md`

### Steps
- [ ] In each of the 10 files replace the substring `You are one of 5 parallel reviewers` → `You are a parallel reviewer` (single mechanical edit; the surrounding sentences — including best-practices' distinguishing-capability sentence — stay untouched)
- [ ] Verify all clean: `grep -rn "one of 5" .opencode/agents/ .zcode/agents/` → no output
- [ ] Commit: `git add .opencode/agents/ .zcode/agents/ && git commit -m "refactor(agents): drop intro count clause from 10 panelist bodies (perspective wording suffices)"`

---

## Task 7: Repo-wide sweep, final commit, push
### Classification: trivial
### Required Docs
- `docs/specs/2026-09-16-panel-security-design.md` — Implementation outline step 3 (the sweep is a plan DoD requirement)

### Task Description
The spec's outline mandates a mechanical sweep to catch unknown count sites before push.

### Files
- none modified directly (sweep may surface fixes that fold into a final commit)

### Steps
- [ ] Run the repo-wide sweep: `grep -rn -E "5 panelists|5 parallel|×5|5-reviewer|one of 5|[Aa]ll 5|ALL 5" --include="*.md" .`
  (pattern extended beyond the spec's list with the `all 5` variants — those are exactly the aggregation-trigger sites this plan edits; document the extension in the task report)
- [ ] Every hit must be either already fixed by Tasks 1–6, or non-panel-related with a one-line justification in the task report (e.g. changelog history lines, unrelated `×5` counts). Panel-related hits = fix and re-sweep until clean
- [ ] Confirm the full stack is present: `ls .opencode/agents/spec-panel-security.md .zcode/agents/spec-panel-security.md` (both exist); `grep -c "spec-panel-security" .opencode/skills/panel-spec-review/SKILL.md .opencode/agents/architect.md .zcode/skills/design-phase/SKILL.md docs/setup/new-project-setup.md` (≥1 each)
- [ ] Update the spec's Status line: `Draft — G1a approved, panel fixes applied, consistency re-run pending` → `Spec OK (G1b), plan G2, IMPL pending` (justification, from plan review: the DESIGN DoD folds gate state into the artifact text, and the line was stale — it still said "Draft" after G1b shipped; also fix the same spec's "twin exists already on disk, uncommitted" → "already committed (cfeae9f)")
- [ ] Commit and push everything: `git add -A && git commit -m "feat(workflow): spec panel 5→6 — spec-panel-security (issue #16)" && git push origin main`

---

## DoD (Definition of Done)

1. `.opencode/agents/spec-panel-security.md` exists, content == Appendix A, frontmatter key set matches the feasibility canon pattern.
2. All six carrier files carry 6-count roster/numbers (`panel-spec-review` SKILL, `architect.md`, host `design-phase` SKILL, workflow doc, setup doc, README).
3. `grep -rn "one of 5" .opencode/agents/ .zcode/agents/` → clean.
4. Repo-wide sweep (Task 7 pattern) → zero panel-related hits; remaining hits carry justifications.
5. Working tree clean after push; `git log` shows the task commits.

## Verification status at plan time (evidence, not tasks)

- **Smoke of the filter (spec Testing item 1) — PASSED 2026-09-16, this session:** host dispatch of `spec-panel-security` against this very spec returned the exact no-attack-surface form (`## Findings (none — no application attack surface: ...)`, `## Verdict SOUND`). 16k tokens, 1 tool call, ~20 s.
- **Routing check (spec Testing item 3) — PASSED 2026-09-16:** direct test-call to `omniroute/panel-security` → HTTP 200, upstream `kimi-k2.7-code`; zcode catalog entry `panel-security` present in `~/.zcode/v2/config.json` (line 797). The omniroute dashboard combo (spec outline step 4, user-side) is therefore done.
- **No-regression (spec Testing item 4):** aggregation behavior for 6 reports is verified by the next consolidated report (field, not IMPL DoD).
- **Scenarios 2–3 (spec Testing item 2):** field acceptance on the next auth-bearing spec; weak findings → scenario 5 (combo re-target), no spec change.
