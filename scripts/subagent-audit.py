#!/usr/bin/env python3
"""subagent-audit.py — recover a subagent's state from the opencode database.

Why: a subagent can "die" (interrupt, Esc, context exhaustion, transport bug) and
return an EMPTY task_result even though it did real work. Before re-dispatching
(fresh = full context reload, expensive) or blindly skipping, read what the
session actually did. Zero token cost — pure SQL.

Usage:
    python3 subagent-audit.py <session_id> [--json]
    python3 subagent-audit.py --project-sessions           # last 10 sessions of current project dir

session_id examples: ses_ffbafe64fffeOX12Lr0lgZmZKJ
DB (default): ~/.local/share/opencode/opencode.db  (override: $OPENCODE_DB)
Read-only: opens the DB with mode=ro — safe to run while opencode is live (WAL).

Output: compact digest —
  * session meta (agent, model, title, window, tokens)
  * recoverable report: last assistant TEXT parts (if the model wrote a report
    that just wasn't delivered)
  * tool-activity digest (read/grep/bash/edit/task/ptys…)
  * signals: git commits, test results (pty_exited), task sub-dispatches
  * verdict hints: resume vs read-from-DB vs re-dispatch
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

DB = os.environ.get("OPENCODE_DB", str(Path.home() / ".local/share/opencode/opencode.db"))
TEXT_MAX = 700          # chars shown per assistant text part
TAIL_TEXTS = 3          # how many last text parts to show
BASH_MAX = 150          # chars shown per bash command
SIGNAL_MAX = 5          # how many git/test signal lines to show


def connect():
    if not Path(DB).exists():
        sys.exit(f"error: DB not found at {DB}")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def run(conn, sql, args=()):
    return conn.execute(sql, args).fetchall()


def fmt_ts(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if ms else "—"


def fmt_dur(ms):
    if not ms:
        return "—"
    s = int(ms / 1000)
    return f"{s // 3600}h {(s % 3600) // 60}m {s % 60}s"


def extract_parts(conn, session_id):
    """Return (meta, parts) where parts = list of (t, type, kind, payload)."""
    meta = run(conn, """
        SELECT id, COALESCE(agent,''), COALESCE(title,''), COALESCE(model,''),
               time_created, time_updated, tokens_input, tokens_output,
               tokens_cache_read
        FROM session WHERE id = ?
    """, (session_id,))
    if not meta:
        sys.exit(f"error: session {session_id} not found")
    m = meta[0]
    parts = run(conn, """
        SELECT m.time_created, p.data
        FROM part p JOIN message m ON m.id = p.message_id
        WHERE p.session_id = ?
        ORDER BY m.time_created, p.id
    """, (session_id,))
    return m, parts


def parse_part(raw):
    try:
        return json.loads(raw)
    except Exception:
        return {"type": "unknown"}


def is_pty_event(text):
    """True if a text part is an actual pty_exited notification.

    opencode injects the notification as its OWN text part that starts with the
    opening tag, e.g. "<pty_exited>\\nID: pty_...\\nExit Code: 0...</pty_exited>
    \\n\\nUse pty_read to check the full output.". Dispatch/instruction text that
    merely MENTIONS the tag (usually inside backticks, e.g. "waiting for
    `<pty_exited>`") must NOT be counted as a signal. Pragmatic heuristic:
    require the part to START with the tag and contain the closing tag.
    """
    return text.startswith("<pty_exited>") and "</pty_exited>" in text


def build_digest(m, parts, tail_texts):
    out = {"session_id": m[0]}
    text_parts, bash_cmds, git_cmds, test_lines, ptys, tasks = [], [], [], [], [], []
    text_positions = []       # (index_in_parts, ts, text) — for ordering decisions
    last_tool_index = -1
    tool_counts = {}
    total_tools = 0

    for idx, (ts, raw) in enumerate(parts):
        p = parse_part(raw)
        kind = p.get("type")
        if kind == "text":
            text = (p.get("text") or "").strip()
            if text:
                text_parts.append((ts, text))
                text_positions.append((idx, ts, text))
                # pty_exited notifications arrive as their own text parts
                if is_pty_event(text):
                    ptys.append(text)
                low = text.lower()
                if ("passed" in low or " failed" in low or "pass" in low) and any(c.isdigit() for c in text):
                    test_lines.append(text)
        elif kind == "tool":
            tool = p.get("tool", "?")
            last_tool_index = idx
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
            total_tools += 1
            state = p.get("state") or {}
            if tool == "bash" and state.get("input"):
                cmd = (state["input"].get("command") or "").strip()
                if cmd:
                    bash_cmds.append(cmd)
                    if "git " in cmd and not cmd.startswith("git status --porcelain"):
                        git_cmds.append(cmd)
            elif tool == "task" and state.get("input"):
                inp = state["input"]
                tasks.append((inp.get("subagent_type", "?"), inp.get("description", "")))
        elif kind == "reasoning":
            pass

    # a genuine final report = a text that came AFTER the LAST tool call and is
    # not a pty notification and not a re-injected resume prompt
    final_texts = [
        (ts, text) for idx, ts, text in text_positions
        if idx > last_tool_index and not is_pty_event(text)
        and "You were interrupted" not in text
    ]

    ts_start, ts_end = m[4], m[5]
    last_text = final_texts[-1][1] if final_texts else ""
    has_final_report = bool(last_text and len(last_text) > 20)
    has_git = bool(git_cmds)
    has_tools = total_tools > 0

    digest = {
        "session_id": m[0],
        "meta": {
            "agent": m[1], "model": m[3], "title": m[2],
            "started": fmt_ts(ts_start), "ended": fmt_ts(ts_end),
            "duration": fmt_dur(ts_end - ts_start if ts_start and ts_end else 0),
            "messages_parts": len(parts),
            "tokens_input": m[6], "tokens_output": m[7],
            "tokens_cache_read": m[8],
        },
        "report": {
            "final_text_present": has_final_report,
            "last_texts": [
                {"at": fmt_ts(ts), "text": txt[:TEXT_MAX] + ("…" if len(txt) > TEXT_MAX else "")}
                for ts, txt in final_texts[-tail_texts:]
            ],
            "working_notes": [
                {"at": fmt_ts(ts), "text": txt[:200]}
                for ts, txt in [t for t in text_parts
                                if not is_pty_event(t[1]) and "You were interrupted" not in t[1]][-2:]
            ],
        },
        "tools": {
            "counts": dict(sorted(tool_counts.items(), key=lambda kv: -kv[1])),
            "total": total_tools,
            "bash_commands": [c[:BASH_MAX] for c in bash_cmds[-SIGNAL_MAX:]],
            "task_subdispatches": tasks[-SIGNAL_MAX:],
        },
        "signals": {
            "git_last": [c[:BASH_MAX] for c in git_cmds[-SIGNAL_MAX:]],
            "test_last": [t[:200] for t in test_lines[-3:]],
            "pty_exited": [t[:300] for t in ptys[-2:]],
        },
    }

    hints = []
    if has_final_report:
        hints.append("REPORT RECOVERABLE — final assistant text after last tool call; use it as the result")
    if has_git:
        hints.append("COMMITS FOUND — work may be salvageable (audit-verify-commit) instead of redo")
    if ptys or test_lines:
        hints.append("TEST RESULT IN DB — verdict readable without re-running")
    if not has_final_report and has_tools:
        hints.append("WORKED BUT NO FINAL REPORT — resume this session (cheap) to finish, do NOT fresh re-dispatch")
    if not has_tools and len(text_parts) <= 1:
        hints.append("NO WORK DONE — died at start; fresh re-dispatch is fine")
    digest["verdict_hints"] = hints
    return digest


def print_human(d):
    print(f"=== SESSION {d['session_id']} ===")
    meta = d["meta"]
    print(f"agent:      {meta['agent']}")
    print(f"model:      {meta['model']}")
    print(f"title:      {meta['title'][:110]}")
    print(f"window:     {meta['started']} → {meta['ended']}  ({meta['duration']})")
    print(f"parts:      {meta['messages_parts']} | in:{meta['tokens_input']} out:{meta['tokens_output']} "
          f"cache_read:{meta['tokens_cache_read']}")
    print()
    print("--- REPORT (last assistant text) ---")
    if d["report"]["final_text_present"]:
        for t in d["report"]["last_texts"]:
            print(f"[{t['at']}] {t['text']}")
    else:
        print("(no recoverable final text)")
    if d["report"].get("working_notes"):
        print("…last working notes (before dying):")
        for t in d["report"]["working_notes"]:
            print(f"  [{t['at']}] {t['text']}")
    print()
    print("--- TOOL ACTIVITY ---")
    counts = d["tools"]["counts"]
    print(" ".join(f"{k}:{v}" for k, v in counts.items()) or "(none)")
    if d["tools"]["task_subdispatches"]:
        print("sub-dispatches:")
        for sa, desc in d["tools"]["task_subdispatches"]:
            print(f"  {sa}: {desc[:80]}")
    print()
    print("--- SIGNALS ---")
    if d["signals"]["git_last"]:
        print("git:")
        for c in d["signals"]["git_last"]:
            print(f"  {c}")
    if d["signals"]["test_last"]:
        print("tests:")
        for t in d["signals"]["test_last"]:
            print(f"  {t[:200]}")
    if d["signals"]["pty_exited"]:
        print("pty_exited:")
        for t in d["signals"]["pty_exited"]:
            print(f"  {t[:300]}")
    if not (d["signals"]["git_last"] or d["signals"]["test_last"] or d["signals"]["pty_exited"]):
        print("(none)")
    print()
    print("--- VERDICT HINTS ---")
    for h in d["verdict_hints"]:
        print(f"* {h}")
    print()


def list_recent_sessions(conn, limit=10):
    """List recent sessions for the CURRENT working directory's project.

    The session table has a `directory` column holding the project path, so we
    scope to the caller's project instead of mixing sessions from all repos
    (e.g. 16 projects shared the audit DB before this filter).
    """
    project_dir = str(Path.cwd())
    rows = run(conn, """
        SELECT id, COALESCE(agent,''), COALESCE(title,''), time_created, tokens_input
        FROM session WHERE directory = ? ORDER BY time_created DESC LIMIT ?
    """, (project_dir, limit))
    print(f"last {len(rows)} sessions in {project_dir}:")
    for r in rows:
        print(f"  {r[0]}  {fmt_ts(r[3])}  {r[1]:<18} in:{r[4]:<9} {r[2][:80]}")


def main():
    ap = argparse.ArgumentParser(description="Recover subagent state from opencode DB")
    ap.add_argument("session_id", nargs="?", help="session id (ses_...)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--project-sessions", action="store_true",
                    help="list recent sessions of the CURRENT working-directory project (not all projects)")
    args = ap.parse_args()

    conn = connect()
    if args.project_sessions:
        list_recent_sessions(conn)
        return
    if not args.session_id:
        ap.error("session_id required (or use --project-sessions)")
    m, parts = extract_parts(conn, args.session_id)
    d = build_digest(m, parts, TAIL_TEXTS)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        print_human(d)


if __name__ == "__main__":
    main()