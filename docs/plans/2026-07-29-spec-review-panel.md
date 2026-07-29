# Spec Review Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 5-model free-tier spec review panel to the SuperAgents framework and sync it into the memo instance.

**Architecture:** 5 new read-only subagents (one per review perspective, each on a different free OpenCode Zen model via the `omniroute` provider) are dispatched in parallel by the architect after spec self-review and before the user review gate. The architect aggregates their reports (dedup + severity) and presents a consolidated review with the spec. Framework files live in `/root/workspace/superagents/` (source of truth) and are synced to `/root/workspace/memo/.opencode/` (first instance).

**Tech Stack:** OpenCode agent configs (YAML frontmatter markdown), opencode.jsonc provider model entries, SuperAgents framework repo layout.

**Spec:** `/root/workspace/superagents/docs/specs/2026-07-29-spec-review-panel-design.md` (approved 2026-07-29)

---

## Behavioral Delta

How this feature behaves for the user, mapped to spec acceptance criteria:

- **Panel runs automatically after every non-trivial spec** → After the architect writes a spec, the user receives the spec plus a consolidated findings report (BLOCKER/MAJOR/MINOR) from 5 different model perspectives, before being asked to approve.
- **Different models notice different things** → Findings are labeled by perspective (completeness / feasibility / consistency / simplicity / best-practices); when several perspectives flag the same issue, the report says so.
- **Best practices are checked against current sources** → The best-practices perspective verifies the spec's technology choices via web research and tags each finding `[VERIFIED via research]` or `[SELF-ASSESSED]`.
- **Zero cost** → All panel models are free-tier; no paid tokens are consumed by the panel.
- **Quotas exhausted → graceful degradation** → If one model is unavailable (after retries), its perspective is skipped with a visible note; if all 5 are unavailable, the panel is skipped entirely with an explicit warning, and the flow goes straight to user review.
- **Trivial specs skip the panel** → For specs under ~50 lines the architect states "panel skipped (trivial spec)" and goes straight to user review.
- **Panel never edits the spec** → The user sees findings and decides: fix (panel re-runs on the revision), dismiss, or approve.

---

## File Structure

**Framework repo (`/root/workspace/superagents/`):**

| File | Action | Responsibility |
|------|--------|----------------|
| `agents/spec-review-completeness.md` | create | Holes/edge-cases perspective, model `omniroute/opencode-zen/big-pickle` |
| `agents/spec-review-feasibility.md` | create | Technical-risk perspective, model `omniroute/opencode-zen/mimo-v2.5-free` |
| `agents/spec-review-consistency.md` | create | Internal/repo/domain consistency perspective, model `omniroute/opencode-zen/nemotron-3-ultra-free` |
| `agents/spec-review-simplicity.md` | create | YAGNI/overengineering perspective, model `omniroute/opencode-zen/deepseek-v4-flash-free` |
| `agents/spec-review-best-practices.md` | create | Best-practices perspective with researcher-agent dispatch, model `omniroute/opencode-zen/ling-3.0-flash-free` |
| `skills/brainstorming/SKILL.md` | modify | Insert "Spec Panel Review" step between spec self-review and user review gate |
| `agents/architect.md` | modify | Add task permissions for 5 panelists + aggregation instructions |
| `docs/setup/new-project-setup.md` | modify | Document panel installation for new projects + model substitution |
| `README.md` | modify | Add panel to capabilities list |

**Memo instance (`/root/workspace/memo` + global config):**

| File | Action | Responsibility |
|------|--------|----------------|
| `.opencode/agents/spec-review-*.md` | create (sync from framework) | 5 panelist agent configs |
| `.opencode/skills/brainstorming/SKILL.md` | modify (sync from framework) | Panel step |
| `.opencode/agents/architect.md` | modify (sync from framework) | Permissions + aggregation |
| `~/.config/opencode/opencode.jsonc` | modify | 5 model entries under `provider.omniroute.models` |
| `~/.config/opencode/infrastructure.md` | regenerate | Infra reference update |

---

## Task 1: Create the 4 simple panelist agents (framework)

### Classification: standard

### Required Docs
- `/root/workspace/superagents/docs/specs/2026-07-29-spec-review-panel-design.md` — panel composition table, report format
- `/root/workspace/superagents/agents/spec-reviewer.md` — existing agent frontmatter/permission pattern to mirror

### Task Description

Create 4 agent files in `/root/workspace/superagents/agents/`. All share the same frontmatter shape (read-only subagent, temperature 0.1) and differ only in `description`, `model`, and the perspective prompt body.

**Frontmatter template (identical except `description` and `model`):**

```yaml
---
description: <one line from panel table>
mode: subagent
model: <model from panel table>
temperature: 0.1
permission:
  read: allow
  grep: allow
  glob: allow
  edit: deny
  bash:
    "git diff*": allow
    "git log*": allow
    "git show*": allow
    "ls*": allow
    "cat*": allow
    "*": deny
  task:
    "*": deny
---
```

**Models (from spec):**
- `spec-review-completeness.md` → `omniroute/opencode-zen/big-pickle`
- `spec-review-feasibility.md` → `omniroute/opencode-zen/mimo-v2.5-free`
- `spec-review-consistency.md` → `omniroute/opencode-zen/nemotron-3-ultra-free`
- `spec-review-simplicity.md` → `omniroute/opencode-zen/deepseek-v4-flash-free`

**Shared body skeleton (each file):** role statement for the perspective → input contract ("You receive a spec file path in the dispatch prompt. Read it with the read tool.") → perspective-specific checklist → mandatory report format:

```markdown
## Findings
- [BLOCKER] <what> — <why> — <where in spec: section/quote>
- [MAJOR] ...
- [MINOR] ...

## Verdict
SOUND | SOUND_WITH_CONCERNS | NEEDS_REVISION
```

**Perspective checklists:**

- **Completeness:** unhandled edge cases; missing user scenarios vs spec's `## User Scenarios`; unspecified error/failure flows; undefined empty states; implicit assumptions never stated.
- **Feasibility:** technical risks; hidden complexity (distributed state, migrations, concurrency); unrealistic assumptions about libraries/APIs; unverified external dependencies; performance red flags.
- **Consistency:** contradictions between spec sections; conflicts with existing code (read the repo — follow imports/paths the spec mentions); conflicts with `docs/domain-rules/` and AGENTS.md conventions; naming/terminology drift.
- **Simplicity:** scope not derivable from the stated goal; "for the future" features without justification; needless abstraction layers; simpler existing alternative in the codebase being ignored.

### Steps

- [ ] Write `agents/spec-review-completeness.md` (frontmatter + body per above)
- [ ] Write `agents/spec-review-feasibility.md`
- [ ] Write `agents/spec-review-consistency.md`
- [ ] Write `agents/spec-review-simplicity.md`
- [ ] Verify all 4: YAML frontmatter parses (no tabs, quoted globs), report format block present verbatim
- [ ] Commit: `git add agents/spec-review-*.md && git commit -m "agents: add 4 spec review panelists (completeness, feasibility, consistency, simplicity)"`

---

## Task 2: Create the best-practices panelist agent (framework)

### Classification: standard

### Required Docs
- `/root/workspace/superagents/docs/specs/2026-07-29-spec-review-panel-design.md` — best-practices research flow section
- Task 1 files — shared skeleton

### Task Description

Create `/root/workspace/superagents/agents/spec-review-best-practices.md`. Same skeleton as Task 1 with three differences:

1. `model: omniroute/opencode-zen/ling-3.0-flash-free`
2. Permission block adds researcher dispatch:
   ```yaml
   task:
     "researcher-agent": allow
     "*": deny
   ```
3. Body includes the **mandatory research flow** (from spec):
   - Identify technologies/libraries/frameworks/APIs/patterns in the spec.
   - **ALWAYS dispatch `researcher-agent` at least once per review** with a query about current best practices for the identified external dependencies; for purely internal specs, one query about the dominant pattern (e.g. clean-architecture layer separation in FastAPI/Next.js as applicable).
   - Compare spec decisions against research results + own knowledge of project conventions.
   - Tag every finding `[VERIFIED via research]` or `[SELF-ASSESSED]`.
   - If researcher-agent fails/is unavailable: note the failure in the verdict section, report all findings as `[SELF-ASSESSED]`.

### Steps

- [ ] Write `agents/spec-review-best-practices.md`
- [ ] Verify: `task` permission block exactly as above; research-flow section present; report format block verbatim
- [ ] Commit: `git add agents/spec-review-best-practices.md && git commit -m "agents: add best-practices spec panelist with researcher-agent dispatch"`

---

## Task 3: Add Spec Panel Review step to brainstorming skill (framework)

### Classification: standard

### Required Docs
- `/root/workspace/superagents/skills/brainstorming/SKILL.md` — current checklist (lines 24-43) and spec self-review section
- Spec — workflow integration section (6 numbered steps + skip rule)

### Task Description

Modify `/root/workspace/superagents/skills/brainstorming/SKILL.md`:

1. **Checklist (lines 26-38):** renumber — insert new step 7 "Spec Panel Review" after step 6 (spec self-review); old steps 7-9 become 8-10.
2. **Process Flow diagram (line 43):** change to `... → Write design doc → Spec self-review → Spec panel review → User reviews spec? → Invoke writing-plans skill`.
3. **New section** after the "Spec Self-Review" section, before "User Review Gate (BLOCKING)":

```markdown
**Spec Panel Review (automated — runs BEFORE the user gate):**

After the spec self-review passes, run the spec review panel — 5 parallel subagents, each analyzing the spec from one perspective:

| Perspective | Subagent |
|-------------|----------|
| Completeness | `spec-review-completeness` |
| Feasibility | `spec-review-feasibility` |
| Consistency | `spec-review-consistency` |
| Simplicity / YAGNI | `spec-review-simplicity` |
| Best Practices | `spec-review-best-practices` |

1. Dispatch all 5 **in parallel** (single message, 5 Task calls). Each dispatch prompt MUST contain the spec file path and instruct the panelist to read it.
2. Wait for all reports.
3. Aggregate: deduplicate overlapping findings, rank BLOCKER → MAJOR → MINOR, note where perspectives agree (agreement = stronger signal).
4. Present the consolidated report to the user alongside the spec. Ask: fix, dismiss, or approve.
5. If the user requests changes → revise the spec → re-run the panel on the revision → back to step 4.

**Skip rule:** you MAY skip the panel for trivial specs (< ~50 lines). State the skip explicitly.

**Availability policy (retry → partial skip → full skip):**
- Panelist fails → retry up to 2 more times (3 attempts total). Still failing → skip that perspective, mark "perspective X unavailable (quota exhausted / error)" in the consolidated report, proceed with the rest.
- ALL 5 unavailable → skip the panel entirely, warn the user explicitly ("spec panel skipped — all free models unavailable, spec not independently reviewed"), proceed to the user review gate.
```

### Steps

- [ ] Apply the three edits to `skills/brainstorming/SKILL.md`
- [ ] Verify: checklist has 10 steps ending with writing-plans transition; new section present before user review gate; diagram updated
- [ ] Commit: `git add skills/brainstorming/SKILL.md && git commit -m "skills: add spec panel review step to brainstorming workflow"`

---

## Task 4: Update architect agent — permissions + aggregation (framework)

### Classification: small

### Required Docs
- `/root/workspace/superagents/agents/architect.md` — frontmatter permission block (lines 33-40) and Plan Review section (~lines 370-374) for tone/pattern

### Task Description

Modify `/root/workspace/superagents/agents/architect.md`:

1. **Frontmatter `task:` permission block** — add before the `"*": allow` line:
   ```yaml
     "spec-review-completeness": allow
     "spec-review-feasibility": allow
     "spec-review-consistency": allow
     "spec-review-simplicity": allow
     "spec-review-best-practices": allow
   ```
2. **Body** — add a short subsection near the Plan Review instructions:

```markdown
### Spec Panel aggregation (brainstorming step)

When running the Spec Panel Review (see brainstorming skill):
- Dispatch all 5 panelists in parallel, each with the spec file path.
- Aggregate: deduplicate overlapping findings, rank BLOCKER → MAJOR → MINOR, note agreement across perspectives.
- Present one consolidated report next to the spec; the user decides fix / dismiss / approve. The panel never edits the spec itself.
- Apply the retry → partial skip → full skip availability policy from the brainstorming skill.
```

### Steps

- [ ] Apply both edits to `agents/architect.md`
- [ ] Verify: YAML still valid; new subsection present
- [ ] Commit: `git add agents/architect.md && git commit -m "agents: architect — panelist permissions + aggregation instructions"`

---

## Task 5: Update setup docs + README (framework)

### Classification: small

### Required Docs
- `/root/workspace/superagents/docs/setup/new-project-setup.md` — Steps 1-4 structure
- `/root/workspace/superagents/README.md` — capabilities bullet list (~lines 13-21)

### Task Description

1. **`docs/setup/new-project-setup.md`:**
   - Step 1 (copy agents): add a note that the 5 `spec-review-*.md` files are copied along with the rest by the existing `cp agents/*.md` command — no change to the command, just mention the panel in surrounding text.
   - Add a new subsection after Step 4: "Step 5: Configure Spec Review Panel models" explaining:
     - The panel ships with 5 panelists; each needs a model entry resolvable by the instance's providers.
     - Reference default (memo instance): free OpenCode Zen models via the `omniroute` provider — list the 5 `opencode-zen/*` model IDs from the spec.
     - Model substitution: to swap a panelist's model, edit the `model:` line in the corresponding `.opencode/agents/spec-review-*.md`. Reserve pool: `opencode-zen/north-mini-code-free`, `opencode-zen/laguna-s-2.1-free`, or any capable free model.
     - If no free models are available in a project, the panel can be skipped per-spec (see brainstorming skill skip/availability rules).
2. **`README.md`:** add one bullet to the capabilities list:
   ```markdown
   - **Spec review panel** — 5 parallel free-model perspectives review every spec before user approval
   ```

### Steps

- [ ] Edit `docs/setup/new-project-setup.md` per above
- [ ] Edit `README.md` per above
- [ ] Commit: `git add docs/setup/new-project-setup.md README.md && git commit -m "docs: spec review panel in setup guide and README"`

---

## Task 6: Sync panel into memo instance

### Classification: small

### Required Docs
- Framework files from Tasks 1-4 (source content)
- `/root/workspace/memo/.opencode/agents/architect.md` — check for memo-local drift vs framework before overwriting (diff first; memo's architect may carry project-specific sections that must be preserved)

### Task Description

Copy framework files into the memo instance:

1. `cp /root/workspace/superagents/agents/spec-review-*.md /root/workspace/memo/.opencode/agents/` (5 files)
2. Brainstorming skill: memo's copy is currently identical to framework — `cp /root/workspace/superagents/skills/brainstorming/SKILL.md /root/workspace/memo/.opencode/skills/brainstorming/SKILL.md`
3. Architect: **diff first** (`diff /root/workspace/superagents/agents/architect.md /root/workspace/memo/.opencode/agents/architect.md`). If memo's copy only differs in ways already covered by Task 4's edits → overwrite with framework version. If memo has local drift (project-specific sections) → apply Task 4's two edits manually to memo's copy instead, preserving local content.

### Steps

- [ ] Copy 5 panelist files to memo
- [ ] Copy brainstorming SKILL.md to memo
- [ ] Diff architect.md; sync per rule above
- [ ] Verify: `ls /root/workspace/memo/.opencode/agents/spec-review-*.md` → 5 files; memo SKILL.md contains "Spec Panel Review"
- [ ] Commit in memo: `git add .opencode/ && git commit -m "chore: sync spec review panel from superagents framework"`

---

## Task 7: Register 5 models in opencode.jsonc

### Classification: small

### Required Docs
- `~/.config/opencode/opencode.jsonc` — `provider.omniroute.models` block (~lines 61-118) for entry format
- Spec — opencode.jsonc changes section (exact entry names/limits)

### Task Description

**Backup first:** `cp ~/.config/opencode/opencode.jsonc ~/.config/opencode/opencode.jsonc.bak-<timestamp>`.

Add 5 entries to `provider.omniroute.models` (after the existing `kmc/k3-256k` / `opencode-go/*` entries, same object):

```jsonc
"opencode-zen/big-pickle": {
  "name": "Panel: Completeness (Big Pickle)",
  "limit": { "context": 256000, "output": 64000 }
},
"opencode-zen/mimo-v2.5-free": {
  "name": "Panel: Feasibility (MiMo v2.5)",
  "limit": { "context": 256000, "output": 64000 }
},
"opencode-zen/nemotron-3-ultra-free": {
  "name": "Panel: Consistency (Nemotron Ultra)",
  "limit": { "context": 256000, "output": 64000 }
},
"opencode-zen/deepseek-v4-flash-free": {
  "name": "Panel: Simplicity (DSv4 Flash)",
  "limit": { "context": 256000, "output": 64000 }
},
"opencode-zen/ling-3.0-flash-free": {
  "name": "Panel: Best Practices (Ling Flash)",
  "limit": { "context": 256000, "output": 64000 }
}
```

Note (from spec): context/output limits are placeholders — verify against omniroute's actual model metadata and adjust if omniroute reports smaller limits for any model.

### Steps

- [ ] Backup opencode.jsonc
- [ ] Add the 5 entries
- [ ] Validate JSON: `node -e "JSON.parse(require('fs').readFileSync(process.env.HOME+'/.config/opencode/opencode.jsonc','utf8').replace(/\/\/.*$/gm,'').replace(/\/\*[\s\S]*?\*\//g,''))"` (strip comments then parse) — or open opencode and confirm no config error
- [ ] Verify with `cat` that entries are present and well-formed
- [ ] Do NOT commit (file is outside the memo repo)

---

## Task 8: Smoke-test panel models via omniroute + regenerate infra doc

### Classification: small

### Required Docs
- `/root/workspace/memo/.opencode/skills/dev-workflow/SKILL.md` — if needed for environment rules
- Task 7 output (models must be registered first)

### Task Description

Verify each of the 5 models actually responds through omniroute, then regenerate the infrastructure reference.

1. **Smoke test each model** — for each of the 5 model IDs, send a minimal request through the omniroute OpenAI-compatible endpoint:
   ```bash
   curl -s http://omniroute:20128/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "opencode-zen/<MODEL>", "messages": [{"role":"user","content":"Reply with exactly: OK"}], "max_tokens": 16}'
   ```
   Expected: JSON response containing "OK". Record any model that errors (check omniroute logs: `docker logs omniroute --tail 50`).
2. **Full-panel dry run** (optional but recommended): dispatch one Task call to `spec-review-simplicity` with a path to any existing small spec in memo `docs/specs/` and confirm it returns the Findings/Verdict format.
3. **Regenerate infra reference:** `~/.config/opencode/update-infrastructure.sh`

### Steps

- [ ] Smoke test all 5 models via curl — all return "OK"
- [ ] If any model fails: check omniroute logs, note the failure, report to user (do NOT silently substitute)
- [ ] Optional dry run of one panelist subagent
- [ ] Run `~/.config/opencode/update-infrastructure.sh`
- [ ] Report: per-model status table + any config-limit adjustments made in Task 7

---

## Self-Review

- **Spec coverage:** panel composition (T1, T2, T7) ✓; report format (T1, T2) ✓; research flow (T2) ✓; workflow integration (T3) ✓; architect aggregation (T4) ✓; setup docs/README (T5) ✓; memo sync (T6, T7) ✓; error handling/availability (T3 skill text, T8 verification) ✓; testing (T8) ✓; infra regen (T8) ✓.
- **Placeholders:** none — all file contents and commands are literal.
- **Type consistency:** agent file names and model IDs match across tasks and spec.
- **Required Docs:** every task has a section; no entity/domain-rules docs needed (framework/config change, no business entities). E2E-mapping: this is a workflow/config feature — spec's User Scenarios are verified via the manual E2E in Task 8 rather than code tests (nothing to unit-test in markdown configs).
