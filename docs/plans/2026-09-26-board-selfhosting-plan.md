# Board Self-Hosting Implementation Plan (issue #23)

**Spec:** `docs/specs/2026-09-26-board-selfhosting-design.md` (G1a + G1b approved, panel fixes folded)
**Date:** 2026-09-26
**Port source:** memo clone — container path `/root/workspace/memo`, host path `~/dev/memo`, pinned at commit `20b710f7` (all spec anchors reference that state). **Port strictly from the pinned ref** (e.g. `git -C /root/workspace/memo show 20b710f7:.zcode/scripts/gh_board.py`), never from HEAD: memo has already moved past the pin with functionality drift in exactly the ported commands (`host` set/clear signature, `reconcile` marker persistence, `pick-next` foreign-host skip) that the spec does not cover. Re-anchoring to a newer memo commit is a spec change, not an implementation liberty.

## Goal

Port memo's evolved board stack into superagents exactly as specified: the full `gh_board.py` (Next Up stripped, config-driven, priority ordering added), the three skills, the container watcher template, zero-network CI, and the old-model text sync (workflow docs, container agent bodies, setup doc) — so this repo runs the board automation it ships as canon and the #24 transitional drift is closed.

## Architecture

```
docs/board/board_config.json (v1)          ← written by #24's board_bootstrap adopt
        ↓ read
.zcode/scripts/gh_board.py  ═══ byte-identical twins ═══  .opencode/scripts/gh_board.py
        ↓ token protocol (NONE | <number>)
.opencode/scripts/auto_impl_watch.sh (container loop)   +   .zcode/skills/auto-design (2h ZCode card)
        ↓ consumed by
skills: github-board (twins), design-phase, auto-design   +   agent bodies + workflow docs (synced)
        ↓ guarded by
.github/workflows/gh-board.yml + tests/test_gh_board.py  (zero network, subprocess.run mock seam)
```

Identity (project id, owner, repo, field ids, host budgets) lives ONLY in the config; the script text is repo-independent. All board writes go through the script (single writer per field value; board_bootstrap is the rollout-time writer per #24).

## Tech Stack

Python 3 stdlib only (subprocess, json, pathlib, datetime) — no new dependencies; `gh` CLI for all GitHub access; bash for the watcher; GitHub Actions (ubuntu-latest, zero secrets, explicit least-privilege `permissions:`); test runner = stdlib `unittest` (matches #24's `tests/test_board_bootstrap.py`, no pytest dependency).

## Behavioral Delta

- The container manager asking "what to implement" gets a priority-ordered (Critical > High > Medium > Low, oldest-issue tiebreak), host-budget-honoring answer from `pick-next` — instead of reading a deleted queue field.
- A scheduled design session gets `pick-next-design` with the one-at-a-time design-slot invariant and priority ordering over `Backlog`.
- Gate stops are visible board state (`gate` field: concept/spec/plan/blocked), set/cleared by `gate N <v>|none`, auto-maintained by `status` transitions (host stamp on entering In Design/In IMPL; host+gate cleared on leaving; gate-only cleared entering PR (G7)).
- The same script file works in any bootstrapped repo unchanged.
- CI catches regressions in all of the above with zero network and zero secrets, and mechanically enforces twins byte-identity.
- Container agent texts and workflow docs speak only the current model — no dead `next-up`/`shift` instructions, no gate-suffixed statuses.
- Fast-track is usable only for docs/prose diffs.

---

## Task 0: Precondition gate — #24 must be shipped

### Classification: trivial

Verify BEFORE any other task: origin/main contains #24's artifacts (`docs/board/board-etalon.md`, `.zcode/scripts/board_bootstrap.py` + `.opencode` twin, `tests/test_board_bootstrap.py`, `.github/workflows/board-bootstrap.yml`). `docs/board/board_config.json` may be in EITHER state: absent (this issue's Task 7 generates it) or already committed by #24's own close-out acceptance — in the latter case verify it maps project #4 (`project_number: 4`, repo `superagents`); both states allow work to start. If #24 is not shipped — stop and report; the spec's dependency («IMPL of #23 starts strictly after #24's IMPL ships») is blocking.

### Required Docs
- Spec §Dependencies and ordering; #24 spec `docs/specs/2026-09-21-board-bootstrap-design.md` §Dependencies.

### DoD
- Precondition verified and stated in the session report; work did not start otherwise.

---

## Task 1: Port gh_board.py — skeleton, config identity, pick commands

### Classification: large

Copy memo's `/root/workspace/memo/.zcode/scripts/gh_board.py` (800 lines @ 20b710f7) into BOTH twins, then apply the spec's deltas:

1. **Strip Next Up everywhere**: `cmd_next_up` / `cmd_set_next_up` / `cmd_shift` functions + dispatch entries + `NEXT_UP_FIELD` / `NEXT_UP_OPTS` constants + the `next_up` key in items parsing + Next Up columns in `show` output + docstring mentions (spec Goal 1: removed everywhere).
2. **Config-driven identity**: replace `PROJECT_ID` / `OWNER` / `REPO` / `PROJECT_NUM` / field-id lookups / `HOST_BUDGETS` with a config loader for `docs/board/board_config.json` v1 (repo root = `Path(__file__).resolve().parents[2]`). Loader rules per spec §gh_board.py: missing file → clean exit with the `adopt` hint; wrong `version` → clean exit naming v1; garbage JSON → clean exit with the parse error; missing required key (`version, project_id, project_number, owner, repo, fields, host_budgets`) → clean exit naming the key; value format checks (owner/repo charset, `PVT…`/`PVTSSF…` node-id patterns). Lazy load: no network before validation.
3. **Priority ordering** (new code): in `pick-next` and `pick-next-design`, replace the Next Up sort with key `(priority rank, issue number)` ascending — rank Critical=0, High=1, Medium=2, Low=3, unset=4; priority read from the card's `Priority` field value; priority never overrides status-prefix eligibility (spec §Concepts).
4. **Drop the legacy freshness path**: `_recent_markers` standalone `auto-impl claim:` / `auto-impl blocked:` comment scanning is removed (spec: can never fire here, widens spoof surface). Keep auto-log-based freshness.
5. **Canonical log pinning**: `auto-log` pins the canonical comment id at creation; `_auto_impl_log` prefers the pinned id and ignores later prefix-matches from other authors.
6. Keep everything else verbatim (spec §gh_board.py "Unchanged" list): container paths, policy constants, `find_item` auto-add, `gql()` transport, `resolve()`-based root.
7. Twins must be byte-identical (single source, copied).
8. Create `tests/test_gh_board.py` (stdlib `unittest`, same runner as #24's tests) — Tasks 2–3 extend it; the subprocess-mock harness lands here with the first tests.

Consume spec Reuse: memo `:265–348` (pick commands), `:364–397` (log), config contract from #24 spec §board_config.

### Required Docs
- Spec §gh_board.py (command table, loading rules, unchanged list); §Concepts (Priority selection, Trust model, Claim log); #24 spec (config v1 keys).

### DoD
- Automated test for scenario 1 passes (RED-GREEN-REFACTOR): mocked board, mixed priorities, budget pressure → correct number / NONE.
- Automated test for scenario 2 passes: design-slot busy → `NONE (design slot busy: …)`; Backlog candidates priority-ordered.
- Automated test for scenario 6 passes: temp-fixture repo root with a v1 config loads identity; without config → exact adopt hint; each malformed-config case exits cleanly with the specified message.
- Unit: TTL-boundary freshness skip holds; canonical-comment pinning holds (a later prefix-matching comment from another author is ignored).
- Twins byte-identical (`cmp`/sha).

---

## Task 2: Port the bookkeeping commands — status/gate/host/auto-log/auto-state/reconcile/merged/show/issue

### Classification: standard

Port from memo (anchors in spec table): `status` with the auto-stamp matrix (enter In Design/In IMPL → stamp host; leave → clear host AND gate; enter `PR (G7)` → clear gate, keep host — incl. the third-arg host form `status N "In Design" <host>`), `gate N concept|spec|plan|blocked|none` (values validated against live field options; `none` clears via `clearProjectV2ItemFieldValue`), `host N`, `auto-state`, `reconcile [host] [--dry-run]` (dry-run prints, never mutates; idle threshold `SESSION_IDLE_LIMIT_S`), `merged N PR [title]` (scratchpad append, MERGED_MAX=5, idempotent; container-side only), `show N|all` (Next Up column gone), `issue N`.

Consume spec Reuse: memo `:638–673` (status), `:675–690` (gate), `:489–585` (reconcile), `:716–775` (merged).

### Required Docs
- Spec §gh_board.py table; §Concepts (Gates A/B/C and the gate field; Host ownership and budgets — budget counts In IMPL only).

### DoD
- Automated test for scenario 3 passes: `gate` set/clear round-trip against the mocked transport.
- Automated test for scenario 4 passes: full stamping matrix incl. the PR exception.
- Automated test for scenario 5 passes: `reconcile --dry-run` prints the plan and the mock records zero mutations.
- Unit: auto-log merge keeps lines for non-overlapping cycles; merged formatting/trim/idempotence.

---

## Task 3: CI — workflow, mock guard, cross-cutting tests

### Classification: standard

Create `.github/workflows/gh-board.yml` (push + pull_request with paths filter over the script twins, `tests/test_gh_board.py`, the github-board skill twins, `auto_impl_watch.sh`, and the workflow itself — every file its tests guard must be in the filter; zero secrets; explicit least-privilege `permissions:`; pattern per #24's `board-bootstrap.yml`, NOT `site.yml`). Extend `tests/test_gh_board.py` with the cross-cutting targets: session-wide guard fixture that fails any test reaching a real `subprocess.run` call not backed by the mock; twins byte-identity test (script twins AND github-board skill twins, sha comparison); `bash -n` over `auto_impl_watch.sh`; field-list pagination explicitness (or loud overflow exit) in the live-options read.

Consume spec Reuse: `site.yml` paths-filter syntax; #24 workflow posture; `gql()`/`subprocess.run` seam (memo :73).

### Required Docs
- Spec §CI; #24 spec §CI.

### DoD
- CI green on the PR; zero network asserted (guard fixture demonstrably fails an intentionally unmocked call in a scratch check, then removed).
- All scenario tests from Tasks 1–2 run in this workflow.

---

## Task 4: Skills — github-board twins, design-phase, auto-design

### Classification: standard

1. `github-board`: rewrite both twins byte-identical from memo's `.zcode` seed, Next Up stripped, configure-constants guidance rewritten for the config era, **merged with #24's additions** — the single-writer exception line («board_bootstrap.py is the rollout-time board writer») must survive; content model per spec §Skills (status flow, gate semantics, budgets count In IMPL, pick token protocol, fast-track docs-only rule, mutation rules).
2. `design-phase` (`.zcode` only): port memo's seed — A/B/C gates, gate-field read-check-repair, fast-track exception, triggers; strip Next Up references.
3. `auto-design` (new, `.zcode` only): port memo's seed — 2h one-cycle protocol; strip hardcoded host `imac` (host comes from arg/`GH_BOARD_HOST` — the automation card supplies it); strip Next Up ordering notes.
4. English bodies; Russian only as functional literals.

Consume spec Reuse: memo skill seeds (`.zcode/skills/{github-board,design-phase,auto-design}/SKILL.md`); #24 plan Task 6 (the exception line's exact wording).

### Required Docs
- Spec §Skills; harness-language convention (English bodies).

### DoD
- `grep -rniE "next.?up|set-next-up|shift" .zcode/skills/github-board .zcode/skills/design-phase .zcode/skills/auto-design .opencode/skills/github-board` returns no queue semantics (the three rewritten skills + twins; the finishing skill is Task 6's).
- Twins byte-identical (CI test from Task 3 covers).
- No gate-suffixed statuses (`In Design (G1a)` etc.) anywhere in the three skills.

---

## Task 5: auto_impl_watch.sh — container template

### Classification: small

Port memo's `/root/workspace/memo/.opencode/scripts/auto_impl_watch.sh` to `.opencode/scripts/` with the spec's parameterization: working dir `/root/workspace/superagents`; owner/repo `mkosinov/superagents` in the HANDOFF text; pid-lock path per repo (`/tmp/auto-impl-watch-superagents.lock` — memo's watcher shares the container); HANDOFF content-adapted: drop the «сдвиг очереди» finishing tail (removed `shift` command), route blocker logging through `gh_board.py auto-log` instead of raw `gh api -X PATCH` instructions. Keep: loop interval, enable-file gate, freeze knob, reconcile→pick-next→claim→tiebreak→attach flow, container property paths.

### Required Docs
- Spec §auto_impl_watch.sh; §Concepts (Trust model — HANDOFF references repo-committed docs, not free issue text).

### DoD
- `bash -n` clean (CI test from Task 3).
- HANDOFF text contains no instruction to run `shift`/`next-up` and no raw comment-PATCH instruction.

---

## Task 6: Old-model text sync — workflow docs, agent bodies, setup doc

### Classification: standard

1. `docs/workflow/design-phase.md` + `docs/workflow/impl-phase.md`: merged statuses, gate field + A/B/C, host budgets, no Next Up.
2. `.opencode/agents/manager.md`: remove `next-up` / `set-next-up` / `shift` instructions (today at :98, :220–221 and the dispatch template), status flips to merged names, claim flow via `pick-next` + host stamping.
3. `.opencode/agents/architect.md` + `.opencode/skills/brainstorming/SKILL.md`: gate vocabulary G1a/G1b/G2 → A/B/C (G7 survives only inside `PR (G7)`).
4. `docs/setup/new-project-setup.md`: old-model status mentions → merged names.
5. `.opencode/skills/finishing-a-development-branch/SKILL.md`: the architect report template's Board Update block drops the dead `Next Up: was 1|2|3|not in queue` line — the block reports status/gate/host fields only.

### Required Docs
- Spec §Documentation (the closure list); #24 spec §Переходное состояние (what was promised).

### DoD
- `grep -rn "In Design (G1a)\|Spec OK (G1b)\|Ready to IMPL (G2)" docs/workflow docs/setup .opencode/agents .opencode/skills/finishing-a-development-branch .zcode/skills/github-board .zcode/skills/design-phase .zcode/skills/auto-design` → empty (scoped to the changed file set — historical specs/plans legitimately cite old names and are NOT touched: exclude `docs/specs`, `docs/plans`, `.zcode/plans`).
- `grep -rn "next-up\|set-next-up" .opencode/agents/manager.md` → empty.
- Spec §Documentation closure claim now true for canon texts (site excepted by design).

---

## Task 7: Live verification + wiring (manual, against board #4)

### Classification: small

Execute the spec's Wiring checklist: if `docs/board/board_config.json` is absent, run `board_bootstrap.py adopt 4 --repo mkosinov/superagents` (#24) and commit it; if #24's close-out already committed the config, verify the project-#4 mapping instead — never force a regeneration (config is repo content with a single writer). Then read-only checks (`show all`, `pick-next imac`, `pick-next-design`, `reconcile --dry-run`, `gate N none` round-trip on #23's own card); create the ZCode automation card (2h, host passed explicitly via `GH_BOARD_HOST=imac` or arg); start the container watcher (`docker exec -d opencode bash /root/workspace/superagents/.opencode/scripts/auto_impl_watch.sh`, enable file present); observe one auto-design cycle and one pick-next cycle.

### Required Docs
- Spec §Wiring after ship; §Testing (manual live verification).

### DoD
- Config committed; board #4 readable through the new script; one full cycle of each loop observed with gate/host fields ending in the expected state.

---

## Task 8: Final verification and merge

### Classification: trivial

Full CI green (both board workflows), twins identical, grep sweeps from Tasks 4/6 clean, spec/plan status lines updated, PR squash-merge (this issue's diff touches executable harness — fast-track is NOT eligible by the spec's own rule).

### DoD
- All prior DoD lines hold on the merged main; the #24 spec's transitional section is closed by this issue.

---

## Scenario → task map

| Spec scenario | Automated in | Live check |
|---|---|---|
| 1 pick-next priority+budget | Task 1 | Task 7 |
| 2 pick-next-design slot invariant | Task 1 | Task 7 |
| 3 gate set/clear | Task 2 | Task 7 (round-trip) |
| 4 status stamping matrix | Task 2 | — |
| 5 reconcile dry-run no mutations | Task 2 | Task 7 |
| 6 config-driven fresh repo | Task 1 | Task 7 (adopt + load) |
