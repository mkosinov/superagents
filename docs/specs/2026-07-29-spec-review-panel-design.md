# Spec Review Panel — Design

**Date:** 2026-07-29
**Status:** Draft — awaiting user approval
**Author:** infra agent (brainstorming session with user)

**Placement:** SuperAgents is the framework source of truth — the panel (5 agents + brainstorming skill step + setup docs) lives here. The memo project (`/root/workspace/memo`) is the first instance: files are synced to `memo/.opencode/` and its project config. New projects onboarded via `docs/setup/new-project-setup.md` get the panel by default.

**Instance-specific values:** model IDs below are memo's setup (OpenCode Zen free tier via the `omniroute` provider). The framework files keep these as the reference default; instances may substitute equivalents (reserve list: `opencode-zen/north-mini-code-free`, `opencode-zen/laguna-s-2.1-free` — or any capable free model).

---

## Summary

After the architect writes a spec (end of brainstorming) and before writing-plans starts, a **panel of 5 subagents** reviews the spec. Each panelist runs on a different free OpenCode Zen model (via the `omniroute` provider) and analyzes the spec from a fixed perspective with its own prompt. The architect dispatches all 5 in parallel, aggregates their reports (dedup + severity ranking), and presents a single consolidated review to the user together with the spec. The user decides what to fix before approving the spec.

**Cost:** $0 — all panel models are free-tier in the OpenCode Zen subscription. Account selection and failover across the 3 configured opencode-zen accounts is handled by omniroute itself; no combos are created.

---

## Goals

- Catch spec problems **before** any plan or code exists: holes, risks, contradictions, overengineering, outdated approaches.
- Exploit model diversity: different LLMs notice different classes of issues.
- Exploit prompt diversity: each perspective has a dedicated system prompt.
- Keep zero marginal cost by using only free-tier models.

## Non-Goals

- The panel does **not** edit the spec — findings only.
- The panel does **not** replace the existing `spec-reviewer` Plan Review Mode (plan-vs-spec verification stays as is, after writing-plans).
- The panel does **not** replace the user review gate — it feeds into it.
- No omniroute combos, no account-balancing logic — omniroute's built-in account selection (fill-first with failover across the 3 opencode-zen accounts) is sufficient.

---

## User Scenarios

1. **Standard feature spec review.** User brainstorms a new feature with the architect. After the spec file is written and self-reviewed, the panel runs automatically. The user sees the spec plus a consolidated findings report (blockers/majors/minors) and decides: fix now, dismiss, or approve as-is.
2. **Panel catches a blocker.** The consistency reviewer finds that the spec contradicts an existing domain rule. The user asks the architect to revise the spec, the panel re-runs on the updated spec, then the user approves.
3. **Best-practices verification with research.** A spec introduces a new library integration. The best-practices reviewer dispatches researcher-agent, gets current community/vendor practices, and flags that the spec's approach is outdated. The user updates the approach before planning.
4. **Trivial spec skip.** A tiny change produces a short spec (< ~50 lines). The architect skips the panel and goes straight to user review, noting the skip.
5. **Model substitution.** One panelist consistently produces weak reports. The user asks infra to swap its model to one from the reserve list (`north-mini-code-free`, `laguna-s-2.1-free`) by editing one line in the agent file.

---

## Architecture

### Panel composition

| # | Perspective | Agent file | Model (via omniroute) | Looks for |
|---|-------------|-----------|----------------------|-----------|
| 1 | Completeness | `.opencode/agents/spec-review-completeness.md` | `omniroute/opencode-zen/big-pickle` | Holes, unhandled edge cases, missing user scenarios, unspecified error flows |
| 2 | Feasibility | `.opencode/agents/spec-review-feasibility.md` | `omniroute/opencode-zen/mimo-v2.5-free` | Technical risks, hidden complexity, unrealistic assumptions, unverified dependencies |
| 3 | Consistency | `.opencode/agents/spec-review-consistency.md` | `omniroute/opencode-zen/nemotron-3-ultra-free` | Contradictions within the spec; conflicts with existing code (reads the repo), domain rules, AGENTS.md |
| 4 | Simplicity / YAGNI | `.opencode/agents/spec-review-simplicity.md` | `omniroute/opencode-zen/deepseek-v4-flash-free` | Overengineering, unrequested scope, unjustified "for the future" features, needless complexity |
| 5 | Best Practices | `.opencode/agents/spec-review-best-practices.md` | `omniroute/opencode-zen/ling-3.0-flash-free` | Conformance to accepted best practices for the technologies/patterns used; **always** dispatches `researcher-agent` at least once per review |

**Reserve models** (for future substitution): `opencode-zen/north-mini-code-free`, `opencode-zen/laguna-s-2.1-free`.

### Agent configuration (all 5)

- `mode: subagent`, `temperature: 0.1`
- Permissions: `read`, `grep`, `glob` allow; `edit` deny; `bash` limited to read-only git/ls/cat (same as existing `spec-reviewer`); `task` deny
- Exception: **best-practices** agent additionally gets `task: { "researcher-agent": allow }`

### Common report format (all 5)

```markdown
## Findings
- [BLOCKER] <what> — <why> — <where in spec: section/quote>
- [MAJOR] ...
- [MINOR] ...

## Verdict
SOUND | SOUND_WITH_CONCERNS | NEEDS_REVISION
```

The best-practices agent additionally tags each finding: `[VERIFIED via research]` (backed by researcher-agent results) or `[SELF-ASSESSED]` (from the model's own knowledge).

### Best-practices research flow

1. Reads the spec, identifies technologies/libraries/frameworks/APIs/patterns involved.
2. Always dispatches `researcher-agent` with at least one query about current best practices for the identified external dependencies (for purely internal specs: one query about the dominant pattern, e.g. clean architecture layer separation in FastAPI/Next.js as applicable).
3. Compares spec decisions against research results and own knowledge of project conventions.
4. Reports deviations with severity and the verification tag.

### Workflow integration

New step in `.opencode/skills/brainstorming/SKILL.md`, inserted after "Spec self-review" and before "User reviews written spec":

**Spec Panel Review:**
1. Architect dispatches all 5 panelists **in parallel** (single message, 5 Task calls). Each dispatch prompt contains the spec file path and instructions to read it.
2. Architect waits for all 5 reports.
3. Architect aggregates: deduplicates overlapping findings, ranks by severity (BLOCKER → MAJOR → MINOR), notes which perspectives agree (agreement = stronger signal).
4. Architect presents the consolidated report to the user alongside the spec, asking: fix, dismiss, or approve.
5. If the user requests changes → architect revises spec → panel re-runs on the revision → back to step 4.
6. User review gate remains the hard block: no writing-plans until explicit spec approval.

**Skip rule:** the architect MAY skip the panel for trivial specs (< ~50 lines), stating the skip explicitly.

### opencode.jsonc changes

Add 5 entries under `provider.omniroute.models`:

```jsonc
"opencode-zen/big-pickle":            { "name": "Panel: Completeness (Big Pickle)",   "limit": { "context": 256000, "output": 64000 } },
"opencode-zen/mimo-v2.5-free":        { "name": "Panel: Feasibility (MiMo v2.5)",     "limit": { "context": 256000, "output": 64000 } },
"opencode-zen/nemotron-3-ultra-free": { "name": "Panel: Consistency (Nemotron Ultra)","limit": { "context": 256000, "output": 64000 } },
"opencode-zen/deepseek-v4-flash-free":{ "name": "Panel: Simplicity (DSv4 Flash)",     "limit": { "context": 256000, "output": 64000 } },
"opencode-zen/ling-3.0-flash-free":   { "name": "Panel: Best Practices (Ling Flash)", "limit": { "context": 256000, "output": 64000 } }
```

Context/output limits are placeholders to be verified against omniroute's actual model metadata at implementation time.

### architect.md changes

- `task` permission: allow `spec-review-completeness`, `spec-review-feasibility`, `spec-review-consistency`, `spec-review-simplicity`, `spec-review-best-practices`
- Brief aggregation instructions: dedup, severity ranking, agreement signal, consolidated presentation format

---

## Error handling

Availability policy: **retry → partial skip → full skip**.

- **Panelist fails or quota exhausted:** the architect retries the dispatch up to 2 more times (3 attempts total, short delay between). If still failing → the perspective is **skipped**, marked in the consolidated report as "perspective X unavailable (quota exhausted / error)", and the panel proceeds with the remaining reports. The user decides whether the partial panel is acceptable or wants to wait and re-run.
- **All 5 panelists unavailable (e.g., all zen quotas exhausted):** the entire panel is **skipped**. The architect explicitly warns the user ("spec panel skipped — all free models unavailable, spec not independently reviewed") and proceeds straight to the user review gate. The user may approve anyway or postpone until quotas reset.
- **Researcher-agent unavailable for best-practices:** the best-practices agent reports with all findings tagged `[SELF-ASSESSED]` and notes the research failure in its verdict.
- **Empty findings from all available panelists:** consolidated report states "all perspectives SOUND" and the flow proceeds to user review.

## Testing

- Manual end-to-end: run brainstorming on a real feature, verify all 5 dispatches fire in parallel, reports arrive, aggregation is coherent.
- Verify model routing: check omniroute call logs that requests went to the expected free models.
- Verify skip rule on a trivial spec.
- Verify re-run flow: request a spec change, confirm the panel re-runs on the revision.
- Verify availability policy: simulate one failing model (partial skip with warning) and all-failing (full skip with explicit warning before user review gate).

---

## Implementation outline (for writing-plans)

Framework repo (`/root/workspace/superagents/`):

1. Create 5 agent files in `agents/` (`spec-review-completeness.md`, `spec-review-feasibility.md`, `spec-review-consistency.md`, `spec-review-simplicity.md`, `spec-review-best-practices.md`)
2. Add the "Spec Panel Review" step to `skills/brainstorming/SKILL.md` (after spec self-review, before user review gate)
3. Update `agents/architect.md` (task permissions for the 5 panelists + aggregation instructions)
4. Update `docs/setup/new-project-setup.md` — new-project onboarding installs the panel; document model substitution for instances
5. Update `README.md` capabilities list (add spec review panel)

Memo instance (`/root/workspace/memo`):

6. Sync the 5 agent files + brainstorming SKILL.md + architect.md changes to `memo/.opencode/`
7. Add 5 model entries (`opencode-zen/*` via omniroute) to `~/.config/opencode/opencode.jsonc`
8. Smoke-test each model via omniroute (single dispatch each)
9. Regenerate `~/.config/opencode/infrastructure.md`
