# Panel Test-Design Reviewer (7th Panelist) + Simplicity Mandate Surgery — Implementation Report

**Date:** 2026-10-11
**Issue:** superagents #15
**Spec:** `docs/specs/2026-10-08-panel-test-design-design.md` (v3, gate B OK 2026-10-10)
**Plan:** `docs/plans/2026-10-10-panel-test-design-plan.md` (8 tasks)
**Branch:** `panel-test-design` — 9 commits `35e56e6..a49ff3d` on top of origin/main `2787354`

## What landed

Two-part change per the spec: (1) the simplicity panelist's mandate is surgically narrowed — economies that change what a test verifies move out of scope BY DESIGN (the four memo precedents cited in-body); (2) a new always-on 7th panelist `spec-panel-test-design` (canon + host-port twin) owns verification quality of spec-defined tests. The panel grows 6→7 across every roster carrier, and the reflect over-orchestration default `max_subagents` 6→8 makes a 7-panelist dispatch the designed norm.

## Tasks

| # | Task | Class | Commit | Status |
|---|---|---|---|---|
| 1 | Simplicity mandate surgery — both twins | trivial | `35e56e6` | done |
| 2 | Test-design agent twins (spec Appendices A/B) | trivial | `7d6cdc0` | done |
| 3 | `panel-spec-review` roster 6→7 + gradient note | small | `40a4cd5` | done |
| 4 | Architect dispatch/permission/skip 6→7 | small | `071f6c2` | done |
| 5 | Host skills design-phase + auto-design 6→7 | small | `fa2f74d` | done |
| 6 | Best-practices prose counts 5/6→6/7 | trivial | `41f181f` | done |
| 7 | Reflect `max_subagents` 6→8 + tests | small | `e51cf3f` | done |
| 8 | Docs carriers + spec status + sweep | standard | `0fadc33` | done |
| — | Follow-up: availability-policy attribution | — | `a49ff3d` | done |

Diff: 18 files, +151/−22.

## DoD status (plan DoD, §202)

| # | Criterion | Status |
|---|---|---|
| 1 | Exclusion block in both simplicity twins; both test-design twins with gradient (incl. best-practices boundary), executable-test-surface filter, fenced Report Format; host twin `thoughtLevel: max` | ✓ |
| 2 | Every roster carrier lists 7 — runner args, host fallback, architect allowlist/dispatch/skip, best-practices counts | ✓ |
| 3 | Reflect `max_subagents` 8 in all three sites (default, fallback, example config); over-orchestration tests pass | ✓ |
| 4 | Scoped grep sweep: zero unjustified panel hits (2 remaining hits are correct post-change counts) | ✓ |
| 5 | Spec Status = gate B OK | ✓ |

## Tests

- `.opencode/skills/reflect/tests/test_workflow_checks.py`: **31/31 passed** (incl. the 2 over-orchestration tests updated for the 6→8 ceiling).
- Repo `tests/` suite: **198/200** — the 2 failures are pre-existing and environment-caused (container host-label file present; tests assume absent). The identical pair fails at baseline `2787354` before any change in this diff.

## Notes

- Push happens via the PR finishing flow; the worktree protocol supersedes the plan's `git push origin main` step (Task 8).
- Field verification pending by design (plan §Verification status): smoke = first panel run of the next session (7th verdict present); pilot = first DESIGN cycle after merge, recorded as an issue #15 comment.
- Visual compliance: N/A per spec (no UI).
