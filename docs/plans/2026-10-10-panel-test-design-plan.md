# Panel Test-Design Reviewer (7th Panelist) + Simplicity Mandate Surgery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 7th spec-review panelist `spec-panel-test-design` (test-design perspective) and redraw the simplicity panelist's mandate — per spec `docs/specs/2026-10-08-panel-test-design-design.md` (v3, approved at gate B 2026-10-10): create both agent twins, add the exclusion block to both simplicity twins, grow every roster/count carrier 6→7, and bump the reflect over-orchestration default so a 7-panelist dispatch is the designed norm.

**Architecture:** Text-only harness change in the superagents repo (issue #15). Both agent bodies transcribe the spec's Appendices A/B verbatim. The carrier edits are mechanical count/roster changes quote-anchored in the spec's Workflow integration table. One code-adjacent edit: the reflect default `max_subagents` 6→8 (config default + in-check fallback + test fixture). No build step; verification = grep sweeps + the next session's panel run (smoke) + the first DESIGN cycle (pilot).

**Tech Stack:** Markdown (agents, skills, docs) + two Python lines in reflect (`config.py`, `workflow_checks.py`) and its test.

**Spec:** `docs/specs/2026-10-08-panel-test-design-design.md` (v3, commit 49d1fb4).

---

## File Structure

| File | Action | Task |
|---|---|---|
| `.opencode/agents/spec-panel-simplicity.md` | modify (exclusion block) | 1 |
| `.zcode/agents/spec-panel-simplicity.md` | modify (same block, host twin) | 1 |
| `.opencode/agents/spec-panel-test-design.md` | **create** (spec Appendix A verbatim) | 2 |
| `.zcode/agents/spec-panel-test-design.md` | **create** (spec Appendix B verbatim) | 2 |
| `.opencode/skills/panel-spec-review/SKILL.md` | modify (roster row, 2 count lines, gradient note) | 3 |
| `.opencode/agents/architect.md` | modify (allowlist + dispatch line + skip rule) | 4 |
| `.zcode/skills/design-phase/SKILL.md` | modify (description + §4 counts/roster) | 5 |
| `.zcode/skills/auto-design/SKILL.md` | modify (runner arg list + fallback count) | 5 |
| `.opencode/agents/spec-panel-best-practices.md` | modify (2 prose counts) | 6 |
| `.zcode/agents/spec-panel-best-practices.md` | modify (2 prose counts) | 6 |
| `.opencode/skills/reflect/scripts/lib/config.py` | modify (`max_subagents` 6→8) | 7 |
| `.opencode/skills/reflect/scripts/lib/workflow_checks.py` | modify (fallback default 6→8) | 7 |
| `.opencode/skills/reflect/tests/test_workflow_checks.py` | modify (fixture 7→9 children) | 7 |
| `docs/workflow/design-phase.md` | modify (count sites, quote-anchored) | 8 |
| `docs/setup/new-project-setup.md` | modify (count + stale attribution fix) | 8 |
| `README.md` | modify (count sites, sweep-caught) | 8 |

Not touched: `panel_review.sh` (agents come from argv — no baked roster), the panel-spec-review researcher wiring, gate C / plan-reviewer / IMPL files (spec Non-Goals), the other four panelists' bodies.

---

## Task 1: Simplicity mandate surgery (both twins)
### Classification: trivial
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — §Architecture, "Simplicity mandate surgery" block (the exact text to insert)

### Task Description
The simplicity panelist keeps proposing economies but loses the verification-changing ones; the block cites the four dismissed precedents.

### Files
- modify: `.opencode/agents/spec-panel-simplicity.md`, `.zcode/agents/spec-panel-simplicity.md`

### Steps
- [ ] In BOTH files insert the spec's exclusion block (verbatim from §Architecture, "Simplicity mandate surgery", as a PLAIN paragraph — strip the blockquote `>` marker; form follows the security panelist's scope note) between the last "What you look for" bullet (`- A new component, form, or API invented by the spec…`) and `## Report Format (MANDATORY)`
- [ ] Nothing else changes in either body (intro, checklist, report format, one-sentence-direction rule stay)
- [ ] Verify: `grep -c "economies that change what a test verifies" .opencode/agents/spec-panel-simplicity.md .zcode/agents/spec-panel-simplicity.md` → 1 in each
- [ ] Commit: `git add .opencode/agents/spec-panel-simplicity.md .zcode/agents/spec-panel-simplicity.md && git commit -m "feat(agents): simplicity mandate surgery — test-economy out of scope BY DESIGN (issue #15)"`

---

## Task 2: Create test-design twins
### Classification: trivial
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — **Appendix A (canon) and Appendix B (host twin) are the authoritative file contents** (transcribe verbatim, strip the outer 4-backtick fence)
- `.opencode/agents/spec-panel-simplicity.md` — canon frontmatter shape reference
- `.zcode/agents/spec-panel-simplicity.md` — host frontmatter shape reference (incl. `thoughtLevel: max`)

### Task Description
Make the 7th panelist dispatchable in the container (canon) and on the host (twin).

### Files
- create: `.opencode/agents/spec-panel-test-design.md`, `.zcode/agents/spec-panel-test-design.md`

### Steps
- [ ] Write `.opencode/agents/spec-panel-test-design.md` = spec Appendix A content (frontmatter `description`, `mode: subagent`, `model: opencode/nemotron-3-ultra-free`, `temperature: 0.1`, the read-only `permission:` allowlist; body with the gradient block incl. the best-practices boundary sentence, the checklist, the executable-test-surface filter, the fenced Report Format)
- [ ] Write `.zcode/agents/spec-panel-test-design.md` = spec Appendix B content (frontmatter `name`, `description`, `tools: [Read, Bash]`, `model: "account:zai-individual-coding-plan/GLM-5.3-Flash"`, `thoughtLevel: max`; port-header comment with the 2026-10-10 date; read-only constraints prose; same body)
- [ ] Verify: `grep -c "no executable test surface\|no tests or e2e scenarios with data and assertions" .opencode/agents/spec-panel-test-design.md .zcode/agents/spec-panel-test-design.md` → ≥1 in each; `grep -c "thoughtLevel: max" .zcode/agents/spec-panel-test-design.md` → 1
- [ ] Commit: `git add .opencode/agents/spec-panel-test-design.md .zcode/agents/spec-panel-test-design.md && git commit -m "feat(agents): spec-panel-test-design canon body + host twin (7th panelist, Appendices A/B)"`

---

## Task 3: Roster in panel-spec-review skill (container)
### Classification: small
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — §Architecture, Workflow integration row for `.opencode/skills/panel-spec-review/SKILL.md` + the gradient-note wording

### Task Description
Grow the roster 6→7 in the container-side panel protocol skill.

### Files
- modify: `.opencode/skills/panel-spec-review/SKILL.md`

### Steps
- [ ] In the `## Panel Agent Roles` table, after the `spec-panel-security` row add the test-design row with the spec's perspective wording (verification quality: exercise completeness, non-duplication, localizability, AC testability) and `read/grep/glob/git-read` access
- [ ] `All 6 are read-only leaf agents.` → `All 7 are read-only leaf agents.`
- [ ] `After all 6 return:` → `After all 7 return:`
- [ ] Add the gradient note under the roster (spec wording): completeness = coverage of scenarios (missing tests), test-design = verification quality of defined tests (under-exercised, duplicated, unlocalizable) — opposite gradients, separate panelists
- [ ] Commit: `git add .opencode/skills/panel-spec-review/SKILL.md && git commit -m "feat(workflow): panel-spec-review roster 6→7 (test-design row, gradient note)"`

---

## Task 4: Architect dispatch list and skip rule
### Classification: small
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — Workflow integration row for `.opencode/agents/architect.md`

### Task Description
The container architect dispatches the panel on the legacy path; it must know the roster is 7.

### Files
- modify: `.opencode/agents/architect.md`

### Steps
- [ ] In the frontmatter permission block, after `    "spec-panel-security": allow` add `    "spec-panel-test-design": allow`
- [ ] Dispatch line: `Dispatch all 6 panelists (`…`) in parallel — single message, 6 Task calls.` → `Dispatch all 7 panelists (`…`, `spec-panel-test-design`) in parallel — single message, 7 Task calls.` (keep the trailing "Each prompt MUST contain…" unchanged)
- [ ] `ALL 6 unavailable → skip the panel entirely` → `ALL 7 unavailable → skip the panel entirely`
- [ ] Sweep: `grep -nE "all 6|All 6|ALL 6|6 panelists|6 Task" .opencode/agents/architect.md` → every hit fixed or non-panel-related
- [ ] Commit: `git add .opencode/agents/architect.md && git commit -m "feat(agents): architect panel dispatch 6→7 + test-design permission entry"`

---

## Task 5: Host skills — design-phase and auto-design
### Classification: small
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — Workflow integration rows for both skills (auto-design row names the TWO Step 5 sites: the runner argument list — primary — and the fallback clause)

### Task Description
The host session's phase protocols dispatch the panel (primary: container runner; fallback: host agents).

### Files
- modify: `.zcode/skills/design-phase/SKILL.md`, `.zcode/skills/auto-design/SKILL.md`

### Steps
- [ ] `design-phase` frontmatter description: `spec + 6-reviewer panel` → `spec + 7-reviewer panel`
- [ ] `design-phase` §4 dispatch line: `6 agents in parallel` → `7 agents in parallel`; append `spec-panel-test-design` to the roster list in the same line
- [ ] `auto-design` Step 5, primary path: append `spec-panel-test-design` to the `panel_review.sh` command's agent argument list (after `spec-panel-security`)
- [ ] `auto-design` Step 5, fallback clause: `the 6 host agents` → `the 7 host agents`
- [ ] Verify: `grep -c "spec-panel-test-design" .zcode/skills/design-phase/SKILL.md .zcode/skills/auto-design/SKILL.md` → ≥1 each; `grep -c "7 host agents" .zcode/skills/auto-design/SKILL.md` → 1
- [ ] Commit: `git add .zcode/skills/design-phase/SKILL.md .zcode/skills/auto-design/SKILL.md && git commit -m "feat(workflow): design-phase + auto-design panel 6→7 (runner args, host fallback)"`

---

## Task 6: Best-practices twins prose counts
### Classification: trivial
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — Workflow integration row for the best-practices twins (quote-anchored)

### Task Description
Both best-practices bodies hard-code panel counts in prose; both numbers go stale after the bump.

### Files
- modify: `.opencode/agents/spec-panel-best-practices.md`, `.zcode/agents/spec-panel-best-practices.md`

### Steps
- [ ] In BOTH files: `the other 5 panelists` → `the other 6 panelists`; `aggregates all 6 reports` → `aggregates all 7 reports` (same sentence, one edit each)
- [ ] Verify: `grep -n "other 5\|all 6" .opencode/agents/spec-panel-best-practices.md .zcode/agents/spec-panel-best-practices.md` → no output
- [ ] Commit: `git add .opencode/agents/spec-panel-best-practices.md .zcode/agents/spec-panel-best-practices.md && git commit -m "fix(agents): best-practices panel counts 5/6 → 6/7 (issue #15)"`

---

## Task 7: Reflect over-orchestration default
### Classification: small
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — Workflow integration row for reflect (rationale: a 7-panelist host dispatch becomes the designed norm, not a violation)

### Task Description
The over-orchestration check flags >6 subagents per parent; the panel now dispatches 7.

### Files
- modify: `.opencode/skills/reflect/scripts/lib/config.py`, `.opencode/skills/reflect/scripts/lib/workflow_checks.py`, `.opencode/skills/reflect/tests/test_workflow_checks.py`, `.opencode/skills/reflect/config/reflect.config.example.json`

### Steps
- [ ] `config.py` line 23: `{"max_subagents": 6}` → `{"max_subagents": 8}`
- [ ] `workflow_checks.py` in-check fallback: `cfg.options.get("max_subagents", 6)` → `cfg.options.get("max_subagents", 8)`
- [ ] `config/reflect.config.example.json` line 15: `"max_subagents": 6` → `"max_subagents": 8` (the shipped example re-arms the old ceiling for every project seeded from it)
- [ ] Test `test_over_orchestration_detects`: 7 children → 9 children; comment `# 7 subagents > default max of 6` → `# 9 subagents > default max of 8`; assertion `subagent_count == 9`
- [ ] Run the test: `python3 -m pytest .opencode/skills/reflect/tests/test_workflow_checks.py -k over_orchestration` → 2 passed
- [ ] Commit: `git add .opencode/skills/reflect/ && git commit -m "feat(reflect): over-orchestration max_subagents 6→8 (default, fallback, example config) — 7-panelist dispatch is the designed norm (issue #15)"`

---

## Task 8: Docs carriers, spec status, sweep, push
### Classification: standard
### Required Docs
- `docs/specs/2026-10-08-panel-test-design-design.md` — Workflow integration rows for the three docs files + the Grep sweep line (scoped, case-insensitive, exclusions)

### Task Description
Human-facing texts carry the count (and one stale attribution); the sweep is the DoD backstop; then push.

### Files
- modify: `docs/workflow/design-phase.md`, `docs/setup/new-project-setup.md`, `README.md`

### Steps
- [ ] `docs/workflow/design-phase.md`: table row `Spec panel ×6` → `×7`; diagram `6 parallel independent agents` → `7 parallel independent agents`; if the spelled-out roster sentence is present (`Six independent parallel perspectives…`) → `Seven …` + `spec-panel-test-design` appended
- [ ] `docs/setup/new-project-setup.md`: `6-perspective` → `7-perspective` AND fix the same sentence's stale attribution — the panel is dispatched by the DESIGN-phase skills (design-phase/auto-design), not by the brainstorming skill
- [ ] `README.md`: sweep-caught count sites (e.g. mermaid edge `panel report ×6` → `×7`) — fix every panel-related hit
- [ ] Update the spec Status line: `In design — Gate B pending…` → `Spec OK (gate B 2026-10-10), plan approved (gate C 2026-10-10) — in IMPL`
- [ ] Run the scoped sweep (spec's Grep sweep line, case-insensitive): `grep -rniE "all 6|the 6|6 host|6 panel|6 parallel|6-reviewer|6-perspective|6 reviewers|6 perspectives|6 panelists|panel of 6|6 Task|6 agents|6 reports|other 5|× ?6|[Ss]ix (independent|parallel|perspectiv)" README.md docs/ .zcode/ .opencode/agents/ .opencode/skills/ --exclude-dir=node_modules | grep -v "docs/specs/\|docs/plans/\|token-analytics/"` → zero panel-related hits; every remaining hit carries a one-line justification in the task report
- [ ] Confirm the full stack: both test-design twins exist; `grep -c "spec-panel-test-design" .opencode/skills/panel-spec-review/SKILL.md .opencode/agents/architect.md .zcode/skills/design-phase/SKILL.md .zcode/skills/auto-design/SKILL.md` → ≥1 each
- [ ] Commit and push everything: `git add -A && git commit -m "docs(workflow): panel count 6→7 across docs; spec status → gate B OK (issue #15)" && git push origin main`

---

## DoD (Definition of Done)

1. Both simplicity twins carry the exclusion block; both test-design twins exist with the gradient (incl. best-practices boundary), the executable-test-surface filter, and the fenced Report Format; host twin has `thoughtLevel: max`.
2. Every roster carrier lists 7 names — including the auto-design runner argument list (primary) and the "7 host agents" fallback, the architect allowlist/dispatch/skip rule, and the best-practices 7-counts.
3. Reflect: `max_subagents` 8 in both sites; the two over-orchestration tests pass.
4. The scoped sweep returns zero panel-related hits; remaining hits justified.
5. Working tree clean after push; `git log` shows the task commits; the spec Status says gate B OK.

## Verification status at plan time (evidence, not tasks)

- **Panel feasibility of the runner path — PROVEN this cycle (2026-10-10):** the migrated `panel_review.sh` ran 6 real panelists in `panel-superagents` (2 batches), reports fetched and folded into spec v3; the container-wide lock (`panel.lock`, commit 8aaf086) serializes future runs.
- **Smoke (spec Testing item 2):** the first panel run of the next session includes `spec-panel-test-design` — verdict present, no completeness drift, no simplicity drift.
- **Pilot (spec Testing item 3):** the first DESIGN run after merge observes the two success criteria; recorded as an issue #15 comment; one run is directional signal (spec wording).
- **No-regression:** aggregation for 7 reports is verified by the next consolidated report.
