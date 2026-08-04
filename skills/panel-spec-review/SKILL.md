---
name: panel-spec-review
description: Use when dispatching spec-review-* panel agents during DESIGN phase spec review. Covers dispatch protocol, agent roles, and aggregation rules.
---

# Panel Spec Review

## When to load

Architect loads this skill on DESIGN phase before dispatching
spec-review-* panel agents. Not needed on IMPL phase.

## Dispatch Protocol

1. **Spec must be self-contained BEFORE panel review.** If issue scope
   must be checked against the spec — architect does this themselves and
   incorporates findings INTO the spec during DESIGN. The spec is what
   panel agents review; they do not cross-reference GitHub issues.

2. **Give each panel agent:** spec file path (+ prior spec path if exists).
   No `gh issue view`, no `webfetch`, no direct network/bash beyond
   read-only git/cat/ls.

3. **If issue scope check is needed** — architect does it themselves
   during DESIGN phase, incorporates into spec. Do NOT delegate this
   to panel agents.

4. **Exception: best-practices agent** dispatches `researcher-agent`
   for web research — this is its designed workflow. All other panel
   agents are strictly repo-local read-only.

## Panel Agent Roles

| Agent | Perspective | Access |
|-------|------------|--------|
| `spec-review-completeness` | Holes, edge cases, missing scenarios | read/grep/glob/git-read |
| `spec-review-consistency` | Contradictions, conflicts with code/domain rules | read/grep/glob/git-read |
| `spec-review-feasibility` | Technical risks, hidden complexity | read/grep/glob/git-read |
| `spec-review-simplicity` | Overengineering, unrequested scope, YAGNI | read/grep/glob/git-read |
| `spec-review-best-practices` | Current best practices via web research | same + `task: researcher-agent` |

All 5 are read-only leaf agents. They do NOT edit, do NOT run `gh`,
do NOT access the network directly (except best-practices via researcher-agent).

## Aggregation

After all 5 return:

1. Collect findings from all reports.
2. Dedup overlapping findings (same issue flagged by multiple agents).
3. Rank: BLOCKER > MAJOR > MINOR.
4. Present consolidated report to user for revision decision.
5. If any agent returned `FAILED` (best-practices without research) —
   note it in the report and exclude from verdict.