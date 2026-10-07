# token-analytics

Per-issue token & duration analytics: collector, static viewer, and GitHub board write-back (#26) — skeleton; see `docs/specs/2026-09-26-token-analytics-design.md`.

Implemented so far: source readers in `collector.py` (`read_host` — sqlite3 read-only URI + `PRAGMA busy_timeout=5000`; `read_container` — `docker exec <c> sqlite3 -readonly -json <db> .timeout 5000 <SQL>`, argv list only; both fail-open: warning + `None`, exit code unaffected); session→issue mapping + design/IMPL phase attribution (`attribute_project`, `extract_issue`, overrides, `group_by_root`, `phase_for_root`, `build_unmatched`); aggregation + snapshot writing — `aggregate(...)` builds per-issue snapshot dicts (5 token components + raw-sum total, active model time, per-phase calendar span, recursive drill-down tree with `T<N>` folding on IMPL-root children and agent-labeled design children, `by_model`/`by_agent` bars, board-ready `tokens.total_m` / `active.hours` values rounded 1 dp), `rebuild(...)` persists `data/issues/<project>-<N>.json` + `index.json` + `unmatched.json` + `titles.json` (gh cache, one bulk `gh issue list` per repo per run) atomically and byte-deterministically, drops stale issue files, creates `state.json` (write-back caches only).

Tests (stdlib `unittest`, offline — fixture DBs are generated into tmp dirs at test time):

    python3 -m unittest discover token-analytics/tests -v
