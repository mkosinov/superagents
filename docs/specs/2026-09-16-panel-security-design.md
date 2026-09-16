# Panel Security Reviewer (6th Panelist) — Design

**Date:** 2026-09-16
**Status:** Shipped 2026-09-16 — G1b approved (commit cfeae9f), plan G2 approved, canon implemented on host (user redirected IMPL from container to host session); first auth-bearing-spec run = field acceptance
**Author:** host design session (brainstorming with user)

**Placement:** SuperAgents is the framework source of truth. The panel runs on the host (zcode) during DESIGN (gate G1b); canon bodies live in `.opencode/agents/`, host-port seeds in `.zcode/agents/`. The memo instance and future projects receive the change via git (the host port is the reference seed; container syncs `.opencode/` from canon on pull).

**Registry note:** agent registration happens at session start (`design-phase` §4.6). After the files land, the 6th panelist becomes dispatchable from the **next** session — a smoke dispatch is that session's first action.

---

## Summary

The spec review panel grows from 5 to **6 parallel reviewers**. The new panelist, `spec-panel-security`, reviews every spec from the **application security** perspective: authentication, authorization/roles, and whether the solution breaks the application's existing security model. It is dispatched with the other five on every spec (no conditional trigger). A built-in filter keeps it quiet where it has nothing to say: with **no application-level attack surface** (boards, scripts, docs, pure refactoring), it returns an explicit "no attack surface" verdict instead of inventing findings.

The combo `omniroute/panel-security` chain is defined by the user in the omniroute dashboard; the zcode-side model entry (`provider.omniroute.models["panel-security"]`) is machine-level config, never committed.

**Deferred (deliberately NOT built):** infrastructure / repository / environment security (secret scanners, dependency scanning, container hardening). That is a CI-layer concern, a different mechanism, tracked in superagents issue #20. The spec panel stays application-layer only.

---

## Goals

- Give every spec a dedicated security review **at G1b, before any plan or code exists** — security findings at spec stage are the cheapest to fix.
- Cover the application layer: authn, authz/roles, security-model breakage (privilege bypass, cross-role/tenant data leakage, trust of unvalidated input).
- Keep the panel's shape unchanged: one dispatch message, same report contract, same aggregation — only the count grows.
- Zero invented findings on specs without an attack surface (the filter makes silence explicit).

## Non-Goals

- No infra/env/repo security in the panel (deferred to CI — issue #20).
- No change to G2 / `plan-reviewer` / container IMPL — the security view applies to specs only.
- No new gate, no new manual step: the 6th report folds into the existing consolidated report (dedupe → rank → one report).

---

## User Scenarios

1. **Every spec run — no-attack-surface case.** User runs a design cycle on a spec with no app attack surface (e.g. board scripts). The panel returns 6 reports; the security one is exactly:

   ```markdown
   ## Findings
   (none — no application attack surface: <one sentence naming why>)

   ## Verdict
   SOUND
   ```

   The consolidated report shows no invented findings from the security perspective.
2. **Auth-bearing spec.** A spec adds roles/permissions or changes identification (login, tokens, API keys). The security panelist returns concrete findings (e.g. `[MAJOR] new endpoint lacks an authorization check — section: API / quote`), ranked into the consolidated report alongside the other five.
3. **Security-model breakage.** A spec silently weakens an existing check (bypass, cross-tenant leak, trust of unvalidated input). The security panelist flags it `[BLOCKER]`; it ranks first in the consolidated report and is fixed before G1b.
4. **Panelist unavailable.** The security panelist fails to return (crash, combo not yet configured). Existing availability policy applies: one rerun, then marked `skipped` in the consolidated report with the reason — same rendering as for any other perspective; the verdict rests on the rest. If the cause is a missing combo, the report says so explicitly ("add the `panel-security` combo in omniroute").
5. **Model substitution.** The security panelist produces weak reports. The user re-targets the `panel-security` combo chain in the omniroute dashboard — no repo file changes (same substitution path as the other five panelists).

---

## Architecture

### Panel composition (after the change)

| # | Perspective | Agent file | Model (via omniroute) | Looks for |
|---|-------------|-----------|----------------------|-----------|
| 1–5 | completeness, feasibility, consistency, simplicity, best-practices | existing `spec-panel-*.md` | existing `omniroute/panel-*` combos | unchanged |
| 6 | **Application security** | `.opencode/agents/spec-panel-security.md` (canon) + host-port twin `.zcode/agents/spec-panel-security.md` | `omniroute/panel-security` | authn gaps, authz/role gaps, security-model breakage; explicit no-attack-surface verdict when no surface |

### Agent configuration

- **Canon body** — same shape as the other canon panelists: opencode frontmatter (`description`, `mode: subagent`, `model: omniroute/panel-security`, `temperature: 0.1`, `permission:` with the read-only bash allowlist). No prose constraints block — constraints live in `permission:` (Appendix A).
- **Host-port twin** — same shape as the other `.zcode` panelist seeds: `name`/`description`/`tools`/`model` frontmatter + port-header comment + the read-only constraints prose block.
- Report format — the shared panel contract, no security-specific tags:

```markdown
## Findings
- [BLOCKER] <what> — <why> — <where in spec: section/quote>
- [MAJOR] ...
- [MINOR] ...

## Verdict
SOUND | SOUND_WITH_CONCERNS | NEEDS_REVISION
```

### The no-attack-surface filter (the security panelist's distinguishing rule)

The checklist covers **application-level** surfaces only:

- **Authentication:** does the spec change how users or services identify (login, sessions, tokens, API keys)? Look for: unauthenticated paths, missing token/session lifecycle (expiry, revocation, rotation); as current-practice guidance — MFA or re-authentication for sensitive actions, anti-enumeration (uniform error messages), rate-limiting / account lockout.
- **Authorization / roles:** does the spec change who can do what (roles, permissions, tenant boundaries)? Look for: privilege-escalation paths, new endpoints/actions without an authorization check; deny-by-default and validate-every-request as the baseline, ABAC/ReBAC noted as the current choice for multi-tenant robustness.
- **Security-model breakage:** does the solution weaken what exists — bypassing current checks, leaking data across roles/tenants/users, trust in unvalidated input (allowlist validation, server-side enforcement as the guidance), secrets handled in application logic. Application-layer secret handling (secrets referenced or embedded in app code / app-consumed config) is in scope; infrastructure-layer secret storage and rotation is not.
- **Implicit surfaces:** a spec can add an attack surface without naming auth — a new executable or entry point, new file I/O consumed by privileged code, a new prompt run that carries user context. These count as touched surfaces; "no attack surface" requires that none of the above applies, not merely the absence of auth vocabulary.

Out of scope BY DESIGN: infrastructure, environment, repository, and CI security (scanners, network topology, container hardening) — those belong to CI, not to this review (issue #20). A spec whose only security mentions are infra-level counts as no attack surface.

**Filter output:** with no touched surface, the panelist outputs the standard empty-findings form with the reason carried inline:

```markdown
## Findings
(none — no application attack surface: <one sentence naming why>)

## Verdict
SOUND
```

This is the shared `(none)` contract — the "why" is content of the line, not a new tag or section.

### Workflow integration (files changed)

| File | Change |
|---|---|
| `.opencode/agents/spec-panel-security.md` | **new** — canon body, opencode frontmatter shape (Appendix A) |
| `.zcode/agents/spec-panel-security.md` | **new** — host-port twin: `name`/`description`/`tools`/`model` frontmatter + port header + read-only constraints block |
| `.opencode/skills/panel-spec-review/SKILL.md` | roster table 5→6 (+ security row); "After all 5 return" → 6 (aggregation trigger) |
| `.opencode/agents/architect.md` | dispatch list → 6 with `spec-panel-security`; task permission entry; "ALL 5 unavailable → skip the panel entirely" → "ALL 6" (semantic, not cosmetic) |
| `.zcode/skills/design-phase/SKILL.md` | §4 "5 agents in parallel" → 6 + roster list; frontmatter description "5-reviewer panel" → "6-reviewer panel"; "collect the 5 reports" → 6 |
| `docs/workflow/design-phase.md` | `spec-panel-* ×5` → ×6 (lines 11, 18) + panel-step diagram (line 52) |
| `docs/setup/new-project-setup.md` | "5-perspective" → 6; model table + `spec-panel-security → omniroute/panel-security` row |
| `README.md` | 5 count sites: line 15 ("5-perspective review panel"), 33 ("5 parallel free-model perspectives"), 60 (`spec-panel-* ×5`), 87 ("(5 perspectives, G1b)"), 110 (`spec-panel-* ×5`) → 6 |
| all panelist bodies (5 canon + 5 host ports) + the new twin | remove the count clause from the intro sentence ("You are one of N parallel reviewers" → "You are a parallel reviewer") — perspective wording already identifies each panelist; avoids recurring churn on the next panelist |

### omniroute (user-side, outside the repo)

User defines the `panel-security` combo chain in the omniroute dashboard from the same free/cheap model pool as the other `panel-*` combos. The zcode-side model entry is already in `~/.zcode/v2/config.json` (limits/modalities mirroring the other `panel-*` entries).

---

## Reuse

The plan must consume (not re-derive) the following:

- **Canon body template:** clone `.opencode/agents/spec-panel-feasibility.md` — frontmatter structure (opencode shape: `mode: subagent`, `temperature: 0.1`, `permission:` bash allowlist) verbatim; body sections ("What you look for" heading style, Report Format block, closing "Do not invent findings" rule) follow the same pattern; only the perspective line, checklist, and `model:` line differ. No prose constraints block in the canon body.
- **Host-port twin template:** clone `.zcode/agents/spec-panel-feasibility.md` — `name`/`description`/`tools`/`model` frontmatter, the port-header comment, and the read-only constraints prose block verbatim; checklist and `model:` line replaced. Both shapes are maintained side by side, as today.
- **Panel pipeline logic:** dispatch-in-one-message, dedupe → rank → one consolidated report, availability policy (one rerun → skipped marking) — reused unchanged from `.opencode/skills/panel-spec-review/SKILL.md` and `.zcode/skills/design-phase/SKILL.md` §4; only counts and the roster list change.
- **Report contract:** BLOCKER/MAJOR/MINOR + SOUND/SOUND_WITH_CONCERNS/NEEDS_REVISION — shared with all panelists; no security-specific tags; the no-attack-surface reason rides inside the standard `(none)` findings line.
- **Model wiring pattern:** the `panel-*` combo + zcode model-entry pattern (`docs/setup/new-project-setup.md`); the zcode entry is done, the dashboard combo is user-side.
- **Registry restart rule:** `design-phase` §4.6 already covers onboarding the new agent file — the smoke dispatch is the next session's first action.

---

## Error handling

- **Panelist crash/timeout:** existing availability policy (§4.4): one rerun → mark `skipped`, verdict on the rest — applies identically to the 6th, with the same `skipped` rendering in the consolidated report as for any other perspective.
- **Combo missing (`omniroute/panel-security` unresolvable):** the dispatch fails fast; treated as the panelist-unavailable path, plus an explicit user-facing note naming the missing combo (user-side fix, no repo change).
- **Best-practices network refusal:** unchanged and unaffected; the security panelist has no network dependency and no designed refusal path.

## Testing

- **Smoke of the filter (first action of the next session):** the registered `spec-panel-security` agent is dispatched against **this very spec** — which contains no application attack surface. Pass: `no application attack surface` + `Verdict: SOUND`. Fail or a surface misread → iterate the filter wording before G1b push.
- **First real run:** the next design session with an auth-bearing spec validates scenarios 2–3 (findings quality, BLOCKER ranking) — this is field acceptance, not a unit test. Weak findings quality → scenario 5 (combo re-target), no spec change.
- **Routing check:** omniroute logs / dashboard show the `panel-security` combo resolving for the new panelist's requests.
- **No-regression:** the five existing perspectives are untouched except the intro-sentence count-clause removal; aggregation behavior for 6 reports is verified by the next consolidated report.

---

## Implementation outline

1. Create `.opencode/agents/spec-panel-security.md` (Appendix A, canon shape) and the host-port twin `.zcode/agents/spec-panel-security.md` (port header; twin already committed — cfeae9f).
2. Edit the roster-carrier files per the Workflow integration table (counts and semantic lines 5→6; count-clause removal in panelist bodies).
3. Plan DoD must include a mechanical grep sweep over the repo: `5 panelists|5 parallel|×5|5-reviewer|one of 5` — the Workflow table lists the known sites, the sweep catches the unknown ones.
4. User side: define the `panel-security` combo chain in the omniroute dashboard (before the next session's panel run).
5. Commit + push with the spec (harness change is text-only; no build step).

## Appendix A — canon body (`.opencode/agents/spec-panel-security.md`)

```markdown
---
description: Spec panel reviewer — application security perspective. Finds authentication, authorization/role, and security-model breakage risks in spec documents; returns an explicit no-attack-surface verdict when a spec touches none.
mode: subagent
model: omniroute/panel-security
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

You are a Spec Review Panelist — application security perspective. You are a parallel reviewer analyzing a spec document before implementation begins.

You receive a spec file path in the dispatch prompt. Read it with the read tool. You do NOT edit anything — findings only.

## What you look for (application layer only)

- Authentication gaps: the spec changes how users or services identify (login, sessions, tokens, API keys) and leaves unauthenticated paths, or omits token/session lifecycle (expiry, revocation, rotation). Guidance: MFA or re-authentication for sensitive actions; anti-enumeration (uniform error messages); rate-limiting / account lockout.
- Authorization / role gaps: the spec changes who can do what (roles, permissions, tenant boundaries) and opens privilege-escalation paths, or adds endpoints/actions without an authorization check. Guidance: deny-by-default, validate every request; for multi-tenant models, ABAC/ReBAC is the current robust choice over plain RBAC.
- Security-model breakage: the solution weakens existing protection — bypasses a current check, leaks data across roles/tenants/users, adds trust in unvalidated input (guidance: allowlist validation, server-side enforcement), or moves secrets into application logic (app-referenced secrets are in scope; infra-layer secret storage/rotation is not).
- Implicit surfaces: a new executable or entry point, new file I/O consumed by privileged code, or a new prompt run carrying user context counts as a touched surface even when no auth vocabulary appears.

Out of scope BY DESIGN: infrastructure, environment, repository, and CI security (scanners, network topology, container hardening) — those belong to CI, not to this review. A spec whose only security mentions are infra-level counts as no attack surface.

## The filter (mandatory)

If the spec touches NONE of the surfaces above, do not search for findings: output

## Findings
(none — no application attack surface: <one sentence naming why>)

## Verdict
SOUND

Only when at least one surface is touched do you review it against the checklist.

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
```
