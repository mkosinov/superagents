# token-analytics

Per-issue token & duration analytics: collector, static viewer, and GitHub board write-back (#26) — see `docs/specs/2026-09-26-token-analytics-design.md`.

Implemented so far: source readers in `collector.py` (`read_host` — sqlite3 read-only URI + `PRAGMA busy_timeout=5000`; `read_container` — `docker exec <c> sqlite3 -readonly -json <db> .timeout 5000 <SQL>`, argv list only; both fail-open: warning + `None`, exit code unaffected); session→issue mapping + design/IMPL phase attribution (`attribute_project`, `extract_issue`, overrides, `group_by_root`, `phase_for_root`, `build_unmatched`); aggregation + snapshot writing — `aggregate(...)` builds per-issue snapshot dicts (5 token components + raw-sum total, active model time, per-phase calendar span, recursive drill-down tree with `T<N>` folding on IMPL-root children and agent-labeled design children, `by_model`/`by_agent` bars, board-ready `tokens.total_m` / `active.hours` values rounded 1 dp), `rebuild(...)` persists `data/issues/<project>-<N>.json` + `index.json` + `unmatched.json` + `titles.json` (gh cache, one bulk `gh issue list` per repo per run) atomically and byte-deterministically, drops stale issue files, creates `state.json` (write-back caches only); the `collect` subcommand (`collect.py` → `collector.run_collect`) wires readers → mapping → aggregation → snapshots → write-back (`writeback.run_after_rebuild`) under an exclusive `flock` on `data/.lock`; the `serve` subcommand (`server.py`, Task 7) serves the viewer + snapshots + the bind API; board write-back + the `writeback`/`fields` subcommands (`writeback.py`, Task 8) push snapshot metrics to GitHub Projects boards via the managed gh CLI.

## Collect

One pass = a full rebuild of both sources plus the write-back hook:

    python3 collect.py collect                      # default: ./config.json
    python3 collect.py collect --config /path/to/config.json

The data dir is the `data/` sibling of the config file. The whole write phase runs under `flock` on `data/.lock`; a second run started while one is active logs «skipped: previous run still active» and exits 0. Warnings always go to stderr. Cron (15–30 min cadence is your choice) — the redirect lands them in `data/collect.log`:

    */15 * * * * cd <repo>/token-analytics && python3 collect.py collect >> data/collect.log 2>&1

Tests (stdlib `unittest`, offline — fixture DBs are generated into tmp dirs at test time):

    python3 -m unittest discover token-analytics/tests -v

## Board write-back

Every `collect` pass (and the serve bind rebuild) ends by pushing each issue's board-ready values (tokens in millions, hours — 1 decimal, verbatim from the snapshot: «48.2», «25.3») onto that project's own GitHub Projects board, for every project with `write_back.enabled: true` and a non-empty `fields` map (name → snapshot dot-path, binding by NAME). The managed gh CLI only — `gh project item-edit --id … --field-id … --project-id … --number …`, one item+field per call; never raw GraphQL, never field-definition mutations.

    python3 collect.py writeback                  # manual re-push from existing data/ snapshots
    python3 collect.py fields                     # one run per project after enabling write_back

- **`fields` (one run per project)**: creates the configured missing fields via `gh project field-create --data-type NUMBER` (idempotent — rerun creates nothing). An existing field name with a definitely non-NUMBER type (single-select, iteration) stops loudly naming the field, changing nothing. Never renames fields, never touches single-select options. Validate the result (and see created vs pre-existing) with `gh project field-list <N> --owner <owner> --format json` — the 6 canonical fields must all be `ProjectV2Field` with NUMBER semantics (gh reports the base type for numeric fields).
- **Enabling memo (or any project) later**: flip `write_back.enabled` to `true` in `config.json`, run `python3 collect.py fields` once for that project's board — nothing else. The 6 canonical name→dot-path lines already ship in the config; disabling again is just the flip back (the stage skips, board values stay as last written).
- **Constants sync (until #23)**: the superagents `board` block (`owner`/`project_number`/`project_id`) duplicates the constants at the top of `.zcode/scripts/gh_board.py` (`OWNER`/`REPO`/`PROJECT_ID` — same values, kept in sync by hand, two lines). If you edit either side, check the other; the duplication goes away with #23's parameterization.
- **Diff-gate**: the last WRITTEN value per project+issue+field is cached in `data/state.json`; an unchanged (rounded) value is never re-written — rounding noise never hits the board. The cache updates only after a successful write. A corrupt cache entry (state.json is hand-editable) resets with a warning instead of crashing the run, and entries for issues whose snapshots no longer exist are pruned after each pass — the cache never grows forever.
- **Item/field ids**: resolved per run via `gh project item-list`/`field-list` with an explicit `--limit` and a drain loop until exhausted (the CLI's default 30 silently truncates); item ids cached in `state.json`, and a failed write drops the cached id (a re-added card gets a new one — re-resolved next run). An unknown field name warns with a «run `collect.py fields`» hint and skips only that field.
- **Fail-open everywhere**: a gh/network failure logs a warning and the run still exits 0; an issue not on its project's board is skipped with a note; WIP and closed issues are written alike (no status filtering). `write_back.enabled: false` skips the whole stage; an empty `fields` map is a documented no-op with a log note.
- `collect.py writeback` takes the same `flock` as `collect` (a busy lock skips, exit 0).

## Serve

    python3 collect.py serve                       # 127.0.0.1:8765 from the config `serve` block
    python3 collect.py serve --config /path/to/config.json

`server.py` runs a threaded stdlib HTTP server on the configured loopback address (default `127.0.0.1:8765`; the data dir is the config's sibling `data/`, same as `collect`):

- `GET /` — `viewer/index.html`; `/app.js`, `/lib.js`, `/style.css` — the viewer whitelist (nothing else under `viewer/` is served).
- `GET /data/<path>.json` — snapshot files (`index.json`, `unmatched.json`, `issues/<project>-<N>.json`, …) straight from the data dir; `.json` only, path traversal and symlink escapes rejected, no directory listing.
- `POST /api/bind` — `{session_id, project, issue, phase}`: binds a session to an issue. Any session id from the last snapshot set works — root or child (resolved to its root), matched or unmatched (rebinding a wrong auto-match is the normal fix path). Issue must exist (a snapshot or `gh issue view -R` confirms — typos get a 400, not phantom snapshots). The override is written atomically to `data/overrides.json` keyed by root session id, then the same full rebuild as `collect` runs in-process under `data/.lock` (~10 s wait, then 503 «сбор идёт, повтори»). Reply: `{"ok": true, "redirect": "/#/<project>/<N>", …}`; the viewer reloads and opens the issue page.

Guards, always on: `Host` must be the bound `127.0.0.1:8765`/`localhost:8765` (DNS-rebinding), a POST with a non-loopback non-null `Origin` is rejected (CSRF), POST accepts only `Content-Type: application/json`. The single POST endpoint writes exactly one file itself — `overrides.json`. Handler threads carry a 30 s socket timeout (a stalled client frees its worker); a 500 replies «внутренняя ошибка сервера» with the details warned to the server console; an oversized body gets a 413 and the connection closes; a second `collect serve` on a busy port exits 1 with a one-line «порт … занят» error instead of a traceback.

## Viewer

Static dashboard in `viewer/` (`index.html` + `lib.js` + `app.js` + `style.css`; vanilla, no build step, no external references), served at the root by `collect serve` — it fetches `/data/index.json`, `/data/unmatched.json`, `/data/issues/<project>-<N>.json` and posts binds to `/api/bind`. Pure formatting/navigation helpers live in `lib.js` (DOM-free, CommonJS export guard) and are unit-tested under `node` in `tests/test_viewer.py`.

Manual browser checklist — one line per spec User Scenario (`python3 collect.py serve`, open `http://127.0.0.1:8765`):

- [ ] **1 Dashboard overview** — project tabs (one per project, «Несопоставленные» last) + a source-availability line, strongest project first; issue table sorted by token total desc (title with issue №, tokens human «12.4M»/«830K» + raw total in the tooltip, active time human «1ч 24м», last activity date, design/IMPL mini-split chips); a WIP row shows accrued totals and its real date; a zero-issue project renders an explicit empty state; no invented completion status anywhere.
- [ ] **2 Issue page** — click a row → design/IMPL phase cards (absent phase hidden, not zero-filled) with the 5 token components + total, active model time, secondary line «календарно: 3 дня» / «календарно: 9 ч»; by-model and by-agent horizontal CSS bars (issue-level and per phase).
- [ ] **3 Design drill-down** — expand design → root → gate nodes (scout, each panelist, plan-reviewer), each with agent, tokens, time.
- [ ] **4 IMPL drill-down** — expand IMPL → marathon root → `T1…Tn` folded nodes aggregating their sub-sessions (nested levels included) + standalone unlabeled children; expand/collapse at any depth; container-time nodes carry the «≈» mark with the single «≈ сумма по параллельным дочерним сессиям» note; session nodes have a «Привязать» button (rebind path), T-fold nodes don't.
- [ ] **5 Bind a session** — «Несопоставленные» tab: table + «Привязать» per row → dialog (project prefilled when attributable, issue №, phase) → POST → the row moves into the issue and leaves the tab; a wrongly auto-matched session is rebound the same way from its issue page; without the server running the dialog shows a plain failure message.
- [ ] **6 Board write-back** — after a collect, the issue's card on its project board (web UI) shows the 6 numeric fields (tokens in millions, hours — 1 dp, e.g. «48.2»); only changed values are written; WIP and closed cards alike.

## Live acceptance runbook (one-time per project)

Real calls against the real board — run from `token-analytics/`, `gh` must be authenticated with the `project` scope. Memo board #3 stays disabled until its config flip (see `fields` above).

1. **Create the fields** (idempotent; validate + record created vs pre-existing):

        python3 collect.py fields
        gh project field-list 4 --owner mkosinov --format json     # 6 canonical fields present

2. **Real collect** — full rebuild of both sources + the write-back hook:

        python3 collect.py collect

   Expect `data/index.json`, `data/issues/<project>-<N>.json`, `data/unmatched.json` refreshed with plausible numbers. A source that can't be read (DB missing, `docker exec` unavailable) warns and is skipped — the run still exits 0 (fail-open by design); record the exact warning.

3. **Real write-back / diff-gate proof** — a rerun writes nothing (all values cached unchanged):

        python3 collect.py writeback

   Read back what landed on cards (fields per item):

        gh project item-list 4 --owner mkosinov --format json

4. **Browser pass** — `python3 collect.py serve`, walk the checklist above; open the board in the GitHub web UI and confirm the 6 values on a card. Record: created fields, collect warnings, cards written, 2–3 sample values, deviations.

## IMPL wrap-up (2026-10-07, #26)

**Shipped:** collector (dual-source read, mapping, phase attribution, aggregation, snapshots) + static viewer + board write-back, per `docs/specs/2026-09-26-token-analytics-design.md`. All 9 plan tasks DONE, two-stage reviews passed, quality findings fixed.

**Tests:** 186 pass / 0 fail / 1 skip (`python3 -m unittest discover token-analytics/tests`; the golden test skips by design when the golden file is absent).

**Live acceptance (real data, container DB):** 6 canonical NUMBER fields created on board #4 via managed `gh project field-create` (idempotent rerun verified); real collect + diff-gated write-back — card #26 got 6/6 values (tokens 35.4 / design 35.2 / IMPL 0.2; hours 261.7 / 261.7 / 0), card #24 4/6 (impl phase legitimately absent — skipped by design); rerun wrote nothing (diff-gate proven). Host DB absent in this container → source failed open per design (warning, exit 0). Visual gate: PASS after one fix round (proportional bars, table scroll containers).

**Known deviations/notes:**
1. gh CLI exposes no list cursor → pagination drains via explicit `--limit` growth (verified vs gh 2.100.0).
2. `field-list` JSON cannot distinguish NUMBER/TEXT → the loud non-NUMBER stop covers single-select/iteration only; a TEXT clash degrades fail-open (documented above and in code).
3. Viewer gained two architect-acked additive snapshot fields (`approx` on tree nodes, `projects` in index.json).
4. Title-mode phase heuristic misses «#N IMPL …» root titles — the designed fix path (overrides/bind) was used and works; follow-up candidate.

**Deliberate follow-ups (Non-Goals per spec):** memo board #3 enablement (config flip + one `fields` run); timelines/latency/retries; token-economy.md refresh; #23 skill rewrite must name `writeback.py` as the second board writer.
