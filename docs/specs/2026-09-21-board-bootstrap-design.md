# Board Bootstrap: roll out a project from the etalon — Design (issue #24)

**Date:** 2026-09-21
**Status:** G1a approved (concept, 2026-09-22); G1b panel reviewed 2026-09-22 (6/6: 5 NEEDS_REVISION, 1 SOUND), all fixes folded — G1b approved 2026-09-22; plan G2 approved 2026-09-22 (docs/plans/2026-09-22-board-bootstrap-plan.md)
**Author:** host design session (brainstorming with user)

**Placement:** superagents is the tooling canon. The script ships in BOTH harness folders (`.zcode/scripts/` + `.opencode/scripts/`, identical twins per the gh_board.py header convention) and travels to consumer repos with the harness copy step. The etalon doc lives in `docs/board/board-etalon.md`; the generated config lives in `docs/board/board_config.json` (both resolved from the repo root derived from the script's own path — the same `parents[2]` convention `gh_board.py` uses, so both twins read and write the same files).

---

## Summary

Board rollout for a new repo is today a manual gh command sequence (verified 2026-09-21 for project #4; the log with discovered quirks is a comment in issue #23). `board_bootstrap.py` turns it into one run: create a GitHub Project whose fields and options come from the declarative **etalon doc**, link the repo, seed the open issues as cards at `Backlog`, and write `board_config.json`.

Two modes: **`init`** (create a new project from the etalon) and **`adopt`** (connect an EXISTING project: compare with the etalon, write the config — never mutate the board). Both support `--dry-run`. A guard refuses destructive reruns with an explicit description of the damage prevented. CI runs an **offline** dry-run smoke plus unit tests (no secrets, no network at all).

This issue defines **board_config.json format v1** and the **etalon doc format** — issue #23 (gh_board.py parameterization + memo stack port) consumes both. The pick-priority rule (below) is specified here and implemented there.

## Goals

- One run rolls out a usable board for any repo with open issues.
- The etalon doc is the single source of truth for board shape (machine block) and field meaning (prose).
- `board_config.json` ends the era of constants baked into `gh_board.py` by hand (#23 consumes it).
- `adopt` gives the two existing boards (superagents #4, memo #3) their configs without touching a live board.
- `--dry-run` makes the whole plan readable before anything runs — with zero network calls (also the CI smoke).

## Non-Goals (deliberately NOT built here)

- `gh_board.py` parameterization and pick-next/pick-next-design changes — issue #23. Including the pick-priority rule implementation (specified here, built there) and the skill/docs port to the merged-statuss model (see «Переходное состояние»).
- Gate/host stamping behavior in the skills (`github-board`, `design-phase`) — part of #23's skill port.
- Any mutation of an existing project. `adopt` compares and writes config only; "repairing" a mismatched board is refused, not attempted.
- A live smoke on a throwaway project (decision 2026-09-22: dry-run only; the first real rollout is the live validation of the mutation chain — accepted risk). The User Scenarios that need live projects are therefore **manual one-shot acceptance runs at implementation time**, not automated tests (see Testing).
- Project views (table/kanban layouts) — the gh CLI does not manage views; web UI only.
- The GitHub web "auto-add to project" workflow (decided 2026-09-22: out of CLI reach; the rule «created an issue → add its card» already lives in the github-board skill and keeps the board complete).
- A site page rendering the etalon (the project site is a showcase layer over the file; file-first, page later if wanted — separate work).
- The Next Up queue — the field is deleted on both boards; the etalon does not resurrect it.
- Shipping the CI smoke to consumer repos (canon-only; a consumer may copy it if wanted).
- A separate JSON machine file for the etalon (decided 2026-09-22 over a schema-tooling argument: one markdown doc with an embedded block is the single human+machine source; the block parser is covered by unit tests).

---

## Переходное состояние (canon drift, owned by #23)

The canon's skills, workflow docs, manager body, `gh_board.py` constants and the site still encode the pre-memo board model (status names with gate suffixes — `In Design (G1a)`, `Spec OK (G1b)` — and the deleted Next Up queue). The live boards already carry the merged model this spec describes. Until #23 ports those artifacts: read `In Design (G1a)`/`Spec OK (G1b)` as plain `In Design`, `Ready to IMPL (G2)` as `Ready to IMPL` (the G2 flip target exists under that name), and ignore `next-up`/`set-next-up`/`shift` commands (they degrade gracefully on the dead field). Owner of the interim: this spec documents it; the artifact fixes ship with #23.

---

## Concepts

### Board anatomy (the two worlds)

A **project** (ProjectV2) is a GitHub table owned by an account (here: `mkosinov`). Inside it: **fields** (attribute columns — the single-selects `Status`, `Priority`, `host`, `gate`), **items** (rows — one per issue), and **views** (tabs: table / kanban / timeline — presentation only). The project and its contents live in the GitHub cloud; the scripts and `board_config.json` live in the git repo. `board_bootstrap.py` writes both worlds: cloud (project, fields, items) and git (config).

### The etalon doc — `docs/board/board-etalon.md`

A markdown document: prose semantics per field (short — what each field and its options mean) plus one fenced machine block:

    ```board-etalon
    {
      "version": 1,
      "fields": [
        {"name": "Status", "type": "single_select", "options": ["Hold", "Backlog", "In Design", "Ready to IMPL", "In IMPL", "PR (G7)", "In-main", "deployed", "Not planned"]},
        {"name": "Priority", "type": "single_select", "options": ["Critical", "High", "Medium", "Low"]},
        {"name": "host", "type": "single_select", "options": ["imac", "macbook", "hk", "gcp"]},
        {"name": "gate", "type": "single_select", "options": ["concept", "spec", "plan", "blocked"]}
      ],
      "host_budgets": {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1}
    }
    ```

Option order in the block is the option order on the created field. Field/option values match the live boards #4 and #3 verbatim (verified 2026-09-22). Etalon resolution: `--etalon <path>`, else `docs/board/board-etalon.md` (repo root resolved from the script's path). Missing file or malformed block → refuse **before any network call**, naming the path and the parse error. The dry-run plan always prints which etalon path was used.

**Drift contract (statuses):** the etalon is the intent, the web UI is the fact (the option list is user-managed there, e.g. `Not planned` was added on 2026-09-09). `adopt` compares and warns on any difference; it never writes options anywhere.

### board_config.json (format v1)

One canonical path: `docs/board/board_config.json` (repo root derived from the script's path — both twins resolve the same file; the path is outside any harness gitignore, verified tracked in both repos' layouts). Committed to the repo (it carries no secrets).

    {
      "version": 1,
      "project_id": "PVT_…",
      "project_number": 4,
      "owner": "mkosinov",
      "repo": "superagents",
      "fields": {"Status": "PVTSSF_…", "Priority": "PVTSSF_…", "host": "PVTSSF_…", "gate": "PVTSSF_…"},
      "host_budgets": {"imac": 2, "macbook": 1, "hk": 1, "gcp": 1}
    }

Option ids are **not** stored: they are project-specific and must be read from `field-list` at run time, never hardcoded (rollout-log quirk). `host_budgets` travel in the config so #23's parameterized `gh_board.py` reads one file (copied from the etalon at init/adopt). `#23`'s script reads this file (project id, owner, repo, field ids, budgets).

### Field semantics (the etalon's prose content — memo's model)

- **Status** — lifecycle stage; merged names (no gate suffixes): `Hold` (paused) → `Backlog` (not in trajectory) → `In Design` (design underway, gates G1a–G2 pass inside it) → `Ready to IMPL` (plan approved, waiting for dispatch) → `In IMPL` (implementation running) → `PR (G7)` (pull request on CI) → `In-main` (merged) → `deployed`; `Not planned` = closed without plans. Gate stops are tracked in the `gate` field, not in status names. Note: a single-select's first option is what a freshly added item may get — the workflow rule «created an issue → set its status explicitly» (github-board skill) covers this; `init` sets every seeded card explicitly.
- **Priority** — importance (Critical/High/Medium/Low). Behavioral rule (pick-priority, implemented in #23's `pick-next` / `pick-next-design`): among status-eligible cards, an elevated-priority card is taken first — order Critical > High > Medium > Low; a card with **no priority sorts last**; priority breaks ties among equals and does NOT override readiness (a `Backlog` card never jumps a `Ready to IMPL` card).
- **host** — which machine owns the card (`imac` / `macbook` / `hk` / `gcp`). Single ownership source for `In IMPL` / `In Design`: stamped on entering those statuses, cleared on leaving — except the label survives `PR (G7)` (a card on CI stays visibly owned) and clears when it leaves `PR (G7)`. Per-host budget (host_budgets): imac 2, macbook 1, hk 1, gcp 1 — `In IMPL` cards count against their machine's budget; an `In IMPL` card with empty host blocks no one.
- **gate** — the pending-ask marker (`concept` / `spec` / `plan` / `blocked`): a design gate stop (concept = G1a, spec = G1b, plan = G2) or an IMPL blocker awaiting the user (`blocked`). Stamped when the question is asked, cleared at the user's answer and automatically when the card leaves `In Design` / `In IMPL`. Empty = nothing awaits the user.

---

## board_bootstrap.py

### Interface

    board_bootstrap.py init  --repo <owner/name> --title <project title> [--owner <login>] [--etalon <path>] [--out <path>] [--dry-run]
    board_bootstrap.py adopt <project-number> --repo <owner/name> [--owner <login>] [--etalon <path>] [--out <path>] [--force] [--dry-run]

- `--owner <login>` — the project owner's explicit login; defaults to the `--repo` owner. Never `@me` (it fails with "different owner", rollout-log quirk).
- `--out <path>` — where to write the config; defaults to `docs/board/board_config.json` under the script's own repo root. Cross-repo adoption uses it explicitly (e.g. writing memo's mapping from the canon checkout: `--out <memo-checkout>/docs/board/board_config.json`). Guards check the **effective** config path.
- `--dry-run` — **zero network calls**: parse the etalon, validate arguments and local pre-flight, print the plan tree. Where live data would be read (issue list, project fields), the plan says "read at run time". Unit tests drive the comparison/seeding planners on fixture data instead.
- `--force` (adopt only) — deliberate overwrite of an existing `board_config.json`.
- Item ids during seeding come from gh's JSON output (`item-add --format json`), never from parsed text.

Rules enforced in both modes: **etalon parsed and validated before any network call** (step order guarantees it); `gh auth status` pre-flight; every gh mutation followed by a verification read (gh is silent on success, rollout-log quirk); all gh pagination explicit (no 30-row defaults — loop until exhausted for issue listing and field reads).

### `init` behavior (steps)

1. Etalon parse/validate (strictly first — before any network call).
2. Local + auth pre-flight (`gh auth status`), then the guards (below).
3. Create the project (`gh project create --owner <login> --title <title>`, project number taken from the JSON output).
4. **Remove the built-in `Status` field every new project ships with** (Todo / In Progress / Done), then create each etalon field with its options in etalon order (`gh project field-create --number N --owner <login> --name <name> --data-type SINGLE_SELECT --single-select-options "a,b,c"` — capability verified in gh CLI). The delete-and-recreate step exists because gh cannot edit options of an existing field (verified: only field-create / field-delete / field-list); [предположение to verify at implementation]: if the built-in field turns out undeletable, the fallback is a targeted GraphQL option-list update on the freshly created **empty** project — a documented exception to the field-mutation ban, which exists to protect card values (there are none yet).
5. Link the repo (`gh project link <number> --owner <login> -R <owner/name>`).
6. Seed open issues: list **all** open issues with explicit pagination, `item-add` each (`--format json` for the item id), then set `Status = Backlog` per item via `item-edit` — the Backlog option id read from `field-list` at run time.
7. Write `docs/board/board_config.json` (ids read back from the live project after creation; `host_budgets` copied from the etalon).

### `adopt <project-number>` behavior

1. Etalon parse, pre-flight.
2. Verify the project is linked to `--repo` (one read); not linked → refuse.
3. Read the project's custom single-select fields (`field-list`, filtered to the etalon's field type — built-in metadata columns like Title/Labels/Assignees are ignored) and compare with the etalon by **exact name match** (no prefix tolerance):
   - a **missing** field or a **missing** option → REFUSE with the full difference list;
   - an **extra** field or an **extra** option → WARN with the list and proceed (drift contract: etalon = intent, web UI = fact).
4. Write `docs/board/board_config.json` (`host_budgets` copied from the etalon). `adopt` never mutates the project. An existing config → refuse; `--force` overwrites deliberately.

### Guard (damage prevention)

- `init` refuses if `board_config.json` already exists at the canonical path (`docs/board/board_config.json`). Damage described in the refusal: a second run creates a **duplicate project**, re-seeds the issues as **duplicate cards**, and **overwrites the config** — the previously rolled-out board loses its config and goes unwatched. One canonical path means running either twin hits the same guard.
- `init` refuses if the repo is already linked to ANY open project. Implemented as one read pass over the owner's open projects (a repo-side "my projects" connection is not guaranteed in the GraphQL schema — the exact connection field is confirmed by schema introspection at implementation, with a documented downgrade: no connection field found → the guard degrades to the config check plus the title-collision warning, recorded in the PR). Simpler and stricter than the earlier "has items or custom fields" wording, which missed a freshly created empty board — exactly the duplicate case. All list reads carry explicit limits (no 30-row defaults).
- Title collision with an existing open project of the same owner → warning (GitHub allows duplicate titles), naming both.
- Every refusal names what was found and exactly what would have been broken.

### Error handling

- Missing/malformed etalon → exit before any network call; name the path and the parse error (User Scenario 7).
- Mid-run failure in `init` → report exactly what was created so far (project id, created fields, added items) and print the manual cleanup commands. No automatic deletion: the API has no transactions and auto-deletion risks destroying pre-existing resources.
- Recovery path after a partial `init`: the printed report is the repair input — clean up by hand (or `adopt` the half-made project, which refuses with the difference list until it matches the etalon); `--force` covers config rewrites only.
- Verification read after every mutation; expected-vs-actual mismatch → stop and report.

### Dry-run output (the visual plan)

A tree of what WOULD happen — the etalon path used → project to create → fields with options → built-in `Status` removal → repo link → seeding plan (what would be listed live) → config path. `adopt --dry-run` prints the planned comparison (fields to read, criteria) or, with fixture input in unit tests, the comparison result. Offline: the plan never touches the network.

---

## CI

`.github/workflows/board-bootstrap.yml`: on push/PR touching the script or the etalon — run the etalon-parser and planner **unit tests** (fixture data for issue lists and field lists, including the adopt comparison matrix) plus `init --dry-run` and `adopt --dry-run` (offline plan render), asserting exit code 0 and expected plan lines. No secrets, no network — live reads are deliberately out of CI (the Actions token cannot reach user-owned projects anyway; verified against GitHub docs at review).

## Documentation

- `docs/setup/new-project-setup.md` step 0: replace "create a GitHub Project and bake its constants into both twins" with "copy `docs/board/board-etalon.md` from the canon (or point `--etalon` at it) and run `board_bootstrap.py init` (or `adopt` for an existing board)". Transitional note kept visible: until #23 lands, `gh_board.py` still needs its constants baked by hand — the config written here is what #23's parameterization consumes. (The harness copy steps ship only `.zcode/` and `.opencode/`, so the etalon's delivery to consumers is this explicit copy step.)
- The single-writer board rule gains one exception line: `board_bootstrap.py` is the rollout-time writer (create/link/seed); everyday board writes stay exclusively `gh_board.py`'s (the rule's target is hand-written GraphQL mutations — the 2026-09-09 wipe).
- The etalon doc carries the field semantics; a richer presentation may later render it on the project site as a showcase over the file (file-first: the file is always the source).

---

## User Scenarios (each maps to an E2E test — see Testing for which are automated)

1. **Roll out a board in a new repo** — run `init`, get a project whose fields/options match the etalon (its own `Status`, no built-in leftovers), all open issues seeded at `Backlog`, `board_config.json` written. (Manual one-shot at implementation: throwaway repo + project; cleanup deletes the project.)
2. **Re-run protection** — run `init` twice; the second run refuses from either twin, describes the damage prevented, creates nothing. (Manual one-shot + unit test of the guard.)
3. **Adopt an existing board** — run `adopt` on a project matching the etalon (e.g. #4); get the config written, board untouched. (Manual one-shot + unit test of the comparison.)
4. **Mismatch report** — `adopt` on a board with a missing field → refusal with the difference list; with an extra field → warning + config written. (Unit tests on fixtures; one live spot check.)
5. **Dry-run plan** — `init --dry-run` prints the plan tree (incl. the etalon path) and touches nothing. (Automated in CI.)
6. **Empty repo** — `init` on a repo with zero open issues: project + config created, seeding empty, exit 0. (Manual one-shot.)
7. **Broken etalon** — malformed block or missing file → refusal with the parse error before any network call. (Automated: unit tests + CI.)

## Reuse

- **The verified gh command sequence** from the rollout log (issue #23 comment, 2026-09-21): create → link → item-add → item-edit, with its quirks carried as behavior: explicit owner login (never `@me`), option ids read from `field-list` at run time, verification reads after silent-success mutations. (Source: issue #23 «Board rollout log» comment.)
- **`gh project field-create --single-select-options`** — verified gh CLI capability (options seeded at field creation); the built-in `Status` removal (field-delete + recreate) is required because gh cannot edit options of existing fields (verified at review).
- **argparse conventions** from the repo's own scripts (`session_find.py`); **JSON file loading** as in `subagent-audit.py` (the repo's existing `json.load` pattern).
- **Twin convention** from the `gh_board.py` header: identical copies in `.zcode/scripts/` and `.opencode/scripts/`, "change both (or edit one and copy over)".
- **Repo-root resolution** from the script's own path (`Path(__file__).resolve().parents[2]`) as `gh_board.py` and `scratchpad_audit.py` already do — anchors the canonical etalon/config paths for both twins.
- None reusable for config-file semantics — searched: `board_config`, `json.load` across both repos' script dirs (only `subagent-audit.py` loads JSON; no config-file pattern exists to mirror).

## Dependencies and ordering

- **Strictly before #23.** This issue defines `board_config.json` format v1 (incl. `host_budgets`) and the etalon doc; #23's gh_board.py parameterization (its scope item 4) reads the config, and #23's pick-next / pick-next-design implement the pick-priority rule specified above (requirement also logged as a comment on #23, 2026-09-21). The gate/host semantics here seed #23's skill port to memo's model; #23 also owns the canon-drift fixes listed in «Переходное состояние».
- Scope check against issue #24 (done by the main session, 2026-09-22): all four scope items covered — (1) etalon doc incl. semantics + host budgets, (2) bootstrap script with create decision resolved to explicit `create` + `field-create` (not `project copy` — kept after the panel re-raised copy: copy needs a same-account donor and drags donor views, and it would make the live board, not the etalon doc, the source of truth), repo link with the `@me` quirk, issue seeding, `Status=Backlog` with runtime option ids, `board_config.json` write, (3) guard with damage description, (4) CI smoke as offline dry-run + unit tests. The naming decision (`init`/`adopt`) and the dry-run-only CI decision are baked in above.

## Testing

- Unit tests for the etalon block parser: valid block, malformed JSON, missing block, unknown field type (Scenario 7).
- Unit tests for the adopt comparison matrix (missing/extra field and option; built-in metadata columns ignored) and the seeding/guard planners on fixtures (Scenarios 2–4 logic).
- CI offline smoke: both dry-runs render the expected plan trees (Scenario 5).
- Manual one-shot acceptance runs at implementation (toy-IMPL loop / first real rollout) for Scenarios 1, 3, 4 (live spot), 6 — the accepted live validation of the mutation chain.
