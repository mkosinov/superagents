---
description: Raise/stop/restart the user playground (backend :8101 + admin :3100) from the dedicated worktree — isolated from IMPL/e2e sessions
---

> **PROJECT-SPECIFIC values live here** (like gh_board.py constants): worktree path, repo
> name, DB filename, health URL, admin entry route. Shipped values are the reference project
> (memo) — adapt the `<...>`-marked lines when deploying to a new project. Ports :8101/:3100
> are the harness convention — keep them.

Handle a user playground request. First action: call `get-session` and print the returned id. Then dispatch a `tester` subagent with the spec below (verbatim key parts). If the tester subagent is unavailable, you may execute the spec yourself with pty/bash tools.

**Argument handling** (`$ARGUMENTS`, case-insensitive):
- empty or `up` (default) → if backend health AND admin respond → report "already up" with URLs and stop; else run START.
- `restart` or `update` → run STOP, then `git -C <REPO_ROOT> worktree list-check` (see worktree refresh below), then START.
- `stop` → run STOP only.

## Playground spec (harness canon — established 2026-09-08, memo)

Isolated playground serving merged main: dedicated worktree with its OWN frontend build (`.next`), `node_modules`, `.venv`, and a COPY of the seeded dev DB, on host-published ports. Must never conflict with dev.sh defaults (:8000/:3000/:3001), e2e shard ranges (:8001-8002/:3002-3003), or IMPL worktrees.

- Worktree: `/root/workspace/worktrees/playground`, branch `feat/playground` (create with `git -C <REPO_ROOT> worktree add -b feat/playground /root/workspace/worktrees/playground origin/main` if missing).
- Backend: **:8101**, Admin frontend: **:3100** (both must be published to the host by the container; a non-published port gives the browser ERR_CONNECTION_REFUSED even when it works inside — never pick unpublished ports).
- `restart/update` refresh: `git -C /root/workspace/worktrees/playground fetch origin && git -C /root/workspace/worktrees/playground reset --hard origin/main`.

### STOP
1. If scratchpad has playground PTY ids, `pty_kill` them (cleanup=true).
2. Fallback if ids unknown: find PIDs listening on :8101/:3100 via `lsof -ti :8101` / `lsof -ti :3100` and kill those exact PIDs. NEVER pkill by pattern, NEVER touch other ports.

### START
1. Worktree prep (idempotent — skip what exists):
   - Copy gitignored runtime files from the main root if absent in the worktree: backend env (`backend/.env.dev`), seeded DB (`backend/memo.db` — never re-seed, never delete the original).
   - `cd /root/workspace/worktrees/playground/backend && uv sync` (retry with `uv sync --extra dev` if uvicorn missing).
   - `cd /root/workspace/worktrees/playground/frontend/admin && CI=true pnpm install`.
2. Start via TWO `pty_spawn` sessions (no `timeoutSeconds`, titles "Playground backend :8101" / "Playground admin :3100"):
   - Backend, from `/root/workspace/worktrees/playground/backend`:
     `ENV_FILE=.env.dev PYTHONPATH=src uv run uvicorn src.main:app --host 0.0.0.0 --port 8101`
   - Admin, from `/root/workspace/worktrees/playground/frontend/admin`:
     `CI=true NEXT_PUBLIC_API_URL=http://localhost:8101 pnpm exec next dev -p 3100 -H 0.0.0.0`
   (`NEXT_PUBLIC_API_URL` MUST be set at server start — it bakes into the client bundle. `CI=true` suppresses the pnpm 11+ modules-purge prompt.)
3. Verify (mandatory):
   - Backend health: `curl -s http://localhost:8101/api/v1/health` → expect healthy JSON with `db: connected` (adapt path/status to the project).
   - Admin: `curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/<entry-route>` → 200 (first compile up to ~90 s, retry).
   - Baked-URL proof: fetch the entry-route HTML chunks and grep for `localhost:8101` (must be present) and for `:8100`/`:8000` (must be absent).
   - Isolation: playground listens ONLY on :8101 + :3100.
4. Rules: no tests, no commits, no pattern-kills, do not touch IMPL worktrees or other sessions' processes.

### Report to user
Status | URLs (admin `http://localhost:3100`, API docs `http://localhost:8101/docs`) | PTY ids + PIDs | any warnings. Record PTY ids + PIDs in your scratchpad section for later STOP.
