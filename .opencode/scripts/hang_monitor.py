#!/usr/bin/env python3
"""
hang_monitor.py — detect suspected frozen tool calls in opencode sessions and
stamp the corresponding board card's `gate` field with `hang` (via
gh_board.py, idempotent). Monitoring-only: this script NEVER interrupts,
aborts, or kills anything.

Failure class tracked as superagents board issue #21: a tool part stays in
state.status='running' forever because opencode lost the child process's exit
event (a race). Detection signatures (v1):

  bash   — part running beyond threshold AND the command has no live OS
           process in the container  -> high confidence
  task   — part running beyond threshold AND the whole dispatch subtree
           (child sessions) silent beyond 30 min          -> medium/high
  glob/read/grep — instant tools stuck in running          -> high confidence
  other  — running beyond a generous default threshold      -> low confidence

Deliberately NOT flagged: parts whose bash process is still alive (long test
runs, long pty work), 'question' parts (waiting for the user is legitimate),
and 'pty*' tool parts (long-lived by design).

Board channel (2026-10-06, user decision — replaces the issue-label channel):
every cycle stamps `gate=hang` on each issue that currently has evidence
(idempotent), writes ONE evidence comment per episode (new part ids only),
and clears the gate when the evidence is gone AND the chain shows activity
newer than the freeze moment. `hang` is a machine suspicion; a confirmed
hang awaiting the user is `blocked` (manager's job).

Runs inside the opencode container (needs read access to opencode.db, gh
auth, and the gh_board.py runtime copy). Session chain -> issue mapping
comes from session titles (regex '#N' / 'issue N') with a fallback table.

Usage: hang_monitor.py [--once]
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DB = "/root/.local/share/opencode/opencode.db"
STATE_PATH = "/root/.local/share/opencode/hang_monitor_state.json"
LOG_PATH = "/root/.local/share/opencode/hang_monitor.log"
# board script: sibling copy first (repo deployment), then the container
# runtime copy at /root/.local/share/opencode/
GH_BOARD = str(Path(__file__).resolve().parent / "gh_board.py")
if not Path(GH_BOARD).exists():
    GH_BOARD = "/root/.local/share/opencode/gh_board.py"
WINDOW_DAYS = 7          # ignore parts older than this (historic fossils)
CYCLE_SECONDS = 300
MAX_COMMENTS_PER_CYCLE = 10
TASK_SUBTREE_SILENCE_S = 1800   # task: dispatch subtree must be silent this long
CLEAR_MARGIN_MS = 60_000        # chain activity must beat the freeze by this margin

# age threshold (seconds) per tool before a still-running part is suspect
THRESHOLD = {"bash": 600, "task": 1800, "glob": 300, "read": 300, "grep": 300}
DEFAULT_THRESHOLD = 3600
# 'running' is legitimate indefinitely for these -> never flag
SKIP_TOOLS = {"question", "pty", "pty_read", "pty_list", "pty_write",
              "todowrite", "todoread"}

# session directory prefix -> GitHub repo (comment target); others: log only
REPOS = {"/root/workspace/superagents": "mkosinov/superagents"}
# fallback: manager session id -> issue number (when titles carry no number)
SESSION_ISSUE_FALLBACK = {}


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
        if os.path.getsize(LOG_PATH) > 1_000_000:
            os.truncate(LOG_PATH, 200_000)
    except OSError:
        pass


def load_state():
    try:
        with open(STATE_PATH) as f:
            state = json.load(f)
    except Exception:
        state = {}
    state.setdefault("alerted", {})
    state.setdefault("stamped", {})
    return state


def save_state(state):
    # prune per-part alert keys older than 30 days
    cutoff = time.time() * 1000 - 30 * 86400 * 1000
    state["alerted"] = {k: v for k, v in state["alerted"].items()
                        if v.get("t", 0) > cutoff}
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def db_rows(query, args=()):
    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=10)
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def stuck_parts(cutoff_ms):
    return db_rows(
        """SELECT p.id, p.session_id, p.time_created,
                  json_extract(p.data,'$.tool'),
                  json_extract(p.data,'$.state.input.command')
           FROM part p
           WHERE json_extract(p.data,'$.state.status')='running'
             AND p.time_created > ?""", (cutoff_ms,))


def session_row(sid):
    rows = db_rows("SELECT id, parent_id, title, directory FROM session WHERE id=?",
                   (sid,))
    return rows[0] if rows else None


def chain_up(sid):
    """Session chain bottom -> top: [(id, parent_id, title, directory), ...]."""
    chain, cur = [], sid
    for _ in range(10):
        row = session_row(cur)
        if not row:
            break
        chain.append(row)
        if not row[1]:
            break
        cur = row[1]
    return chain


def subtree_last_activity(sid, column="time_created", depth=0):
    """max message/part timestamp (ms) over the session and all descendants."""
    if depth > 8:
        return 0
    rows = db_rows(
        """SELECT max(m), max(p) FROM
             (SELECT (SELECT max(%s) FROM message WHERE session_id=?) m,
                     (SELECT max(%s) FROM part    WHERE session_id=?) p)""" % (column, column),
        (sid, sid))
    best = max(rows[0][0] or 0, rows[0][1] or 0)
    for (child,) in db_rows("SELECT id FROM session WHERE parent_id=?", (sid,)):
        best = max(best, subtree_last_activity(child, column, depth + 1))
    return best


def ps_args_norm():
    out = subprocess.run(["ps", "-eo", "args", "-ww"],
                         capture_output=True, text=True).stdout
    return " ".join(out.split())


def issue_for_chain(chain):
    """chain is bottom -> top; scan titles top -> bottom (manager decides)."""
    for row in reversed(chain):
        title = row[2] or ""
        m = re.search(r"issue\s*#?\s*(\d+)", title, re.I) or re.search(r"#(\d+)", title)
        if m:
            return int(m.group(1))
    top = chain[-1][0] if chain else None
    return SESSION_ISSUE_FALLBACK.get(top)


def repo_for_chain(chain):
    directory = chain[0][3] or ""
    for prefix, repo in REPOS.items():
        if directory.startswith(prefix):
            return repo
    return None


def gh(args, check=True):
    r = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("gh %s failed: %s" % (" ".join(args),
                                                 r.stderr.strip()[:300]))
    return r


def board_gate(issue, value):
    """Stamp/clear the gate via gh_board.py (idempotent). True on success."""
    try:
        r = subprocess.run([sys.executable, GH_BOARD, "gate", str(issue), value],
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        log("board gate %s %s timed out" % (issue, value))
        return False
    if r.returncode != 0:
        log("board gate %s %s failed: %s" % (issue, value,
                                             (r.stderr or r.stdout).strip()[:200]))
        return False
    return True


def fmt_age(seconds):
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 86400:
        return "%dh%dm" % (seconds // 3600, (seconds % 3600) // 60)
    return "%dd%dh" % (seconds // 86400, (seconds % 86400) // 3600)


def fmt_chain(chain):
    parts = []
    for sid, _parent, title, _dir in reversed(chain):
        t = (title or "").replace("|", "/")[:48]
        parts.append("%s [%s]" % (t, sid[:16]))
    return " → ".join(parts)


def comment_body(items):
    lines = [
        "⏱️ **hang-monitor** (v1, monitoring-only — never interrupts): suspected frozen tool call(s); card stamped `gate=hang`.",
        "",
        "| confidence | tool | age | session chain | evidence |",
        "|---|---|---|---|---|",
    ]
    for it in items:
        lines.append("| %s | %s | %s | %s | %s |" % (
            it["confidence"], it["tool"], it["age"], it["chain"], it["evidence"]))
    lines += [
        "",
        "Detection: tool part stuck in `running` + no live process / silent dispatch subtree. The gate stamp is refreshed every cycle and auto-cleared when the evidence is gone and the chain shows life.",
        "If a listed call is actually alive (long test run, long pty work) — this is a false positive, thresholds will be tuned. Ref: board issue #21.",
    ]
    return "\n".join(lines)


def run_cycle():
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - WINDOW_DAYS * 86400 * 1000
    state = load_state()
    psn = ps_args_norm()
    groups = {}   # "repo#issue" -> {repo, issue, manager_sid, freeze_ms, items, has_new}
    scanned = 0

    for part_id, session_id, t_created, tool, command in stuck_parts(cutoff):
        scanned += 1
        tool = tool or "?"
        if tool in SKIP_TOOLS:
            continue
        age_s = (now_ms - t_created) / 1000.0
        if age_s < THRESHOLD.get(tool, DEFAULT_THRESHOLD):
            continue

        chain = chain_up(session_id)
        if not chain:
            continue

        if tool == "bash":
            cmd = (command or "").strip()
            frag = " ".join(cmd.split())[:120]
            if frag and frag in psn:
                log("alive-long %s tool=bash age=%ds session=%s (not flagged)"
                    % (part_id[:24], int(age_s), session_id[:24]))
                continue
            evidence = "no live process for: `%s`" % (cmd[:160] or "?")
            confidence = "high"
        elif tool == "task":
            silent_s = time.time() - subtree_last_activity(session_id) / 1000.0
            if silent_s < TASK_SUBTREE_SILENCE_S:
                continue  # dispatch subtree still active — legitimate long dispatch
            evidence = "dispatch subtree silent for %s" % fmt_age(silent_s)
            confidence = "high" if silent_s > 6 * 3600 else "medium"
        elif tool in ("glob", "read", "grep"):
            evidence = "instant tool stuck in running for %s" % fmt_age(age_s)
            confidence = "high"
        else:
            evidence = "tool '%s' running for %s" % (tool, fmt_age(age_s))
            confidence = "low"

        repo, issue = repo_for_chain(chain), issue_for_chain(chain)
        if not repo or not issue:
            log("stuck-unmapped %s tool=%s age=%ds repo=%s issue=%s (log only)"
                % (part_id[:24], tool, int(age_s), repo, issue))
            continue

        key = "%s#%d" % (repo, issue)
        g = groups.setdefault(key, {"repo": repo, "issue": issue,
                                    "manager_sid": chain[-1][0],
                                    "freeze_ms": 0, "items": [], "has_new": False})
        g["freeze_ms"] = max(g["freeze_ms"], t_created)
        item = {"tool": tool, "age": fmt_age(age_s), "chain": fmt_chain(chain),
                "evidence": evidence, "confidence": confidence}
        g["items"].append(item)
        if part_id not in state["alerted"]:
            state["alerted"][part_id] = {"t": now_ms, "key": key}
            g["has_new"] = True
            log("flagged %s tool=%s age=%ds issue=%s confidence=%s"
                % (part_id[:24], tool, int(age_s), key, confidence))

    # stamp hang on every issue with current evidence (idempotent, every cycle)
    commented = 0
    for key, g in groups.items():
        if not board_gate(g["issue"], "hang"):
            continue
        state["stamped"][key] = {"repo": g["repo"], "issue": g["issue"],
                                 "manager_sid": g["manager_sid"],
                                 "freeze_ms": g["freeze_ms"]}
        if g["has_new"] and commented < MAX_COMMENTS_PER_CYCLE:
            gh(["issue", "comment", str(g["issue"]), "--repo", g["repo"],
                "--body", comment_body(g["items"])])
            commented += 1
        log("gate=hang %s (%d part(s))" % (key, len(g["items"])))

    # clear hang where the evidence is gone AND the chain shows life again
    for key in list(state["stamped"]):
        if key in groups:
            continue
        st = state["stamped"][key]
        last = subtree_last_activity(st["manager_sid"], "time_updated")
        if last and last > st["freeze_ms"] + CLEAR_MARGIN_MS:
            if board_gate(st["issue"], "none"):
                del state["stamped"][key]
                log("gate cleared %s (evidence gone, chain alive)" % key)

    save_state(state)
    log("cycle done: scanned=%d groups=%d stamped=%d comments=%d"
        % (scanned, len(groups), len(state["stamped"]), commented))


def main():
    if "--once" in sys.argv:
        run_cycle()
        return
    log("hang_monitor started (pid %d, cycle %ds)" % (os.getpid(), CYCLE_SECONDS))
    while True:
        try:
            run_cycle()
        except Exception as e:
            log("cycle error: %r" % e)
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()
