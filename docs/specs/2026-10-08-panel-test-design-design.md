# Panel Test-Design Reviewer (7th Panelist) + Simplicity Mandate Surgery — Design

**Date:** 2026-10-08
**Status:** Spec OK (gate B 2026-10-10), plan approved (gate C 2026-10-10) — in IMPL
**Author:** auto-design watcher session (host, zcode)

**Placement:** SuperAgents is the framework source of truth. The panel runs in the opencode container on zen free models via the repo's own runner `.opencode/scripts/panel_review.sh` (migrated from the memo project 2026-10-10 by user decision — no cross-repo dependency); host dispatch is the fallback. Canon bodies live in `.opencode/agents/`, host-port twins in `.zcode/agents/`. Projects receive the change via git (host ports are the reference seeds; containers sync `.opencode/` from canon on pull).

**Registry note:** the container runner spawns ephemeral opencode servers that read agent definitions fresh from its clean clone on every run — the 7th panelist needs no restart there. On the host (fallback path) registration happens at session start: after the files land, the 7th panelist becomes dispatchable from the **next** host session.

**Scout corrections baked in (2026-10-08):** the issue's `omniroute/panel-test-design` model id is stale (the omniroute gateway was removed 2026-10-08, commit 0b9e785 + migration commit ec39dbf); the new agent follows current conventions — host twin pins the zai coding-plan model, canon twin pins an opencode zen free model. The issue's "architect / brainstorming dispatch lists" claim is partially stale: brainstorming no longer enumerates the roster; the real carriers are listed in the Workflow integration table below. The issue's "6 panels" target is stale: the roster is already 6 (security landed via #16); this change makes it 7.

**Frame decision (user, 2026-10-10):** the perspective is framed positively — a test must exercise the functionality it claims, to the full extent needed (data that discriminates correct from incorrect behavior, assertions covering the expected result). Not adversarially — not "surround the code with tests detecting false behavior" and not enumerating hypothetical regressions (their space is infinite). The legacy phrase "regression pin" is retired. Wrong-reason passes are a SYMPTOM of under-exercising; the finding names what is missing (better data, fuller assertions), never a bolt-on guard. Simplicity keeps the right to propose test economies (merging similar tests, dropping steps that assert nothing) — it loses only the calls that change what a test verifies, which become test-design's to judge.

---

## Summary

Two-part change to the spec review panel:

1. **Simplicity mandate surgery.** The simplicity panelist keeps proposing economies, including test economies — but economies that change what a test verifies move out of its mandate: reducing a test's exercise below the functionality it claims, merging tests of different contracts, deriving identifiers/config by string tricks, folding one concern into another endpoint's contract. Verification-preserving economies (merging true duplicates, dropping steps that assert nothing) stay legitimate simplicity ground, proposed WITH the preservation argument. The four memo-project precedents are cited in its body as the excluded direction.
2. **New always-on 7th panelist, `spec-panel-test-design`.** Owns the verification quality of every test a spec defines, through three positive questions — exercise completeness, non-duplication, failure localizability — plus AC testability. It is the standing judge that weighs economy proposals against verification, and the standing counterweight that turns the architect's repeated ad hoc rulings into a permanent panel voice.

The panel grows from 6 to **7 parallel reviewers**; dispatch, aggregation, availability policy, and report contract are unchanged — only the count and roster grow, plus one gradient note separating test-design from completeness.

**Deferred (deliberately NOT built):** conditional dispatch for any panelist (always-on vs economics is issue #17's ground); changes to the other four panelists' mandates; pilot automation (the pilot is a field observation of the next DESIGN run, recorded in the issue — no tooling).

---

## Context / Problem (memo-project evidence, 29–40 panel runs per perspective)

Simplicity had the highest dismiss-rate on large proposals, and every dismiss pushed in one direction — fewer lines at the cost of tests or contracts:

- **#216**: rejected a "minimal" 1-client e2e that stayed green with the feature broken — its data did not discriminate (any result read as success) and its assertions did not cover the expected result. The kept version exercised the functionality properly.
- **#184**: proposed merging the `is_active` preserve/explicit test pairs. The merge itself was acceptable in principle; the harm was in what the merged form lost — unlabeled assertions (a failure did not say which contract broke) and state coupling (the second scenario depended on the first's side effects). Resolved with best-practices: 5 tests with labeled assertions.
- **D15**: proposed deriving `not_found_code` via `rstrip('s')` — factually wrong (breaks on `activities` → `ACTIVITIE`); explicit config kept.
- **#186**: proposed `total_paid` as a correlated subquery inside `GET /records` — rejected: couples aggregation to pagination/filtering and changes the contract for all consumers while only one needs the sum.
- Accepted simplicity hits were small MINORs (type alias placement, layering) plus one joint BLOCKER (with completeness).

The problem is not reliability (simplicity is the cheapest panel, ~176k avg input tokens, 10/12 recent runs recoverable). It is mandate: "fewer lines" vs "does the test still verify what it claims" has been arbitrated ad hoc by the architect (the main session) on every occurrence. This spec moves both sides into standing mandates.

Why a separate panelist rather than a completeness checklist: completeness asks "are all scenarios covered" (more tests); test-design asks "does each defined test verify its claimed functionality, without duplication, with localizable failures" (including "this test under-exercises" and "these two are duplicates — merge them"). Opposite gradients in one head reproduce the same conflict simplicity has today — inverted. A separate voice + architect as arbiter mirrors the setup that already resolved #184.

---

## Goals

- End the ad hoc architect arbitration: both sides of "fewer lines vs still verifies" get a standing panel voice.
- Keep simplicity strong on its real ground: scope/YAGNI, speculative complexity, layering, reuse — including verification-preserving test economies, argued as such.
- Make verification quality someone's explicit job on every spec: exercise completeness, non-duplication, localizability, AC testability.
- Codify the gradient separation (coverage-of-scenarios vs verification-quality) in the roster carrier so future edits keep them apart.
- Keep the panel's shape unchanged: one dispatch message, shared report contract, same aggregation — only the count grows.

## Non-Goals

- No new gate, no new manual step: the 7th report folds into the existing consolidated report (dedupe → rank → one report).
- No change to gate C / `plan-reviewer` / IMPL — the test-design view applies to specs only.
- No conditional dispatch logic for the new panelist (economics is issue #17's ground; practically every spec in this repo defines User Scenarios, so the perspective is needed on nearly every run — and a trigger is maintenance the always-on choice avoids).
- No test-writing by the panelist: it flags under-exercised, duplicated, unlocalizable test definitions in the spec; it does not author tests.

---

## User Scenarios

1. **Every spec run — 7 reports.** A design cycle dispatches the panel; seven reports return (six existing + test-design); the consolidated report aggregates all seven. *Check (mechanical):* every roster carrier lists 7 names and says "After all 7 return" (or equivalent); *check (field):* the next design session's panel step returns 7 reports.
2. **Economy weighed, not vetoed.** A spec proposes merging two similar e2e tests. Simplicity proposes the merge WITH the argument that both verify the same functionality (allowed ground). Test-design weighs it: true duplicates with independent, labeled checks → agrees (merge); different contracts or state-coupled scenarios → flags what the merge loses (typically `[MAJOR]`). The architect aggregates two argued positions instead of arbitrating from scratch. *Check (field, pilot).*
3. **Under-exercised test caught.** A spec defines a test whose data does not discriminate (a single-case "minimal" e2e that stays green with the feature broken) or whose assertions do not cover the expected result. Test-design flags it (`[MAJOR]`): the finding names what is missing — discriminating data, fuller assertions — per the frame decision, not "add guards". *Check (mechanical):* the exercise-completeness wording is in both bodies; *check (field, pilot).*
4. **Untestable acceptance criterion.** A User Scenario's acceptance criterion cannot be checked as written (no observable outcome). The test-design panelist flags it (`[MAJOR]`): the criterion maps to no verifiable check. *Check (field, pilot).*
5. **No-test-surface spec stays quiet.** A spec whose scenarios carry no executable checks (e.g. a docs-only change verified by a mechanical `## Verification` checklist). The test-design panelist returns the standard empty form `(none — no test surface: <one sentence naming why>)` + `SOUND` — it does not invent findings; mechanical doc checklists are not a test surface. *Check (mechanical):* the filter wording in both bodies; *check (field):* rides the smoke/pilot runs — a fast-track spec never meets the panel, so the observation waits for any STANDARD spec without executable checks.*
6. **Panelist unavailable.** The test-design panelist fails to return (crash, timeout). Existing availability policy applies identically: one rerun, then marked `skipped` with the reason in the consolidated report; the verdict rests on the rest. *Check (policy reuse):* no new code path — verified by the next consolidated report if it ever fires.

---

## Behavioral Delta

- **Before:** every spec run returns 6 panel reports; simplicity may push test economies that change what tests verify (minimal e2e, unlabeled merges, derivation tricks), and the architect re-arbitrates "fewer lines vs still verifies" from scratch each time — the same rulings re-derived run after run (#216, #184, D15, #186 all ended as architect dismissals).
- **After:** every spec run returns 7 panel reports; verification quality has a standing owner whose findings rank in the consolidated report like any other perspective; simplicity's mandate draws the line at verification-changing economies (with the dismissed precedents cited), while verification-preserving economies remain its legitimate ground; the architect aggregates two standing, argued perspectives instead of arbitrating ad hoc.

---

## Visual Compliance Checks

- N/A — text-only harness change; no visual surface.

---

## Architecture

### Panel composition (after the change)

| # | Perspective | Agent files | Model | Looks for |
|---|-------------|------------|-------|-----------|
| 1–6 | completeness, consistency, feasibility, simplicity, best-practices, security | existing `spec-panel-*.md` twins | unchanged | unchanged (except simplicity: mandate surgery below) |
| 7 | **Test design** | `.opencode/agents/spec-panel-test-design.md` (canon) + `.zcode/agents/spec-panel-test-design.md` (host-port twin) | canon: `opencode/nemotron-3-ultra-free` (zen free class; the pin is shared with feasibility deliberately — model sharing is accepted when chosen, precedent: plan-reviewer shares a panelist's pin; Appendix A is definitive); host: `"account:zai-individual-coding-plan/GLM-5.3-Flash"` (current host convention, commit ec39dbf) | exercise completeness, non-duplication, failure localizability, AC testability; weighs spec-proposed economies against verification; explicit no-test-surface verdict when the spec defines none |

### Simplicity mandate surgery (both twins, identical block)

Inserted after the "What you look for" list, before "Report Format" (same placement pattern as the security panelist's scope note):

> Out of scope BY DESIGN: economies that change what a test verifies or what a contract promises. Reducing a test's exercise below the functionality it claims — the "minimal" 1-client e2e stayed green with the feature broken (#216). Merging tests of different contracts — the is_active preserve/explicit pairs each verify a different rule (#184; merging same-function duplicates is fine when checks are independent and labeled). Deriving identifiers/config by string tricks — `rstrip('s')` broke on `activities` (D15). Folding one concern into another endpoint's contract — `total_paid` as a subquery inside `GET /records` changed the contract for all consumers (#186). Such calls belong to the test-design panelist. Verification-preserving economies (merging true duplicates, dropping steps that assert nothing) are your legitimate ground — propose them WITH the preservation argument.

Nothing else in the simplicity bodies changes: the intro line, the kept checklist (scope, "for the future", needless abstraction, simpler existing alternative, reuse check), the report format, and the one-sentence-direction constraint all stay. On insert, the block lands as a plain paragraph (form follows the security panelist's scope note) — the blockquote marker above is this document's rendering, not part of the file text.

### The new panelist's distinguishing rules

- **Gradient block** (first body section, keeps the panelist off completeness's ground): completeness asks whether all scenarios are covered — missing tests are completeness's findings; test-design asks whether each defined test verifies its claimed functionality, without duplication, with localizable failures — under-exercised, duplicated, unlocalizable tests are its findings. Wanting another test is completeness's voice; staying silent about it is correct unless an existing test's verification quality is the problem. Boundary vs best-practices: it may cite external testing practice, but the judgment about THIS spec's tests belongs to test-design — when both flag the same line, the architect's dedupe absorbs the overlap (the #184 resolution pattern).
- **Checklist (three positive questions + two standing duties):**
  - *Exercise completeness:* every test must exercise the functionality it claims to the full extent needed — data that discriminates correct from incorrect behavior (not a single-case minimum), assertions covering the expected result. Internal check that generates findings: if the claimed functionality broke, would this test fall? A test that stays green has under-exercising data or missing assertions — name what is missing. The fix is always better data or fuller assertions, never a bolt-on guard.
  - *Non-duplication:* one functionality ≈ one test; duplicate coverage is a finding to merge — but only merge checks that are independent; a state-mutating scenario coupled into another test makes that test's failures ambiguous.
  - *Localizability:* on failure it must be visible which rule broke — assertions labeled and tied to one decision; scenarios not chained through side effects.
  - *AC testability:* every acceptance criterion in the spec must be checkable as written — an untestable criterion maps to no verifiable check.
  - *Economies vs verification:* when the spec proposes an economy on tests or contracts (merging, dropping steps, deriving config, folding endpoints), judge whether it preserves what tests verify; flag reductions of exercise below the claim and contract changes (#216, #184, D15, #186 are the pattern).
- **The filter (mandatory):** a spec with no executable test surface — no tests or e2e scenarios with data and assertions (a prose spec whose only verification is a mechanical `## Verification` checklist counts as no test surface) — gets the standard empty form `(none — no test surface: <one sentence naming why>)` + `SOUND` — no invented findings.
- **Report contract:** shared with all panelists — `[BLOCKER]/[MAJOR]/[MINOR]` findings + `SOUND | SOUND_WITH_CONCERNS | NEEDS_REVISION`; no test-design-specific tags.

### Workflow integration (files changed)

| File | Change |
|---|---|
| `.opencode/agents/spec-panel-simplicity.md` | mandate surgery block (above), nothing else |
| `.zcode/agents/spec-panel-simplicity.md` | same block (host-port twin stays a faithful port) |
| `.opencode/agents/spec-panel-test-design.md` | **new** — canon body (Appendix A) |
| `.zcode/agents/spec-panel-test-design.md` | **new** — host-port twin (Appendix B) |
| `.opencode/skills/panel-spec-review/SKILL.md` | roster table +1 row (test-design, read-only access); "All 6 are read-only leaf agents" → All 7; "After all 6 return" → After all 7; gradient note under the roster: completeness = coverage of scenarios (missing tests), test-design = verification quality of defined tests (under-exercised, duplicated, unlocalizable) — opposite gradients, separate panelists |
| `.zcode/skills/design-phase/SKILL.md` | frontmatter description "spec + 6-reviewer panel" → 7-reviewer; §4 dispatch line "6 agents in parallel" → 7 + `spec-panel-test-design` appended to the name list; "collect the 6 reports" (if present) → 7 |
| `.zcode/skills/auto-design/SKILL.md` | Step 5, TWO sites in one line: append `spec-panel-test-design` to the container-runner command's agent argument list (the PRIMARY path — the list carries no count digit, so no count-based sweep can catch it) AND the fallback clause "the 6 host agents (`.zcode/agents/`) in one parallel dispatch" → 7 host agents. Step 7's plan-reviewer invocation is single-agent — no change |
| `.opencode/agents/architect.md` | task permission allowlist + `"spec-panel-test-design": allow`; dispatch line: "Dispatch all 6 panelists (…)" → all 7 with the name appended, "6 Task calls" → 7; "ALL 6 unavailable → skip the panel entirely" → ALL 7 |
| `.opencode/agents/spec-panel-best-practices.md` + `.zcode/agents/spec-panel-best-practices.md` | body prose counts (quote-anchored, line numbers drift): "the other 5 panelists" → "the other 6 panelists"; "aggregates all 6 reports" → "aggregates all 7 reports" |
| `.opencode/skills/reflect/scripts/lib/workflow_checks.py` (+ `tests/test_workflow_checks.py`) | over-orchestration default max subagents per parent: 6 → 8; test fixture updated to fire at 9 — a 7-panelist host dispatch becomes the designed norm, not a violation |
| `docs/workflow/design-phase.md` | count sites, quote-anchored (line numbers drift across revisions): table row `Spec panel ×6` → ×7; diagram `6 parallel independent agents` → 7; the spelled-out roster sentence (`Six independent parallel perspectives…` where present) → Seven + the name appended — sweep-caught |
| `README.md` | count sites 6 → 7 (e.g. mermaid edge "panel report ×6", perspective counts) — caught by the grep sweep, not enumerated by hand |
| `docs/setup/new-project-setup.md` | the count site `6-perspective` → 7-perspective, fixing its stale attribution in the same sentence — the panel is dispatched by the DESIGN-phase skills (design-phase/auto-design), not by the brainstorming skill; no per-panelist roster table exists there (model rows are wildcarded `spec-panel-*`) |

**Grep sweep (plan DoD):** case-insensitive, scoped to the harness carriers and docs (`README.md`, `docs/` minus `docs/specs/` + `docs/plans/`, `.zcode/`, `.opencode/agents/`, `.opencode/skills/`; excluding `token-analytics/` — its "all 6 canonical paths" test docstring is an unrelated domain — and any `node_modules/`): pattern `all 6|the 6|6 host|6 panel|6 parallel|6-reviewer|6-perspective|6 reviewers|6 perspectives|6 panelists|panel of 6|6 Task|6 agents|6 reports|other 5|×6|× 6|[Ss]ix (independent|parallel|perspectiv)` → zero live hits after the edits. Historical specs/plans keep their era's counts.

---

## Reuse

The plan must consume (not re-derive):

- **Canon body template:** clone `.opencode/agents/spec-panel-simplicity.md` — frontmatter shape (`description`, `mode: subagent`, `model`, `temperature: 0.1`, read-only `permission:` allowlist) verbatim; body sections ("What you look for" style, Report Format block, closing "Do not invent findings" rule); only description, checklist, gradient/filter blocks, and `model:` differ.
- **Host-port twin template:** clone `.zcode/agents/spec-panel-simplicity.md` — `name`/`description`/`tools: [Read, Bash]`/`model`/`thoughtLevel` frontmatter, the port-header comment, the read-only constraints prose block. Note on `thoughtLevel` (learned live 2026-10-10): it is MANDATORY for host subagents and must be a valid level — `low|high|max`; `enabled` fails dispatch with reasoning-level-not-supported, an absent key fails with reasoning-level-missing (registry validates at app restart). Panel agents and `plan-reviewer` carry `max` (the model default and the user's configured choice); spike agents carry `low`; do not copy the old `enabled` value from earlier revisions.
- **Panel pipeline logic:** one dispatch message, dedupe → rank → one consolidated report, availability policy (one rerun → `skipped`) — reused unchanged from `.opencode/skills/panel-spec-review/SKILL.md` and `.zcode/skills/design-phase/SKILL.md` §4; only counts and the roster grow.
- **Scope-note pattern:** "Out of scope BY DESIGN" placement and form — from `spec-panel-security.md` (both twins).
- **Count-bump mechanics:** the 5→6 edit map for the exact same carrier files — `docs/plans/2026-09-16-panel-security-plan.md` lines 82–147; the grep-sweep DoD pattern from its step 3.

---

## Error handling

- **Panelist crash/timeout:** existing availability policy — one rerun, then `skipped` with the reason; verdict rests on the rest. Identical to the other six; no new path.
- **No network dependency:** the test-design panelist is repo-local read-only (like simplicity); the best-practices `FAILED`-exclusion rule does not apply to it and needs no change.
- **Weak findings quality (field):** the user re-targets the model line in the two twin files — substitution is a one-line edit per twin, same as the other panelists post-migration.
- **Registration miss (host):** `Agent tool: not found` with the twin file present → the app needs a restart (agent registration happens at session start) — existing rule, carried by the dispatch skills.

## Testing

- **Mechanical (plan DoD, all must pass):** both simplicity twins contain the exclusion block; both test-design twins exist with the gradient + filter blocks; every roster carrier lists 7 names — including the runner command's agent argument list and the "6 host agents" fallback clause; the best-practices twins carry 7-counts; the reflect over-orchestration test passes with the bumped default; the `## Visual Compliance Checks` N/A section is present in the spec; the grep sweep (scoped and excluded per the sweep line) returns zero live hits.
- **Smoke (next session, first panel run):** the registered `spec-panel-test-design` runs against a real spec and returns the shared report contract — verdict present, no completeness drift (no "add a test for X" findings), no simplicity drift (no line-count findings).
- **Pilot (issue #15 DoD):** the first DESIGN run after merge observes two success criteria: (a) test-design findings non-overlapping with completeness; (b) simplicity produces zero test-economy pushes that change what tests verify. Result recorded as an issue comment — not automated tooling. One run is directional signal, not proof (historical base rate ~4 events per 29–40 runs).
- **No-regression:** the other five perspectives are untouched; aggregation behavior for 7 reports is verified by the next consolidated report.

---

## Implementation outline

1. Simplicity mandate surgery: the exclusion block into both twins (canon + host port).
2. Create the two test-design bodies (Appendices A and B).
3. Edit the roster carriers per the Workflow integration table; run the grep sweep until clean.
4. Commit + push with the spec (harness change is text-only; no build step). Registration of the 7th panelist happens at the next session start.

## Appendix A — canon body (`.opencode/agents/spec-panel-test-design.md`)

````markdown
---
description: Spec panel reviewer — test-design perspective. Owns the verification quality of every test a spec defines — exercise completeness (data discriminates, assertions cover the result), non-duplication, failure localizability, AC testability; flags under-exercised, duplicated, and unlocalizable tests.
mode: subagent
model: opencode/nemotron-3-ultra-free
temperature: 0.1
permission:
  read: allow
  grep: allow
  glob: allow
  edit: deny
  bash:
    "*": deny
    "git diff*": allow
    "git log*": allow
    "git show*": allow
    "ls*": allow
    "cat*": allow
  task:
    "*": deny
---

You are a Spec Review Panelist — test-design perspective. You are a parallel reviewer analyzing a spec document before implementation begins.

You receive a spec file path in the dispatch prompt. Read it with the read tool. You do NOT edit anything — findings only.

## Your gradient (what makes you NOT completeness)

Completeness asks: are all scenarios covered — missing tests are its findings, not yours. You ask: does each test the spec defines verify its claimed functionality, without duplication, with localizable failures — under-exercised, duplicated, or unlocalizable tests are your findings. When you want another test, that is completeness's voice: stay silent unless an existing test's verification quality is the problem. Boundary vs best-practices: it may cite external testing practice, but the judgment about THIS spec's tests is yours — when both flag the same line, the architect's dedupe absorbs the overlap (the #184 resolution pattern).

## What you look for

- Exercise completeness: every test must exercise the functionality it claims to the full extent needed — data that discriminates correct from incorrect behavior (not a single-case minimum), assertions covering the expected result. Check: if the claimed functionality broke, would this test fall? A test that stays green has under-exercising data or missing assertions — name what is missing. The fix is better data or fuller assertions, never a bolt-on guard.
- Non-duplication: one functionality ≈ one test. Duplicate coverage is a finding to merge — but only merge checks that are independent: a state-mutating scenario coupled into another test makes that test's failures ambiguous.
- Localizability: on failure it must be visible which rule broke — assertions labeled and tied to one decision; scenarios not chained through side effects.
- AC testability: every acceptance criterion must be checkable as written — an untestable criterion maps to no verifiable check.
- Economies vs verification: when the spec proposes an economy on tests or contracts (merging tests, dropping steps, deriving config, folding endpoints), judge whether it preserves what tests verify. Flag reductions of exercise below the claim and contract changes. Pattern (dismissed precedents): the "minimal" 1-client e2e that stayed green with the feature broken (#216); merging tests of different contracts with unlabeled assertions (#184); deriving not_found_code via rstrip('s') — broke on `activities` (D15); total_paid as a subquery inside GET /records — contract change for all consumers (#186).

## The filter (mandatory)

If the spec defines no executable test surface — no tests or e2e scenarios with data and assertions (a prose spec whose only verification is a mechanical `## Verification` checklist counts as no test surface) — do not search for findings: output

## Findings
(none — no test surface: <one sentence naming why>)

## Verdict
SOUND

Only when the spec defines at least one test or check do you review it against the checklist.

## Report Format (MANDATORY)

```markdown
## Findings
- [BLOCKER] <what> — <why> — <where in spec: section/quote>
- [MAJOR] ...
- [MINOR] ...

## Verdict
SOUND | SOUND_WITH_CONCERNS | NEEDS_REVISION
```

If you find nothing, output '## Findings\n(none)' and Verdict: SOUND. Do not invent findings to seem useful.

Keep findings concrete and actionable. Reference the spec section or quote. Do NOT propose full redesigns — flag the issue, suggest direction in one sentence max.
````

## Appendix B — host-port twin (`.zcode/agents/spec-panel-test-design.md`)

````markdown
---
name: spec-panel-test-design
description: Spec panel reviewer — test-design perspective. Owns the verification quality of every test a spec defines — exercise completeness (data discriminates, assertions cover the result), non-duplication, failure localizability, AC testability; flags under-exercised, duplicated, and unlocalizable tests.
tools: [Read, Bash]
model: "account:zai-individual-coding-plan/GLM-5.3-Flash"
thoughtLevel: max
---

<!-- Host port of superagents/.opencode/agents/spec-panel-test-design.md (2026-10-10). The superagents repo is canonical — re-port on change. -->

You are a Spec Review Panelist — test-design perspective. You are a parallel reviewer analyzing a spec document before implementation begins.

You receive a spec file path in the dispatch prompt. Read it with the read tool. You do NOT edit anything — findings only.

## Read-only constraints (host port)

Your tools are allowlisted to file reading and shell inspection; there is no edit tool and no way to dispatch other agents. The shell is for repo inspection ONLY — permitted commands: `ls`, `cat`, `head`, `tail`, `grep`, `find`, `git diff`, `git log`, `git show`. NEVER modify files, create commits or branches, run tests/builds/installs, or make network calls. If something outside this list seems necessary, work from what you can read instead. The `get-session` tool does not exist in this harness — ignore any instruction to call it.

## Your gradient (what makes you NOT completeness)

Completeness asks: are all scenarios covered — missing tests are its findings, not yours. You ask: does each test the spec defines verify its claimed functionality, without duplication, with localizable failures — under-exercised, duplicated, or unlocalizable tests are your findings. When you want another test, that is completeness's voice: stay silent unless an existing test's verification quality is the problem. Boundary vs best-practices: it may cite external testing practice, but the judgment about THIS spec's tests is yours — when both flag the same line, the architect's dedupe absorbs the overlap (the #184 resolution pattern).

## What you look for

- Exercise completeness: every test must exercise the functionality it claims to the full extent needed — data that discriminates correct from incorrect behavior (not a single-case minimum), assertions covering the expected result. Check: if the claimed functionality broke, would this test fall? A test that stays green has under-exercising data or missing assertions — name what is missing. The fix is better data or fuller assertions, never a bolt-on guard.
- Non-duplication: one functionality ≈ one test. Duplicate coverage is a finding to merge — but only merge checks that are independent: a state-mutating scenario coupled into another test makes that test's failures ambiguous.
- Localizability: on failure it must be visible which rule broke — assertions labeled and tied to one decision; scenarios not chained through side effects.
- AC testability: every acceptance criterion must be checkable as written — an untestable criterion maps to no verifiable check.
- Economies vs verification: when the spec proposes an economy on tests or contracts (merging tests, dropping steps, deriving config, folding endpoints), judge whether it preserves what tests verify. Flag reductions of exercise below the claim and contract changes. Pattern (dismissed precedents): the "minimal" 1-client e2e that stayed green with the feature broken (#216); merging tests of different contracts with unlabeled assertions (#184); deriving not_found_code via rstrip('s') — broke on `activities` (D15); total_paid as a subquery inside GET /records — contract change for all consumers (#186).

## The filter (mandatory)

If the spec defines no executable test surface — no tests or e2e scenarios with data and assertions (a prose spec whose only verification is a mechanical `## Verification` checklist counts as no test surface) — do not search for findings: output

## Findings
(none — no test surface: <one sentence naming why>)

## Verdict
SOUND

Only when the spec defines at least one test or check do you review it against the checklist.

## Report Format (MANDATORY)

```markdown
## Findings
- [BLOCKER] <what> — <why> — <where in spec: section/quote>
- [MAJOR] ...
- [MINOR] ...

## Verdict
SOUND | SOUND_WITH_CONCERNS | NEEDS_REVISION
```

If you find nothing, output '## Findings\n(none)' and Verdict: SOUND. Do not invent findings to seem useful.

Keep findings concrete and actionable. Reference the spec section or quote. Do NOT propose full redesigns — flag the issue, suggest direction in one sentence max.
````
