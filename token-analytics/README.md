# token-analytics

Per-issue token & duration analytics: collector, static viewer, and GitHub board write-back (#26) — skeleton; see `docs/specs/2026-09-26-token-analytics-design.md`.

Implemented so far: source readers in `collector.py` (`read_host` — sqlite3 read-only URI + `PRAGMA busy_timeout=5000`; `read_container` — `docker exec <c> sqlite3 -readonly -json <db> .timeout 5000 <SQL>`, argv list only; both fail-open: warning + `None`, exit code unaffected); session→issue mapping + design/IMPL phase attribution (`attribute_project`, `extract_issue`, overrides, `group_by_root`, `phase_for_root`, `build_unmatched`); aggregation + snapshot writing — `aggregate(...)` builds per-issue snapshot dicts (5 token components + raw-sum total, active model time, per-phase calendar span, recursive drill-down tree with `T<N>` folding on IMPL-root children and agent-labeled design children, `by_model`/`by_agent` bars, board-ready `tokens.total_m` / `active.hours` values rounded 1 dp), `rebuild(...)` persists `data/issues/<project>-<N>.json` + `index.json` + `unmatched.json` + `titles.json` (gh cache, one bulk `gh issue list` per repo per run) atomically and byte-deterministically, drops stale issue files, creates `state.json` (write-back caches only); the `collect` subcommand (`collect.py` → `collector.run_collect`) wires readers → mapping → aggregation → snapshots → write-back hook (`writeback.run_after_rebuild`, no-op until Task 8) under an exclusive `flock` on `data/.lock`.

## Collect

One pass = a full rebuild of both sources plus the write-back hook:

    python3 collect.py collect                      # default: ./config.json
    python3 collect.py collect --config /path/to/config.json

The data dir is the `data/` sibling of the config file. The whole write phase runs under `flock` on `data/.lock`; a second run started while one is active logs «skipped: previous run still active» and exits 0. Warnings always go to stderr. Cron (15–30 min cadence is your choice) — the redirect lands them in `data/collect.log`:

    */15 * * * * cd <repo>/token-analytics && python3 collect.py collect >> data/collect.log 2>&1

Tests (stdlib `unittest`, offline — fixture DBs are generated into tmp dirs at test time):

    python3 -m unittest discover token-analytics/tests -v
