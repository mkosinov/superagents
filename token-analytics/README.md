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

- **`fields` (one run per project)**: creates the configured missing fields via `gh project field-create --data-type NUMBER` (idempotent — rerun creates nothing). An existing field name with a definitely non-NUMBER type (single-select, iteration) stops loudly naming the field, changing nothing. Never renames fields, never touches single-select options.
- **Diff-gate**: the last WRITTEN value per project+issue+field is cached in `data/state.json`; an unchanged (rounded) value is never re-written — rounding noise never hits the board. The cache updates only after a successful write.
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

Manual browser checklist (draft; final acceptance polish at Task 9):

- [ ] Open `127.0.0.1:8765` — project tabs (one per project, «Несопоставленные» last) + a source-availability line; the strongest project's tab opens first.
- [ ] Issue table sorted by token total desc; columns: title (with issue №), tokens human («12.4M» / «830K», raw total in the tooltip), active time human («1ч 24м»), last activity date, design/IMPL mini-split chips; a WIP row shows accrued totals and its real date — no invented completion status anywhere.
- [ ] A project with zero issues (tab exists via `index.json` `projects`) renders an explicit empty state.
- [ ] Click a row → issue page: phase cards (absent phase hidden, not zero-filled), 5 token components + total, active time, secondary line «календарно: 3 дня» / «календарно: 9 ч»; by-model and by-agent horizontal CSS bars (issue-level and per phase).
- [ ] Drill-down tree: expand/collapse at any depth; container-time nodes carry the «≈» mark and the tree shows «≈ сумма по параллельным дочерним сессиям» once; session nodes have a «Привязать» button (rebind path), T-fold nodes don't.
- [ ] «Несопоставленные» tab: table + «Привязать» per row → dialog (project prefilled when attributable, issue №, phase) → POST → the row moves into the issue; without the server running the dialog shows a plain failure message.
