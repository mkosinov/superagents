# Token Analytics: per-issue token & duration spend — Design (issue #26)

**Date:** 2026-09-26
**Status:** G1a approved 2026-09-26 (concept, incl. durations scope extension and board write-back); G1b panel reviewed 2026-09-26 (6/6 reports: 1 NEEDS_REVISION, 5 SOUND_WITH_CONCERNS, no blockers), all findings folded + two user decisions taken the same day (full rebuild per run instead of incremental watermarks; per-project board config) — G1b approved 2026-09-26; plan G2 approved 2026-09-26 (docs/plans/2026-09-26-token-analytics-plan.md); amended post-G2 same day (user OK): managed field creation + name binding — Design revision 3
**Author:** host design session (brainstorm 2026-09-26 + recon 2026-09-26 + panel 2026-09-26)

**Placement:** a new `token-analytics/` directory at the superagents repo root. This is a host-side personal tool, not an agent-harness artifact — the `.zcode`/`.opencode` twins convention does **not** apply to it. Personal metrics (`token-analytics/data/`) never land in git (`.gitignore` addition is part of this scope). The memo port is a separate follow-up after обкатка (usual reuse-check pipeline).

---

## Summary

An app that answers «where do my tokens go» per feature. A **collector** (Python stdlib, runs on the host) reads two session databases — the zcode host DB (DESIGN sessions) and the opencode container DB (IMPL sessions) — maps sessions to issue numbers, aggregates tokens and active model time per issue/phase/gate/task, and writes per-issue **JSON snapshots** into a gitignored `data/` dir. Every run re-reads both DBs in full and rebuilds all snapshots (a full read is seconds; see Design revision 1). A **static viewer** (`collect serve`, localhost:8765, vanilla JS, no chart libs, no build step) renders: issue list per project → issue page with phase split, by-model and by-agent charts, drill-down into design gates and IMPL tasks. A **board write-back** pushes 6 numeric fields per issue (tokens total/design/impl + hours total/design/impl) to **that project's own board** (superagents #4; memo #3, disabled until enabled) via managed gh CLI commands only — `item-edit` for values, one-time field creation by the `fields` subcommand (Design revision 3).

Approach A (JSON snapshots + static site) — chosen at G1a over B (server + its own analytics DB) and C (self-contained HTML).

**Design revisions (post-panel, user decisions 2026-09-26):**
1. **Full rebuild per run replaces incremental watermarks.** The panel verified a hole in the watermark scheme — 886 of 927 host sessions finish turns AFTER their `session.time_updated` advances (lag up to 9 s), so a `time_updated`-keyed increment permanently misses final turns. A full re-read of both DBs takes seconds (verified), so the incremental machinery (watermarks, `--full`, affected-issue logic) is removed entirely; the G1a-approved periodicity (cron ~15 min) is unchanged. Side benefits: deleted sessions and hand-removed overrides heal on the next run by construction.
2. **Per-project board config.** The G1a phrase «6 numeric fields per project» is now structural: each project in the config carries its own `board` + `write_back` block. Memo write-back ships disabled (`enabled: false`) until the user creates its 6 fields by hand on board #3 — enabling is a config edit, no code.
3. **Managed field creation + name binding (post-G2 amendment, user OK 2026-09-26).** Replaces the G1a decision «fields created once, manually, in the web UI; config ships an empty fields map» with: a `fields` subcommand creates missing NUMBER fields via the managed `gh project field-create`, and the config binds by field NAME with the 6 canonical lines shipped from day one — no user-side chore. Rationale: the 2026-09-09 wipe came from a single-select **option-list replacement** mutation; `field-create` only ADDS a new field and replaces nothing (a NUMBER field has no option list at all), so the dangerous path does not exist for it. Memo enabling = config flip + one `fields` run.

## Goals

- Per-issue token accounting across the host/container split: 5 token components (input, output, reasoning, cache read, cache write) at every level (issue → phase → gate/task → session).
- Active model time next to tokens everywhere: **exact** on the host (per-turn `duration_ms`), **approximated** in the container (child-session spans — per-turn timing does not exist there, verified in recon).
- Periodic collection (~15 min cron) with a **full rebuild every run**, in-progress issues included, real last-activity dates.
- A binding UI for unmatched sessions (global dashboard tab → button → project + issue + phase → rebuild).
- Board write-back: 6 numeric fields per project's board, diff-gated, fail-open, configurable field→value binding.

## Non-Goals (deliberately NOT built)

- **Money / price overlay.** Price tables rot, free pools have no price. The 5 raw token components are the metric; an overlay can be added later without rebuild.
- **«Outside issues» spend.** Only issue-mapped sessions are counted. Consequence accepted knowingly at G1a (twice): sums will NOT reconcile with total account spend. Do not re-propose this bucket.
- **Timelines / latency / retry analytics.** Deferred at G1a («интересно, но отложим»); raw `turn_usage` data stays in the source DBs, so adding them later needs no backfill.
- **Per-task calendar spans.** Calendar span lives on issue-page phase rows only; per-task spans are gap-polluted (the #247 marathon trap — multi-hour tool runs inside a task).
- **Writes to source DBs.** Both databases are read SELECT-only.
- **Incremental collection machinery** (watermarks, affected-issue recomputation, `--full` drift healing) — removed by Design revision 1; the full rebuild made it dead weight.
- **Approach B** (analytics server with its own DB) and **approach C** (one self-contained HTML) — rejected at G1a.
- **Hooks into board canon or agent discipline** (on-completion collection hooks etc.) — collection is periodic from outside, the agent workflow is untouched.
- **Runtime dependency on #24's `board_config.json`.** It is designed but not landed; this tool's config is self-contained (see Relation).
- **Rewriting `docs/architecture/token-economy.md`.** It is stale (v3.5-era, no @manager/gates); per-issue accounting supersedes its estimates. Refreshing that doc is a separate small task.
- **The memo port** — follow-up after обкатка.
- **Auto-installed cron.** The crontab line is documented; the user installs it (agents never touch the user's crontab).
- **New CI workflow.** Canon CI deploys the site only; tests here run locally, offline, on fixtures (see Testing).

## Recon closures (assumptions → verified facts, 2026-09-26; scout + panel probes)

| Claim / assumption | Verified |
|---|---|
| Host DB has per-turn timing | **Better than assumed**: `turn_usage.duration_ms` AND `model_usage.duration_ms` (per model call, with `agent` attribution: `zcode-Explore`, `zcode-spec-panel-*`, `zcode-plan-reviewer`, …). Host active time is exact. |
| Container DB has no per-turn timing | **Confirmed**: `message`/`part` carry only `time_created`/`time_updated`; assistant JSON has `time.created` only. Child-session-span approximation stands. |
| Root titles carry issue numbers | **Partially**: of 198 host roots, 7 match `#26`, 80 match `IMPL`. An ordered tolerant pattern set + overrides is required (see Mapping). |
| Watermark on `session.time_updated` is sound | **REFUTED by the panel**: 886/927 host sessions have `turn_usage.completed_at` AFTER `session.time_updated` (avg 98 ms, max 9 s) — incremental collection keyed on it silently loses final turns. Resolved by Design revision 1 (full rebuild). |
| Tree is two levels (root → children) | **Refuted**: 1227 roots / 4638 children / 2175 grandchildren in the container DB. The tree is walked recursively; node totals are subtree aggregates (see Drill-down). |
| `gh project item-edit` can write a number | **Confirmed**: `gh project item-edit --id <item> --field-id <field> --project-id <proj> --number <float>` (one field per call; `--clear` exists). `item-list` defaults to `--limit 30` — explicit pagination required (see Board write-back). |
| Container read path | `docker exec opencode sqlite3 -readonly /root/.local/share/opencode/opencode.db` works; `/root/workspace/memo` holds 4272 of 5859 sessions (the other 1587 live in other directories — see Mapping step 1). |
| Timestamp units | **Confirmed identical**: both DBs store UTC epoch milliseconds; durations in ms. No normalization layer needed. |
| Container `cost` column | Dead in practice (0.0 via omniroute) — ignored; tokens are the signal. |
| Marathon root wrappers | Root tokens are the wrapper's own spend, child sums exceed them (probe: 398K root vs 482K children) — no double-count in the asymmetric rule below. |

## Concepts

### Directory layout

    token-analytics/
      collect.py        # CLI entry: collect / serve / writeback
      collector.py      # source readers, mapping, aggregation, snapshot writing
      writeback.py      # board write-back via managed gh CLI
      server.py         # `collect serve`: static viewer + JSON + POST /api/bind
      config.json       # committed; no secrets (paths, ids, field bindings)
      README.md         # setup: cron line, field creation (web UI), run serve
      viewer/           # index.html + app.js + style.css (static, no build)
      tests/            # stdlib unittest; synthetic fixture DBs (generated)
      data/             # GITIGNORED: snapshots, state, overrides, logs

### Sources and access

- **Host**: `~/.zcode/cli/db/db.sqlite`. `session` (id, project_id, parent_id, directory, title, time_created, time_updated, task_type, …); `turn_usage` (per turn: session_id, turn_id, status, duration_ms, 5 token kinds, retry/tool/error counts); `model_usage` (per model call: session_id, turn_id, provider_id, model_id, agent, 5 token kinds, duration_ms). No tokens on the session row — host totals are summed from `turn_usage`; by-model/by-agent join via `model_usage.session_id`.
- **Container**: `docker exec opencode sqlite3 -readonly /root/.local/share/opencode/opencode.db`. `session` carries agent, model (JSON id), tokens_input/output/reasoning/cache_read/cache_write, time_created/time_updated, parent_id, directory, title.
- Both opened **read-only** (`sqlite3 -readonly`; SELECT-only SQL). **All SQL uses parameter placeholders — no f-string/format-built SQL** (session titles are free agent-written text and flow into queries). **All subprocess calls are argv lists — never `shell=True`** (docker exec, gh; config values and regex-extracted numbers never become shell syntax).
- **Busy handling**: `PRAGMA busy_timeout=5000` on the host connection, `.timeout 5000` in the container invocation — both DBs are live WAL stores with active writers.
- **Fail-open per source**: container down, docker error, SQLITE_BUSY beyond the timeout, any open/read failure → skip that source with a warning (stderr + a note in `index.json`), the other source continues, snapshots keep their previous values for the skipped source's sessions, exit code stays 0.
- **Every run is a full rebuild** (Design revision 1): read all sessions from each available source, recompute all snapshots, replace `index.json`/`unmatched.json`. Issues whose mapped session set becomes empty after a rebuild lose their snapshot file and index entry (their board cards keep the last written numbers). First run and every later run are the same code path.

### Session → issue mapping

1. **Project attribution**: session `directory` → project, via ordered directory prefixes in config (e.g. `/root/workspace/memo` and `/Users/mkosinov/dev/memo` → `memo`; both superagents clones → `superagents`). Sessions in directories matching no project are still read — they flow into the unmatched table (step 5) with project «—», because they are real spend the user may want to bind. Issue numbers are namespaced per project (memo #26 ≠ superagents #26).
2. **Root detection**: session without `parent_id` (per source DB). Children inherit the root's issue via the recursive `parent_id` tree (panels and T-tasks do NOT repeat the number — verified).
3. **Issue number from the root title** — ordered pattern set, first match wins (leftmost–strongest):
   1. `#(\d{1,4})` anywhere («Разведка issue #327», «IMPL #324 delete family»);
   2. `^(\d{1,4})\b` leading bare number («327 каскад удаления» — memo habit);
   3. `(?:issue|тикет|задач[аи]|дизайн)\s+(\d{1,4})\b` (Russian forms like «дизайн 26 тикета»).
4. **Manual overrides**: `data/overrides.json` — `{session_id: {"project": "memo", "issue": 327, "phase": "impl"}}`, wins over every heuristic. Applied by the binding button and editable by hand; a hand-removed line takes effect on the next run (full rebuild — no stale-cache window). An override carries the project explicitly, so it also serves sessions from unattributed directories.
5. **Unmatched**: roots that match no issue (any directory) → `data/unmatched.json`, regenerated by every rebuild: project (derived, else «—»), date, directory, title, tokens, session id; sorted by tokens desc. Shown in the viewer's **global** dashboard tab (not under a project tab).

### Phase attribution (design vs IMPL)

Per-project mode from config:

- **`split`** (memo): host-DB sessions → design; container-DB sessions → IMPL. Clean split — the two worlds live in different DBs.
- **`title`** (superagents): everything is on the host; a root whose title starts with `IMPL` (case-insensitive) → impl, otherwise → design.

Overrides can force a root's phase in both modes. An issue can have sessions in both phases from both sources (memo: design on host + IMPL in container).

### Token accounting

- Canonical components: input, output, reasoning, cache_read, cache_write (host: summed from `turn_usage`; container: from `session.tokens_*`). **Total = plain sum of the 5 raw components** (no weights).
- All `turn_usage` rows count, including errored/cancelled turns — they are real spend attempts (no NULL `duration_ms` exists — verified).
- Container marathon **root wrapper** (the manager session spanning the whole run): its tokens COUNT (real orchestration spend), its TIME does not (see below).

### Active model time and calendar span

- **Active model time** (primary metric, shown next to tokens at every level):
  - Host: `SUM(turn_usage.duration_ms)` per session — per-turn durations, pauses between turns excluded by construction. Counts for roots AND children.
  - Container (approximation): `SUM(time_updated − time_created)` over **child sessions only**; root wrappers excluded (their span ≈ the whole marathon calendar — including it would double-count wall time). **Childless roots count their own span** (a single-step IMPL session is real work, not a wrapper). The label in the viewer says what it is: «≈ сумма по параллельным дочерним сессиям» — parallel children overlap and children contain tool-run gaps, so the number can over- and under-count wall time; it measures model-engaged span, consistent with summing per-turn durations of parallel panelists on the host.
- **Calendar span** (secondary): `max(end) − min(start)` over the sessions of a phase. Issue-page phase rows only («календарно: 3 дня»; below one day — hours: «календарно: 9 ч»), never per task/gate node.
- Timestamps are UTC epoch milliseconds in both DBs (verified); rendered in local time.

### Drill-down tree

- The `parent_id` tree is walked **recursively to any depth**; a node's tokens and time are the **aggregate of its whole subtree** (own session + descendants), so no level of nesting loses spend and node numbers reconcile with issue totals.
- **Design phase**: root session node → children = gates and helpers, identified by agent attribution (scout `zcode-Explore`, panelists `zcode-spec-panel-*`, `plan-reviewer`, plain subagents; unrecognized agents keep their raw agent string as the label). Every node: title, agent, 5 token components, active time.
- **IMPL phase**: marathon root → children folded under a `T<N>` node when the title matches `^T(\d+)[:. ]` (one task = several sub-sessions: implement/compliance/quality — they aggregate, each keeping its subtree); unlabeled children («Fix GET-side bus emission») stay standalone nodes.

### By-model and by-agent aggregates

Per issue (and per phase): host — from `model_usage` (per-call `model_id`/`agent` + tokens, joined to mapped sessions by `session_id`); container — from `session.model`/`session.agent` + session tokens. Rendered as CSS horizontal bar charts on the issue page.

### Snapshots and state (`data/`, all atomic: tmp file + `os.replace`)

- `issues/<project>-<N>.json` — per-issue snapshot: title (+ source: gh/fallback), project, last activity, issue-level totals — raw (5 components + total, active_ms) AND **board-ready rounded values** the write-back dot-paths point at: `tokens.total_m`, `active.hours`, mirrored per phase; `phases: {design, impl}` each with tokens (5 + total), active_ms, calendar span, the full recursive drill-down tree; plus `by_model`, `by_agent`, `collected_at`. Scaling/rounding happens at snapshot build (millions 1 dp; hours 1 dp) — the write-back writes the resolved number verbatim and its diff-gate compares the written (rounded) value, so rounding noise never triggers writes.
- `index.json` — issue list (project, issue, totals, phase split, last activity), collect metadata, per-source availability (watermarks do not exist — Design revision 1).
- `unmatched.json` — the dashboard tab's table, regenerated every rebuild.
- `titles.json` — gh issue-title cache. Refresh: one bulk `gh issue list` per repo per run (cheap, one call); the cache is the offline fallback; gh failure → «issue #N»; closed issues keep the last known title.
- `state.json` — write-back last-written cache + issue→item-id cache (no watermarks).
- `overrides.json` — manual bindings (see Mapping).
- `collect.log`, `.lock` — cron log and an flock serializing ALL snapshot writers (cron runs and serve-triggered rebuilds).

### Collection runs (`collect.py`)

- `collect` — **full rebuild** of both sources, then write-back (for projects with it enabled). Cron example (README): `*/15 * * * * cd <repo>/token-analytics && python3 collect.py collect >> data/collect.log 2>&1` — cadence 15–30 min is the user's cron choice; no in-tool scheduler. A second run finding the lock held → log «skipped: previous run still active», exit 0.
- Bind-triggered rebuild — the server runs the same full rebuild in-process after appending an override (seconds; under the same lock).
- `fields` — create/validate the 6 NUMBER fields on each enabled project's board (idempotent; safe to run anytime; see Board write-back).
- `writeback` — standalone: re-push from existing snapshots WITHOUT a rebuild (manual re-push). Write-back also runs at the end of every rebuild.

### Viewer (`collect serve`, `server.py`)

- `ThreadingHTTPServer` on **127.0.0.1:8765** (threaded: browsers pre-open sockets, and the bind-triggered rebuild must not stall serving): serves `viewer/` static files, `data/*.json` (GET), and one POST endpoint:
  - `POST /api/bind {session_id, project, issue, phase}` — accepts **any session id known to the last snapshot set** (matched or unmatched — rebinding a wrongly auto-matched session is the normal fix path; overrides always win). Validates: session known, issue exists (has a snapshot or `gh issue view` succeeds — typos get a 400, not phantom snapshots), phase enum, project enum. Appends to `overrides.json` (atomic), runs the rebuild under the lock, responds with the issue page path. Lock busy beyond ~10 s → 503 «сбор идёт, повтори». No other write surface; no path parameters anywhere.
  - **Request guards** (one clause, always on): reject any request whose `Host` is not `127.0.0.1:8765`/`localhost:8765` (DNS-rebinding protection — loopback binding alone does not stop it), reject POSTs bearing a non-loopback `Origin` (CSRF), accept `POST` only with `Content-Type: application/json`.
- `viewer/` mirrors the canon site pattern (static `index.html` + `app.js` + `style.css`, no build step, no external libs):
  - **Index**: project tabs → issue table sorted by token total (title, tokens human, active time human, last activity, design/IMPL mini-split); plus the **global** «Несопоставленные» tab. In-progress issues show accrued spend and the REAL last-activity date — no invented «completed» status. A project with zero issues renders an explicit empty state.
  - **Issue page**: phase rows (design/IMPL; an absent phase is hidden, not zero-filled): tokens 5-components + total, active model time, calendar span as a secondary line; by-model and by-agent CSS bars; expand/collapse drill-down per the recursive tree; container time marked with the «≈» label above.
  - **Unmatched tab**: the `unmatched.json` table + «Привязать» button per row (project prefilled from the directory when attributable, issue № + phase) → POST → row moves into the issue.
- Units: site tokens human («12.4M», «830K»), time human («1ч 24м»); board units below.

### Board write-back (`writeback.py`)

- **Fields**: 6 numeric fields **on each project's own board** (superagents → project #4; memo → project #3) — tokens total / design / IMPL, hours total / design / impl, canonical names as in the config. Created by the **`fields` subcommand** (Design revision 3): per enabled project, missing fields are created via the managed `gh project field-create --data-type NUMBER` (one call per field, idempotent); an existing name with a non-NUMBER type stops loudly naming the field, changing nothing. **Never** renames or modifies existing fields, **never** touches single-select options — the 2026-09-09 wipe ban stands untouched. The config binds by **field name**; `writeback` resolves name→id per run via `gh project field-list` (explicit limit/pagination — same rule as item-list); an unknown name → warning + that field skipped with a «run `fields`» hint. `field-create` is the second recorded exception to the single-writer rule, alongside `item-edit` (both managed CLI; item-edit approved at G1a close, field-create by this amendment). Memo ships `enabled: false`; enablement = config flip + one `fields` run (Design revision 2).
- **Commands**: managed CLI only — `gh project item-edit --id <item> --field-id <field> --project-id <project> --number <value>` (one item+field per call) and `gh project field-create --data-type NUMBER` (one-time field creation); nothing else. **Never** raw GraphQL mutations and **never** field-definition mutations (`updateProjectV2Field`) — the 2026-09-09 wipe ban stands untouched (that ban concerns raw field mutations; `item-edit` is not one). What this tool DOES take is a recorded exception to the single-writer rule «all board writes go through `gh_board.py`»: `writeback.py` is a deliberate second writer via the managed CLI, approved at G1a close (issue #23's skill rewrite should mention it — see Relation).
- **Values**: written verbatim from the snapshot's board-ready fields — tokens in millions with 1 decimal («48.2»), hours with 1 decimal («25.3»).
- **Config is generic**: each project's `write_back.fields` maps field id → dot-path into that issue's snapshot. The 6 starting fields are 6 config lines with canonical paths: `tokens.total_m`, `phases.design.tokens.total_m`, `phases.impl.tokens.total_m`, `active.hours`, `phases.design.active.hours`, `phases.impl.active.hours`. A future field («design gate tokens», hand-measured gate toll) = create the field by hand + one config line, no code change.
- **Diff-gated**: last-written values cached in `state.json`; a field is written only when the written (rounded) number changed. Failures (gh error, network) → warning to the log, collection continues, exit code 0 (fail-open). Issue not on that project's board → skip with a note. A write failure with a cached item id drops that cache entry (a re-added card gets a new id) — re-resolved next run.
- **Item-id resolution**: `gh project item-list` per project board with an **explicit `--limit` and a pagination loop until exhausted** (the CLI's default 30 silently truncates — board #4 already grew past 30 once); resolved once per run and cached in `state.json`.
- **No status filtering**: in-progress AND closed issues are written alike (a closed card keeps its last numbers; late bindings still update it).
- **Kill switch**: `write_back.enabled: false` per project skips the whole stage.

### Config file (`config.json`, committed, no secrets)

    {
      "version": 1,
      "sources": {
        "zcode_host": {"db": "~/.zcode/cli/db/db.sqlite"},
        "opencode_container": {"container": "opencode", "db": "/root/.local/share/opencode/opencode.db"}
      },
      "projects": {
        "superagents": {
          "repo": "mkosinov/superagents", "phase_mode": "title",
          "directories": ["/Users/mkosinov/dev/opencode/workspace/superagents", "/Users/mkosinov/dev/superagents"],
          "board": {"owner": "mkosinov", "project_number": 4, "project_id": "PVT_kwHOA-0Z984BkOSk"},
          "write_back": {"enabled": true, "fields": {
            "Tokens total":  "tokens.total_m",
            "Tokens design": "phases.design.tokens.total_m",
            "Tokens IMPL":   "phases.impl.tokens.total_m",
            "Hours total":   "active.hours",
            "Hours design":  "phases.design.active.hours",
            "Hours impl":    "phases.impl.active.hours"
          }}
        },
        "memo": {
          "repo": "mkosinov/memo", "phase_mode": "split",
          "directories": ["/root/workspace/memo", "/Users/mkosinov/dev/memo"],
          "board": {"owner": "mkosinov", "project_number": 3, "project_id": "<PVT_…>"},
          "write_back": {"enabled": false, "fields": {
            "Tokens total":  "tokens.total_m",
            "Tokens design": "phases.design.tokens.total_m",
            "Tokens IMPL":   "phases.impl.tokens.total_m",
            "Hours total":   "active.hours",
            "Hours design":  "phases.design.active.hours",
            "Hours impl":    "phases.impl.active.hours"
          }}
        }
      },
      "serve": {"host": "127.0.0.1", "port": 8765}
    }

Fields bind by NAME; the six canonical name→dot-path lines ship in the config from day one — nothing to paste; `fields` creates/validates the fields on the board (README documents the one run per project). An empty `fields` map remains a documented write-back no-op. The superagents constants mirror the `gh_board.py` convention (same values, kept in sync by hand — two lines, see Relation).

## Safety & privacy

- `token-analytics/data/` added to `.gitignore` — personal metrics never enter git (the golden test below follows the same rule).
- Source DBs: SELECT-only, `-readonly` flags, parameterized SQL, argv-list subprocesses (no `shell=True`); the container is never restarted or written.
- `config.json` carries no secrets — paths, ids, ports only. gh auth stays inside the gh CLI.
- The server binds 127.0.0.1 AND validates the `Host` header (DNS-rebinding), POST `Origin` (CSRF) and `Content-Type`; the single POST endpoint validates every field against the last snapshot set / enums and writes exactly one file (`overrides.json`) via the atomic helper.

## Testing

Offline by construction: synthetic fixture DBs of BOTH schemas, generated by test setup into a tmp dir (no committed binaries).

- **Unit**: ordered mapping patterns (incl. Russian titles, leftmost-wins, multi-number titles); recursive tree building and subtree aggregation (grandchildren fold into their parent node); T-label folding (labeled group vs standalone); phase modes (split vs title) + phase overrides; token math (5 components, raw-sum total, board-value rounding M-1dp / hours-1dp); full-rebuild determinism (same fixture DB → byte-identical snapshot); write-back diff-gating on rounded values, fail-open, item-cache invalidation; name→id resolution (unknown name → warning + that field skipped); `fields` subcommand (missing → created, rerun idempotent, non-NUMBER type mismatch stops loudly with zero mutations); dot-path resolver; atomic write; lock behavior (second writer skips / POST 503); server guards (Host/Origin/Content-Type); bind validation (unknown session → 400, unknown issue → 400, enum phases).
- **Golden**: real small issue — superagents #16 (host-only, the panel-security design) — golden snapshot in `data/` (gitignored): regenerated on demand, test **skips when the file is absent** (keeps personal numbers out of git while enabling local verification).
- **E2E per User Scenario** (below): `collect serve` on an ephemeral port over a fixture-populated `data/` dir, driven with stdlib `urllib` — assert index JSON, issue snapshot shape, bind POST (unmatched AND already-matched session) → override appended + snapshot updated (write-back stubbed). Browser-level look = manual acceptance (checklist in README).
- **Live acceptance (manual, one-time, at implementation)**: real `collect`; the 6 board fields created by the user in the web UI and written for real on board #4; `collect serve` opened in the browser. No live gh in automated tests.

## User Scenarios

1. **Dashboard overview** — open `http://localhost:8765` → project tabs → issue list sorted by token spend; an in-progress issue shows accrued tokens and its real last-activity date. → E2E: fixture `index.json` renders the table, sorted, with a WIP row carrying accrued totals.
2. **Issue page** — open an issue → design/IMPL phase rows with tokens (5 components + total), active model time, secondary «календарно: N дн»; by-model and by-agent bars. → E2E: issue snapshot contains both phases with the full field set and aggregates.
3. **Design drill-down** — expand design → root → gate nodes (scout, each panelist, plan-reviewer) each with agent, tokens, time. → E2E: tree children present with agent attribution and token components.
4. **IMPL drill-down** — expand IMPL → marathon root → `T1…Tn` folded nodes aggregating their sub-sessions (nested levels included) + standalone unlabeled children. → E2E: fixture children `T1: a`, `T1: b`, `Fix …` fold into one `T1` node plus one standalone node; a grandchild folds into its parent's subtree total.
5. **Bind a session** — dashboard tab «Несопоставленные» → «Привязать» → project + issue № + phase → the session appears under that issue, the row leaves the tab. A wrongly auto-matched session is rebound the same way from its issue page. → E2E: `POST /api/bind` on an unmatched and on an already-matched session → `overrides.json` gains/replaces the entry, the issue snapshot includes the session, `unmatched.json` drops it.
6. **Board write-back** — after a collect, the issue's card on its project board shows the 6 numeric fields; only changed values are written; a gh failure logs a warning and collection still exits 0; WIP issues are written too. → E2E (stubbed gh): diff-gate writes only changed fields; failure path continues; disabled flag skips everything.

## Reuse

- `.zcode/scripts/gh_board.py` — the `gql()` subprocess+error pattern (`sys.exit` on returncode and GraphQL errors), the constants convention (`PROJECT_ID`/`OWNER`/`REPO` at top), and the header's introspection query for discovering field ids. The write-back itself deliberately uses the managed `gh project item-edit` command instead of the script's raw-GraphQL `set_field()` (see Board write-back for which rule is excepted).
- `docs/specs/2026-09-21-board-bootstrap-design.md` §board_config.json — the style neighbor for `config.json` (version/project/owner keys); **no runtime dependency** (that file is not landed; its v1 covers single-select `PVTSSF_` ids, this tool binds numeric `PVTNF_` ids per project). Its pagination rule («no 30-row defaults — loop until exhausted») is adopted for `item-list`.
- `site/` — the static-site pattern to mirror in `viewer/`: `index.html` + JS + CSS, no build step; there data is baked into `main.js`, here it is fetched JSON (the data is dynamic).
- Verified command surfaces: `docker exec … sqlite3 -readonly` (recon), `gh project item-edit/field-list/item-list` flags (recon + panel), `session.time_updated`/epoch-ms timestamps (same column family in both DBs, verified).
- Agent-value vocabularies for chart labels from recon: host `zcode-Explore`, `zcode-spec-panel-*`, `zcode-plan-reviewer`; container memo agents (`frontend-coder`, `plan`, `architect`, `manager`, …).
- Python-stdlib-only convention (`gh_board.py` precedent; tests = stdlib `unittest`).
- Searched, nothing to reuse beyond the above: no `scripts/` dir, no existing collector/analytics code, `docs/domain-rules/` does not exist in this repo.

## Relation

- **#24 (board bootstrap)**: orthogonal — its `board_config.json` v1 binds single-select `PVTSSF_` field ids for status ops; this tool binds numeric `PVTNF_` write-back ids per project in its own config. When #24 lands, unifying the project-binding blocks is an optional follow-up, not a dependency. The issue's phrase «field ids land next to board_config.json» is resolved as: same conventions, self-contained file (the #24 config does not exist yet — recon).
- **#23 (board self-hosting)**: independent. The 2-line duplication of project constants (here vs `gh_board.py`) is accepted until #23's parameterization lands; a note in README marks the sync point. #23's skill rewrite («all board writes through the script») should name `writeback.py` as the recorded second writer (managed CLI only: `item-edit` for values, `field-create` for one-time field creation).
- **superagents #16**: the golden-test issue (small, host-only).
- **`docs/architecture/token-economy.md`**: stale; superseded for per-issue accounting by this tool's measurements. Refresh = separate task.
