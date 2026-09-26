# Token Analytics Implementation Plan (issue #26)

**Spec:** `docs/specs/2026-09-26-token-analytics-design.md` (G1a + G1b approved, panel fixes folded, two post-panel design revisions: full rebuild per run; per-project board config)
**Date:** 2026-09-26
**Port source:** none — all code is new; the spec's Reuse section names the in-repo patterns to mirror.
**Post-G2 amendment (user OK 2026-09-26):** fields are created by a `collect.py fields` subcommand (managed `gh project field-create`, NUMBER only) and the config binds by field NAME — replaces the originally approved «manual web-UI creation + empty shipped fields map»; folded into Tasks 1/8/9, spec Design revision 3.

## Goal

Build the per-issue token & duration analytics app exactly as specified: a Python-stdlib collector that fully rebuilds per-issue JSON snapshots from the zcode host DB and the opencode container DB on every run, a static vanilla-JS viewer served on 127.0.0.1:8765 with a binding endpoint, and a diff-gated board write-back of 6 numeric fields per project's board via managed `gh project item-edit` only.

## Architecture

```
~/.zcode/cli/db/db.sqlite ──┐
                            ├→ collector.py (SELECT-only, parameterized SQL, busy_timeout,
opencode.db via docker exec ┘   fail-open per source; FULL rebuild every run)
        ↓ mapping: directory→project, root-title ordered regex, overrides.json (wins)
        ↓ aggregation: recursive parent_id tree (subtree aggregates), phase modes
        ↓               (split/title), T-folding, by-model/by-agent, board-ready rounding
   data/ (GITIGNORED) ←─ issues/<project>-<N>.json · index.json · unmatched.json
        ↑ GET /data/*.json                overrides.json ←── POST /api/bind (validated)
        |                                         └→ in-process rebuild under data/.lock
   server.py (ThreadingHTTPServer, 127.0.0.1:8765, Host/Origin/Content-Type guards)
        └→ viewer/ static (index.html + app.js + style.css, no libs, no build)
   after every rebuild → writeback.py → gh project item-edit → board #4 (memo #3 later)
   cron */15 → collect.py collect (flock .lock, log to data/collect.log)
```

## Tech Stack

Python 3 stdlib only (`sqlite3`, `subprocess`, `http.server`, `json`, `pathlib`, `fcntl`, `argparse`; tests = stdlib `unittest`, E2E driver = `urllib.request`) — no new dependencies, matching the `gh_board.py` precedent. `gh` CLI for all GitHub access (titles, item-list, item-edit). Viewer = vanilla HTML/JS/CSS, zero external references, no build step. Tests run offline against synthetic fixture DBs; live gh/docker paths are stubbed in tests and exercised once at live acceptance.

## Behavioral Delta

- Opening `http://localhost:8765` shows where tokens go per feature — issue list per project sorted by spend, with in-progress issues showing accrued totals and real last-activity dates — replacing hand audits and the stale token-economy estimates.
- An issue page splits design/IMPL: 5 token components + total, active model time (exact on host, «≈» on container), secondary calendar span; by-model and by-agent bars; expandable drill-down into design gates (scout/panelists/plan-reviewer) and IMPL tasks folded by T-label — nested sub-sessions never lose spend.
- Unmatched sessions are visible in a global dashboard tab and bindable by button (project + issue + phase); wrongly auto-matched sessions are rebound the same way; unbinding = removing a line by hand, effective next run.
- Board cards carry 6 auto-updated numeric fields (tokens total/design/impl in millions, hours total/design/impl); the fields themselves are created by one idempotent `collect.py fields` run — superagents #4 immediately, memo #3 after a config flip + the same run. No manual web-UI step.
- Collection runs unattended every 15 min: container down, gh down, or a busy database degrades to a warning — snapshots and exit code survive; nothing ever writes to the source DBs.

---

## Task 1: Skeleton, config, gitignore

### Classification: trivial

Create `token-analytics/` with stub modules (`collect.py`, `collector.py`, `writeback.py`, `server.py` — module docstring + empty functions), the CLI skeleton in `collect.py` (argparse, subcommands `collect` / `serve` / `writeback`, each stubbed to a «not implemented» exit), `config.json` exactly per spec §Config file: the 6 canonical field-NAME→dot-path pairs ship from day one for both projects (superagents `enabled: true`, memo `enabled: false` — binding by name per the post-G2 amendment; no field ids in git at all). Add `token-analytics/data/` to `.gitignore`. Create `data/` with a `.gitkeep`-free layout (dir created at runtime; gitignore covers it either way) and a README stub (title + one line).

Consume spec Reuse: `gh_board.py` constants-at-top convention for the config's board block.

### Required Docs
- Spec §Directory layout; §Config file.

### DoD
- `python3 token-analytics/collect.py --help` lists the three subcommands; stubs exit cleanly with «not implemented».
- `git check-ignore token-analytics/data/x` succeeds; `git status` clean.
- `config.json` validates against the spec's shape (projects, sources, serve block) and carries the 6 name→dot-path pairs per project.

---

## Task 2: Fixture generators + source readers

### Classification: standard

`tests/fixtures.py`: generator functions building synthetic DBs of BOTH schemas into tmp dirs — host-style (`session` with parent_id/directory/title/time_created/time_updated, `turn_usage` with duration_ms + 5 token kinds incl. errored rows, `model_usage` with session_id/turn_id/model_id/agent + tokens) and container-style (`session` with agent/model JSON/tokens_*/times). Generators parameterize: roots vs children vs grandchildren, marathon root with T-labeled children, parallel overlapping child spans, childless roots, unattributed directories.

`collector.py`: `read_host(db_path)` (sqlite3 connect read-only URI + `PRAGMA busy_timeout=5000`) and `read_container(container, db_path)` (`docker exec <container> sqlite3 -readonly <db> .timeout 5000 …`), argv lists only, **parameter placeholders only** — no f-string/format SQL anywhere. Both return full session sets (ALL directories — filtering is mapping's job, spec §Mapping step 1) plus host turn/model rows. Fail-open: any open/read failure (missing file, docker error, busy beyond timeout) → warning line + `None`; the caller skips that source; exit code unaffected.

Consume spec Reuse: `docker exec … sqlite3 -readonly` command surface (recon-verified); epoch-ms timestamps (verified same units).

### Required Docs
- Spec §Sources and access; §Snapshots (fixtures live under `tests/`, generated).

### DoD
- Unit: fixture DBs read back exact rows (counts + spot fields), grandparents included.
- Unit: fail-open — nonexistent host path and failing container invocation (fake container name) → warning + `None`, pipeline exit 0.
- Unit: reader connections are read-only (a write attempt through them raises).
- Static check: no `shell=True`, no non-parameterized SQL in `collector.py` (grep-asserted in the test).

---

## Task 3: Mapping and phase attribution

### Classification: standard

`collector.py`: `attribute_project(directory, config)` (ordered prefix match; `None` → «—»), root detection (`parent_id IS NULL` per source), `extract_issue(title)` — the spec's ordered pattern set (`#(\d{1,4})` anywhere → `^(\d{1,4})\b` leading bare → `(?:issue|тикет|задач[аи]|дизайн)\s+(\d{1,4})\b`), first match wins; overrides load/save (`data/overrides.json`, entries `{session_id: {project, issue, phase}}`, override beats every heuristic and carries the project for unattributed directories); `phase_for_root(...)` — `split` mode (source decides) vs `title` mode (root title starts with `IMPL`, case-insensitive → impl, else design), override forces either; unmatched row builder (project-or-«—», date, directory, title, tokens, session id; sorted by tokens desc).

### Required Docs
- Spec §Session → issue mapping; §Phase attribution.

### DoD
- Unit: each pattern hits its class of titles («Разведка issue #327», «IMPL #324 delete family», «327 каскад удаления», «дизайн 26 тикета»); multi-number title → leftmost wins; no match → unmatched.
- Unit: `split` and `title` modes classify correctly; phase override wins in both.
- Unit: override with explicit project binds a session from an unattributed directory.
- Unit: unmatched export sorted by tokens desc, project «—» for unknown directories.

---

## Task 4: Aggregation and snapshot writing

### Classification: large

`collector.py`: the rebuild core — `aggregate(...) → per-issue snapshot dicts`:

1. **Tokens**: host = SUM over `turn_usage` (5 kinds, all rows incl. errored/cancelled); container = `session.tokens_*`; total = plain raw sum. Root-wrapper rule: container marathon roots' tokens count.
2. **Active time**: host = SUM(`turn_usage.duration_ms`) per session (roots and children); container = child-session spans (`time_updated − time_created`), root wrappers excluded, **childless roots count their own span**.
3. **Calendar span**: per phase `max(end) − min(start)`; hours granularity below a day («календарно: 9 ч»).
4. **Tree**: recursive `parent_id` walk, any depth; node = subtree aggregate (own + descendants); T-folding on IMPL-root children (`^T(\d+)[:. ]` → one `T<N>` node aggregating its sub-sessions); design children labeled by agent attribution (raw agent string kept when unrecognized); issue totals reconcile with node sums by construction.
5. **Aggregates**: `by_model`/`by_agent` per issue and phase — host from `model_usage` (join by `session_id`), container from session-level model/agent.
6. **Board-ready values**: `tokens.total_m`, `phases.{design,impl}.tokens.total_m`, `active.hours`, `phases.{design,impl}.active.hours` — millions/hours rounded to 1 dp at snapshot build; raw values kept alongside.

Snapshot writing: `issues/<project>-<N>.json` + `index.json` + `unmatched.json`, all atomic (tmp + `os.replace`), sorted keys → **byte-identical output for identical input** (determinism). Issues with zero mapped sessions after a rebuild: snapshot file and index entry removed. Titles: one bulk `gh issue list` per repo per run (argv call), `titles.json` as offline cache/fallback («issue #N»; closed issues keep the last known title). `state.json` created here (write-back caches only — no watermarks).

Consume spec Reuse: agent-value vocabularies (host `zcode-*`, container memo agents) for labels.

### Required Docs
- Spec §Token accounting; §Active model time and calendar span; §Drill-down tree; §By-model and by-agent aggregates; §Snapshots and state.

### DoD
- Unit: token math — 5 components, raw-sum total, board rounding («48.2», «25.3»).
- Unit: recursive aggregation — a grandchild's tokens/time fold into its parent node's subtree total; issue total = sum over roots.
- Unit: T-folding — `T1: a`, `T1: b`, `Fix …` → one `T1` node + one standalone node.
- Unit: root-wrapper asymmetry — wrapper tokens counted, wrapper time not; childless root counts its own span.
- Unit: determinism — two rebuilds over the same fixture → byte-identical snapshot files.
- Unit: stale removal — an issue whose sessions vanish loses its file and index entry.
- Unit: atomic write — simulated failure mid-write leaves the previous file intact.
- Unit: titles — gh failure → fallback; closed issue retains last known title.
- Golden check (spec §Testing) is written HERE: a golden test for real superagents #16 (host-only) — regenerates the golden file on demand (documented one-liner against the live host DB), asserts the snapshot shape/values against it, and **skips cleanly when `data/golden-…` is absent** (personal numbers stay out of git).

---

## Task 5: CLI `collect` + lock

### Classification: small

`collect.py collect`: wire readers → mapping → aggregation → snapshots → write-back hook (Task 8; no-op stub until then). `fcntl.flock` on `data/.lock` for the whole write phase; a second run finding the lock held logs «skipped: previous run still active» and exits 0. Warnings always to stderr; under cron they land in `data/collect.log` (redirect in the README cron line). Per-source availability recorded in `index.json`.

### Required Docs
- Spec §Collection runs.

### DoD
- Unit: full pipeline over fixture DBs via a fixture config produces the expected snapshot set (golden shape: projects, issues, phases).
- Unit: lock held by another process → skip message + exit 0.
- Unit: one source failing → other source's issues still rebuilt, exit 0.

---

## Task 6: Viewer static files

### Classification: large

`viewer/index.html` + `app.js` + `style.css` per spec §Viewer, mirroring the canon `site/` pattern (static, no build, no external references — grep-asserted): project tabs + the **global** «Несопоставленные» tab; issue table sorted by token total (title, tokens human «12.4M»/«830K», active time human «1ч 24м», last activity local, design/IMPL mini-split; WIP rows show accrued totals and the real date — no invented completion status; empty project → explicit empty state); issue page — phase rows (5 components + total, active time, «календарно: …» secondary line; absent phase hidden, not zero-filled), by-model/by-agent horizontal CSS bars, recursive expand/collapse drill-down with container-time «≈ сумма по параллельным дочерним сессиям» labels; «Привязать» button on unmatched rows (dialog: project prefilled from directory when attributable, issue №, phase) and on issue-page session nodes (rebind path). All rendering fetches `/data/*.json`.

Consume spec Reuse: `site/` static-site structure (sections/nav idioms; data via fetched JSON instead of baked JS).

### Required Docs
- Spec §Viewer (all three views + units).

### DoD
- Files served with correct content-types by Task 7's server; zero external references (`grep -E 'https?://|cdn' viewer/` empty).
- Manual browser checklist entry drafted (final polish happens at Task 9 acceptance).

---

## Task 7: Server (`collect serve`) + bind endpoint

### Classification: standard

`server.py`: `ThreadingHTTPServer` bound to `127.0.0.1:8765` (config `serve` block). Routes: `viewer/` static, `data/*.json` (GET), `POST /api/bind`. **Guards (always on):** request `Host` must be `127.0.0.1:8765` or `localhost:8765` (DNS-rebinding); POST with a non-loopback non-null `Origin` → rejected; POST `Content-Type` must be `application/json`. **Bind:** `{session_id, project, issue, phase}` — session must exist in the last snapshot set (matched or unmatched: rebinding is the fix path for wrong auto-matches), project/phase enums, issue must exist (has a snapshot or `gh issue view` succeeds; typos → 400, no phantom snapshots); appends `overrides.json` atomically, runs the in-process full rebuild **under the same `data/.lock`** (try ~10 s → 503 «сбор идёт, повтори»), responds with the issue page path. No path parameters; the endpoint writes exactly one file. `collect.py serve` wiring.

### Required Docs
- Spec §Viewer (server block); §Safety & privacy.

### DoD
- E2E test for scenario 1 passes (RED-GREEN-REFACTOR): fixture-populated `data/` + serve on an ephemeral port → index JSON/table data sorted, WIP row carries accrued totals and real date.
- E2E test for scenario 2 passes (RED-GREEN-REFACTOR): issue snapshot exposes both phases with the full field set (components, active, calendar) and aggregates.
- E2E test for scenario 3 passes (RED-GREEN-REFACTOR): design tree children present with agent attribution.
- E2E test for scenario 4 passes (RED-GREEN-REFACTOR): T-folded node + standalone node; grandchild inside its parent's subtree total.
- E2E test for scenario 5 passes (RED-GREEN-REFACTOR): bind POST on an unmatched AND on an already-matched session → override written/replaced, snapshot includes the session, `unmatched.json` drops it.
- Unit: guards — wrong `Host` rejected; cross-origin POST rejected; wrong `Content-Type` → 415; unknown session/issue → 400; lock busy → 503.

---

## Task 8: Board write-back

### Classification: standard

`writeback.py`: runs after every rebuild (called from `collect` and from the bind rebuild) and standalone via `collect.py writeback` (manual re-push from existing snapshots). Per project with `write_back.enabled` and non-empty `fields`: resolve issue→item-id via `gh project item-list` AND field NAME→id via `gh project field-list` — both with an **explicit `--limit` and a pagination loop until exhausted** (CLI default 30 truncates; canon rule from #24), cached in `state.json` (a write failure drops the item's cached id — a re-added card gets a new one); an unknown field name → warning + that field skipped with a «run `fields`» hint; diff-gate against the last-written cache (compares the written rounded values — rounding noise never writes); write each changed field via `gh project item-edit --id … --field-id … --project-id … --number …` (argv list, one item+field per call).

`collect.py fields` (post-G2 amendment): per enabled project — read fields via `gh project field-list`, create the missing ones from the config's 6 canonical names via `gh project field-create --data-type NUMBER` (one call per field, idempotent); an existing name with a non-NUMBER type → loud stop naming the field, zero mutations. Never renames or modifies existing fields, never touches single-select options. Fail-open: gh/network failure → warning, continue, exit 0; write failure drops that item's cached id (a re-added card gets a new one); issue not on the board → skip with a note. No status filtering (WIP and closed written alike). Empty `fields` → no-op with a log note. **Never** raw GraphQL, **never** field-definition mutations.

Consume spec Reuse: `gh_board.py` `gql()` subprocess+error pattern; recon-verified `item-edit`/`field-list`/`item-list` flags; #24 spec pagination rule.

### Required Docs
- Spec §Board write-back; §Config file.

### DoD
- E2E test for scenario 6 passes (RED-GREEN-REFACTOR, stubbed gh): diff-gate writes only changed fields; a gh failure logs a warning and the run still exits 0; disabled project and empty fields → no calls.
- Unit: dot-path resolver — all 6 canonical paths resolve against a fixture snapshot; an unknown path fails loudly (no silent None written).
- Unit: pagination loop drains a stub returning multiple pages (>30 items total).
- Unit: `fields` — missing name → created (stubbed `field-create`), rerun creates nothing, existing non-NUMBER name stops loudly with zero mutations.
- Unit: unknown field name in write-back → warning + that field skipped only; name→id resolution served by the paginated field-list stub.
- Unit: cached item id dropped on write failure, re-resolved next run.
- Unit: values written verbatim from board-ready snapshot fields («48.2», «25.3»).

---

## Task 9: README + live acceptance

### Classification: small

Complete `token-analytics/README.md`: the cron line (verbatim, with log redirect); field setup = one `python3 collect.py fields` run per enabled project (idempotent; memo enablement = config flip + the same run); `collect serve` usage; the manual browser checklist (one line per User Scenario); the live-acceptance runbook — real `fields` run, real `collect` + `writeback`, browser pass; the constants-sync note (board block duplicates `gh_board.py` constants until #23's parameterization — check on edit). Then execute live acceptance (the user's part is verification only): the session runs `fields` for real on board #4 (creates/validates the 6 NUMBER fields via managed CLI), then a real collect + writeback; the user opens the board in the web UI and confirms the 6 values on a card; results go into the wrap-up report. Memo board #3 stays disabled (enablement = config flip + one `fields` run).

### Required Docs
- Spec §Board write-back (field creation, kill switch); §Testing (live acceptance).

### DoD
- README covers all of the above with copy-pasteable commands.
- Live acceptance executed: `fields` created/validated the 6 NUMBER fields on board #4 (managed CLI, zero manual web-UI steps); a real write-back verified on at least one card with the user; outcome recorded in the wrap-up report.

---

## Finish

DoD for the whole plan mirrors the spec's Testing section: all unit + E2E suites green locally (`python3 -m unittest discover token-analytics/tests`), the golden check passes locally when present (skips otherwise), live acceptance recorded. The wrap-up report states: files created, test summary, live-acceptance results, and the deliberate follow-ups (memo board enablement, deferred timelines/latency/retries, token-economy.md refresh — all Non-Goals; plus #23's skill rewrite must name `writeback.py` as the recorded second board writer — spec §Relation). The wrap-up also records the post-G2 amendment as shipped: `fields` subcommand + binding by field name — no manual web-UI field step.
