# Board Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `board_bootstrap.py` (identical twins) and `docs/board/board-etalon.md` so any repo rolls out its GitHub Project board from the etalon in one `init` run — or connects an existing board with `adopt` — with a destructive-rerun guard and an offline CI dry-run smoke.

**Architecture:** One stdlib-only Python script mirroring `gh_board.py` conventions (argv-list `subprocess.run(["gh", ...])`, never shell=True; repo root via `Path(__file__).resolve().parents[2]`; identical twins in `.zcode/scripts/` and `.opencode/scripts/`). Network-free pure planners (etalon parse, adopt comparison, config build, plan render, guard planner) are unit-tested on fixtures; a thin gh-runner layer executes the verified command sequence — create project → delete built-in `Status` → create etalon fields → link repo → seed issues at `Backlog` → write config — with a verification read after every mutation and explicit `--limit` on every list read (no 30-row defaults). CI runs unittest plus both `--dry-run` modes with zero network and zero secrets. Config writes to `--out <path>` (default `docs/board/board_config.json` under the script's repo root; the default is what makes the twin-guard one logical guard — cross-repo adoption passes `--out` explicitly).

**Tech Stack:** Python 3.12 stdlib (json, argparse, dataclasses, subprocess, pathlib, re, unittest), gh CLI 2.76+ (`gh project` subcommands, `gh api graphql` read-only from inside the script), GitHub Actions.

Spec: `docs/specs/2026-09-21-board-bootstrap-design.md` (G1b approved 2026-09-22). Plan reviewed 2026-09-22 (plan-reviewer: NEEDS_REVISION, 0 blockers) — all findings folded.

---

## Behavioral Delta

How this feature behaves for the user, mapped to the spec's User Scenarios:

- **Scenario 1 (rollout)** → one `init` command leaves the repo with a board whose fields and options exactly match the etalon (its own `Status` with the nine statuses, no built-in leftovers), every open issue at `Backlog`, and `docs/board/board_config.json` written.
- **Scenario 2 (re-run)** → a second `init` — from either script copy — refuses, spells out the prevented damage (duplicate project, duplicate cards, overwritten mapping), changes nothing.
- **Scenario 3 (adopt)** → `adopt 4 --repo mkosinov/superagents` writes the config while the board stays byte-identical (no mutations ever); `adopt 3 --repo mkosinov/memo --out <memo-checkout>/docs/board/board_config.json` does the same for memo's board from any checkout.
- **Scenario 4 (mismatch)** → `adopt` on a board missing a field/option refuses listing every difference; on a board with extras it warns listing them and writes the config anyway.
- **Scenario 5 (dry-run)** → `--dry-run` prints a tree plan including the etalon path used and the guard verdicts in report-only form (a would-be refusal is a plan line, never an exit), and performs zero network calls.
- **Scenario 6 (empty repo)** → `init` succeeds with an empty seeding section.
- **Scenario 7 (broken etalon)** → malformed or missing etalon aborts with the parse error and the path before any network call.
- **Config for #23** → `board_config.json` v1 (project id/number, owner, repo, field ids, host budgets) appears at the canonical path (or `--out`) both script copies resolve.

Deviation from the E2E-in-DoD rule, decided in the spec's Testing section: the mutation chain has no live CI (dry-run only), so scenarios 1/3/4/6 are manual one-shot acceptance runs — their DoD lines name the Task 7 runbook instead of an automated E2E. Scenarios 2/5/7 carry automated tests with RED-GREEN-REFACTOR.

## File Structure

- `docs/board/board-etalon.md` — create: etalon (prose semantics + `board-etalon` machine block). Single source of truth for board shape.
- `.zcode/scripts/board_bootstrap.py` + `.opencode/scripts/board_bootstrap.py` — create: identical twins. CLI entry + pure planners + gh runner + config writer in one file (mirrors the single-file `gh_board.py` pattern).
- `tests/test_board_bootstrap.py` — create: unittest suite (parser, comparison matrix, config shape, plan render, guard planner, CLI flag wiring) on fixtures.
- `.github/workflows/board-bootstrap.yml` — create: offline smoke.
- `docs/setup/new-project-setup.md` — modify: step 0 rewrite (etalon delivery + bootstrap command).
- `.zcode/skills/github-board/SKILL.md` + `.opencode/skills/github-board/SKILL.md` — modify: one exception line to the single-writer board rule.

---

## Task 1: Etalon doc
### Classification: trivial
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — sections «The etalon doc» and «Field semantics»: the exact machine block and the per-field prose meanings. Copy content from there; invent no values.

### Task Description
Create `docs/board/board-etalon.md` with: title; one prose subsection per field — `Status` (merged lifecycle names; explicit status-set rule + first-option note), `Priority` (pick-priority rule, empty priority sorts last, never overrides readiness), `host` (ownership lifecycle, survives `PR (G7)`, budgets imac 2 / macbook 1 / hk 1 / gcp 1), `gate` (concept=G1a, spec=G1b, plan=G2, blocked=IMPL blocker; stamp/clear lifecycle); the fenced `board-etalon` block byte-identical to the spec's block; the drift-contract paragraph (etalon = intent, web UI = fact; adopt only warns).

### Steps
- [ ] Create the file (content per Required Docs)
- [ ] Visually verify exactly one ```board-etalon fenced block present
- [ ] Commit `docs(board): board etalon — declarative board definition`

### DoD
- Block byte-identical to the spec's; every semantic from the spec's «Field semantics» present in prose.

## Task 2: Etalon parser + dry-run plan render
### Classification: standard
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — «The etalon doc» (resolution: `--etalon <path>` else `docs/board/board-etalon.md`), «board_bootstrap.py / Interface» (flag contracts incl. `--out`, `--force`, dry-run semantics), «Error handling» (refuse before any network call), «Dry-run output», Testing (scenario 7 cases)
- `.zcode/scripts/gh_board.py` header — twin convention and repo-root resolution to mirror
- `.opencode/scripts/session_find.py` — the repo's argparse conventions to mirror
- `.opencode/scripts/subagent-audit.py` — the repo's existing `json.load` pattern (reuse for the config writer in Task 3)

### Task Description
In `board_bootstrap.py` (write in `.zcode/scripts/`, copy to `.opencode/scripts/` at task end):

```python
BLOCK_RE = re.compile(r"```board-etalon\n(.*?)\n```", re.S)

class EtalonError(Exception): ...          # carries reason text only

@dataclass(frozen=True)
class Etalon:
    fields: list[dict]          # [{"name","type","options":[str,...]}] in etalon order
    host_budgets: dict[str,int]

def parse_etalon(text: str) -> Etalon:
    """Extract the fenced block (exactly one) and json.loads it; validate:
    version == 1; fields non-empty; every field type == 'single_select' with a
    non-empty list of unique option names; host_budgets values are ints >= 1.
    Raise EtalonError(reason) on any violation."""

def load_etalon(path_arg: str | None) -> tuple[Etalon, Path]:
    """path_arg else repo_root / 'docs/board/board-etalon.md'
    (repo_root = Path(__file__).resolve().parents[2]). Missing file, no block,
    bad JSON -> EtalonError naming the path and the cause."""

def render_plan(mode: str, args, etalon: Etalon, etalon_path: Path,
                guard_verdicts: list[str]) -> str:
    """Offline text tree. Lines, in order:
    etalon: <path>; project: create "<title>" (owner <login>);
    remove built-in field Status (Todo / In Progress / Done);
    create <field>: <opt> | <opt> | ...  (one line per etalon field);
    link: <owner/repo>; seed: open issues would be listed live
    (--dry-run: no network); config: <out path>. One 'guard: <verdict>' line
    per guard (report-only). adopt mode prints the planned comparison instead
    of create/link lines."""
```

`--dry-run` (both modes) = `load_etalon` → guard planner in **report-only** mode (verdicts become plan lines; a would-be refusal never changes the exit code — this is what keeps CI green after the real config is committed) → `render_plan` → print → exit 0. Zero network calls. Flag wiring (argparse per `session_find.py` conventions) honors `--etalon` and `--out` in dry-run paths.

### Steps
- [ ] RED: `tests/test_board_bootstrap.py` scenario 7 cases — valid block; missing block; malformed JSON; unknown field type; duplicate option; empty options; budget 0 — each asserting `EtalonError` reason text; run `python3 -m unittest tests.test_board_bootstrap -v` → ImportError (module missing)
- [ ] GREEN: implement `EtalonError`, `Etalon`, `parse_etalon`, `load_etalon` minimally → tests pass
- [ ] RED: plan-render test asserting the tree lines above (incl. `etalon: <path>` and one `guard:` line — scenario 5) and a CLI-wiring test: `init --dry-run --etalon <tmpfile>` prints `etalon: <tmpfile>` while `--out <tmpfile2>` prints `config: <tmpfile2>`
- [ ] GREEN: `render_plan` + argparse wiring → passes
- [ ] `diff .zcode/scripts/board_bootstrap.py .opencode/scripts/board_bootstrap.py` → empty
- [ ] Commit `feat(board-bootstrap): etalon parser and dry-run plan render`

### DoD
- Automated tests for scenario 7 pass (RED-GREEN-REFACTOR); plan-render and CLI-wiring tests pass (scenario 5); twins identical.

## Task 3: Adopt comparison + config builder
### Classification: standard
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — «board_config.json (format v1)», «adopt <project-number> behavior» (exact match, missing=refuse, extra=warn), «Field semantics» (host_budgets)
- `docs/board/board-etalon.md` — the drift-contract paragraph (comparison philosophy)
- `.opencode/scripts/subagent-audit.py` — its `json.load` pattern (the config writer mirrors it)

### Task Description

```python
def compare_fields(etalon: Etalon, live: list[dict]) -> dict:
    """live = gh project field-list JSON entries filtered to single-select
    fields only (built-in metadata columns — Title/Labels/Assignees/etc — are
    ignored). Exact name matching (no prefix tolerance). Returns
    {"missing_fields": [..], "missing_options": {field: [..]},
     "extra_fields": [..], "extra_options": {field: [..]}}.
    ok_to_adopt = not missing_fields and not missing_options."""

def build_config(project_id: str, project_number: int, owner: str, repo: str,
                 field_ids: dict[str,str], host_budgets: dict[str,int]) -> dict:
    """format v1 exactly: version, project_id, project_number, owner, repo,
    fields {name: field_id}, host_budgets. Option ids never included."""

def write_config(path: Path, config: dict) -> None:
    """json.dump (indent=2) to the effective path (--out or default);
    mkdir parents. Mirrors the subagent-audit.py loading conventions."""
```

### Steps
- [ ] RED: comparison matrix tests (fixtures) — missing field → refuse; missing option → refuse; extra field/option → warn-ok; metadata columns ignored; `In Design (G1a)` vs `In Design` is missing+extra (exact match, scenario 4)
- [ ] GREEN: `compare_fields` → passes
- [ ] RED: config-shape test — keys per format v1, `version == 1`, no option ids, budgets copied
- [ ] GREEN: `build_config`, `write_config` → passes
- [ ] Copy to twin; `diff` empty
- [ ] Commit `feat(board-bootstrap): adopt comparison and board_config v1 builder`

### DoD
- Scenario 3/4 comparison tests pass (RED-GREEN-REFACTOR); config shape test passes; twins identical.

## Task 4: Guards + adopt mode + error paths
### Classification: standard
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — «Guard (damage prevention)», «adopt behavior», «Error handling» (recovery path, `--force`), «Rules enforced in both modes» (auth pre-flight, etalon-first ordering, explicit pagination)
- `.zcode/scripts/gh_board.py` — the `gql()` read pattern (script-internal `gh api graphql`, argv-list) to mirror

### Task Description

Guard planner (pure, fixture-tested) + networked checks:

- `guard_config_exists(path)` → refuse if the effective config path exists (damage text: "a second run creates a duplicate project, re-seeds the issues as duplicate cards, and overwrites the config"); `--force` (adopt only) overrides.
- `guard_repo_has_project(owner, repo)` (for `init`) → refuse if ANY open project of the owner links the repo. Implementation: introspect once — `gh api graphql -f query='query{__type(name:"ProjectV2"){fields{name}}}'` — and use the repository-connection field (expected `linkedRepositories`); if neither that nor a `repositories` connection exists in the schema → documented downgrade: this guard reports "skipped: no repository connection in schema" and the check degrades to `guard_config_exists` + the title-collision warning (record the downgrade in the PR description). Enumerate `gh project list --owner <login> --format json --limit 1000` (explicit limit) and read each project's linked repos with one query: `query{node(id:"<PVT…>"){...on ProjectV2{number title <connection>{nodes{owner login name}}}}}`.
- `verify_project_links_repo(project_number, owner, repo)` (for `adopt`) → refuse if THE project is not linked to `--repo` (the inverse predicate of the init guard — different contract, do not share code paths).
- Title collision: same owner, equal title among open projects → warning naming both (GitHub permits duplicates).
- `cmd_adopt` step order (per «Rules enforced in both modes»): `load_etalon` (strictly first) → `gh auth status` → `verify_project_links_repo` → `gh project field-list <number> --owner <login> --format json --limit 200` (explicit limit; if returned length hits the limit → refuse naming the cap) → `compare_fields` → missing → refuse with the full difference list; extra → warn + proceed → `write_config(--out or default)`.
- Error paths: existing config → refuse naming `--force`; `EtalonError` → the pre-network refusal of scenario 7.

### Steps
- [ ] RED: guard-planner unit tests (fixtures): config exists → refusal text contains "duplicate project"; linked project found → init refuses; adopt on unlinked project → refuses; adopt on linked project → passes; title collision → warn-only; `--force` → overwrite allowed (scenario 2)
- [ ] GREEN: guard planner functions + both link checks (schema-field name resolved by the introspection step; fallback behavior covered by a fixture test) → passes
- [ ] Implement `cmd_adopt` wiring to `gh_json`/`gql` reads in the mandated order
- [ ] Copy to twin; `diff` empty
- [ ] Commit `feat(board-bootstrap): guards and adopt mode`

### DoD
- Scenario 2 guard tests pass (RED-GREEN-REFACTOR), including the introspection-fallback fixture; adopt scenarios 3/4 manual one-shot via the Task 7 runbook; twins identical.

## Task 5: init mode — gh runner
### Classification: large
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — «init behavior (steps)», «Rules enforced in both modes», «Error handling» (partial-failure report + recovery routes)
- Issue #23 «Board rollout log» comment (https://github.com/mkosinov/superagents/issues/23) — quirks: explicit login never `@me`; gh is silent on success → verify by read-back; option ids read at run time
- `.opencode/scripts/session_find.py` — argparse conventions (flag wiring consistency with Task 2)

### Task Description
Wire `init` to the verified sequence (gh 2.76 signatures, verified 2026-09-22):

1. `load_etalon` (strictly first — before any network call), then `gh auth status` (non-zero exit → refuse, naming it).
2. Guards (Task 4 functions: `guard_config_exists`, `guard_repo_has_project`, title-collision warning).
3. `gh project create --owner <login> --title <title> --format json` → `number` (owner = `--owner` or the `--repo` owner).
4. `gh project field-list <number> --owner <login> --format json --limit 200` → find the built-in `Status` (single-select with options Todo/In Progress/Done) → `gh project field-delete --id <fieldId>`. [verify at implementation: if the built-in field is undeletable, fall back to a targeted GraphQL option-list update on the still-empty project — documented exception to the field-mutation ban (it protects card values; there are none yet); record the outcome in the PR description.]
5. Per etalon field: `gh project field-create <number> --owner <login> --name <name> --data-type SINGLE_SELECT --single-select-options "opt1,opt2,..." --format json` → collect `{name: field_id}`.
6. `gh project link <number> --owner <login> --repo <owner/name>`.
7. Seed: `gh issue list --repo <owner/name> --state open --limit 10000 --json number,url` in ONE call (gh paginates internally up to `--limit`; there is no page/cursor flag — if the returned length hits the limit, refuse naming the cap and telling the operator to raise it); per issue `gh project item-add <number> --owner <login> --url <url> --format json` → item id, then `gh project item-edit --project-id <PVT…> --id <PVTI…> --field-id <StatusFieldId> --single-select-option-id <BacklogOptionId>` (both ids read back from the new project at run time).
8. Verification read after every mutation (field-list / `gh project item-list <number> --owner <login> --format json --limit 1000`); expected-vs-actual mismatch → stop and report.
9. `write_config(--out or repo_root/"docs/board/board_config.json", build_config(...))`.
10. On any mid-run failure: print exactly what was created (project id, fields, items) plus **per-resource cleanup** — items and fields are removed from the project's web board page, the project itself via its web Settings (gh has no project-delete command, verified against `gh project --help`) — and the second recovery route: `adopt <number>` on the half-made project (refuses with the difference list until it matches the etalon, then writes the config and the run continues by hand). No automatic deletion.

### Steps
- [ ] RED: unit tests for the partial-failure report formatter (inputs: created resources dict → output names project id, per-resource cleanup routes, and the adopt-recovery route)
- [ ] GREEN: report formatter passes
- [ ] Implement `cmd_init` per the sequence above; `gh_json(*args)` helper: `subprocess.run(["gh", *args], capture_output=True, text=True)` → non-zero exit → raise with stderr
- [ ] `python3 .zcode/scripts/board_bootstrap.py init --repo mkosinov/tmp-smoke --title "Smoke" --dry-run` prints the full tree (manual smoke of scenario 5 shape)
- [ ] Copy to twin; `diff` empty
- [ ] Commit `feat(board-bootstrap): init mode — create board from etalon`

### DoD
- Failure-report test passes (RED-GREEN-REFACTOR); dry-run smoke prints the tree; manual one-shot acceptance for scenarios 1, 2, 6 passes via the Task 7 runbook; twins identical.

## Task 6: CI smoke + docs + single-writer exception
### Classification: small
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — «CI», «Documentation», «Переходное состояние»
- `docs/setup/new-project-setup.md` — current step 0 («Host DESIGN Pipeline») being rewritten
- `.zcode/skills/github-board/SKILL.md` — the «Rules» section receiving the exception line

### Task Description
1. `.github/workflows/board-bootstrap.yml` (asserting plan lines, not just exit codes — per the spec's CI contract):

```yaml
name: board-bootstrap
on:
  push:
    paths: [".zcode/scripts/board_bootstrap.py", ".opencode/scripts/board_bootstrap.py", "docs/board/board-etalon.md", "tests/**"]
  pull_request:
    paths: [".zcode/scripts/board_bootstrap.py", ".opencode/scripts/board_bootstrap.py", "docs/board/board-etalon.md", "tests/**"]
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 -m unittest discover -s tests -v
      - name: init dry-run renders the plan
        run: |
          python3 .zcode/scripts/board_bootstrap.py init --repo example/tool --title "Smoke" --dry-run | tee /tmp/plan.txt
          grep -q 'etalon: docs/board/board-etalon.md' /tmp/plan.txt
          grep -q 'config: docs/board/board_config.json' /tmp/plan.txt
          grep -q 'remove built-in field Status' /tmp/plan.txt
      - name: adopt dry-run renders the comparison plan
        run: |
          python3 .zcode/scripts/board_bootstrap.py adopt 1 --repo example/tool --dry-run | tee /tmp/aplan.txt
          grep -q 'etalon: docs/board/board-etalon.md' /tmp/aplan.txt
          grep -q 'guard:' /tmp/aplan.txt
```

Guard verdict lines are report-only in dry-run — assertions target stable structural lines, so CI stays green after Task 7 commits the real config.
2. `docs/setup/new-project-setup.md` step 0: replace the "create a GitHub Project and bake its constants" bullet with: copy `docs/board/board-etalon.md` from the canon checkout (or point `--etalon` at it), run `board_bootstrap.py init` (or `adopt <number>`) from either script copy; the config lands at `docs/board/board_config.json` (`--out` for another repo) — commit it. Keep the transitional note: until #23 lands, `gh_board.py` constants are still baked by hand.
3. Both `github-board` skill twins — append to the single-writer rule bullet: "Exception: `board_bootstrap.py` is the rollout-time board writer (create/link/seed during repo setup only); everyday board writes remain exclusively this script's."

### Steps
- [ ] Add the workflow file
- [ ] Rewrite the step 0 bullet + transitional note
- [ ] Add the exception line to both skill twins (identical wording)
- [ ] Commit `chore(board-bootstrap): offline CI smoke, setup docs, single-writer exception`

### DoD
- CI green on push with no secrets and plan-line assertions (scenarios 5+7 automated); docs mention etalon delivery + bootstrap + `--out`; both skill twins carry the identical exception line.

## Task 7: Manual one-shot acceptance runbook
### Classification: small
### Required Docs
- `docs/specs/2026-09-21-board-bootstrap-design.md` — «User Scenarios», «Testing» (the manual/automated split), «Goals» (both existing boards get configs)

### Task Description
Execute once at implementation verification (toy-IMPL loop); record results as an issue #24 comment. Runbook:

1. **Scenarios 1+2+6 (throwaway):** `gh repo create mkosinov/tmp-board-smoke --private`; run `init --repo mkosinov/tmp-board-smoke --title "Tmp board smoke"`; assert fields/options equal the etalon, all issues at `Backlog`, config written; run `init` again from the `.opencode/scripts/` copy → assert refusal text names "duplicate project"; create a second empty repo and `init` it → seeding empty, exit 0.
2. **Scenario 3 (real, safe by design):** `adopt 4 --repo mkosinov/superagents` → assert config written and `gh project field-list 4` output identical before/after (adopt never mutates).
3. **Scenario 3b — memo's board (the second named deliverable):** from any checkout, `adopt 3 --repo mkosinov/memo --out <memo-checkout>/docs/board/board_config.json --etalon docs/board/board-etalon.md` → commit the config in the memo repo (separate commit, memo's own PR/branch discipline). Record the commit hash in the issue comment.
4. **Scenario 4 (throwaway):** on the throwaway project delete one field (`gh project field-delete`), run `adopt <number>` → refusal listing the missing field; add an extra option in the web UI → `adopt` warns and writes config.
5. **Cleanup:** delete `mkosinov/tmp-board-smoke` (`gh repo delete`) and the throwaway project via its web Settings page (gh has no project-delete command).

### Steps
- [ ] Run steps 1–4, capture outputs
- [ ] Cleanup step 5
- [ ] Post results comment on issue #24
- [ ] Commit the scenario-3 config `docs/board/board_config.json` (real superagents board mapping) in this repo

### DoD
- Manual one-shot acceptance for scenarios 1, 3, 4, 6 passes; both existing boards (#4 and memo #3) have their configs (Goal coverage); results recorded on issue #24; the real config for board #4 is committed here and memo's config committed in memo.
