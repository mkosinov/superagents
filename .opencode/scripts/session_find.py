#!/usr/bin/env python3
"""session_find.py — read-only search over the opencode session DB.

Replaces hand-written sqlite one-liners (audit 2026-09-09: 21+ observed in
manager sessions over 3 weeks). One command, fixed output, no schema
relearning, no escaping mistakes.

Usage (from repo root, inside the container):
  python3 .opencode/scripts/session_find.py <text>              # search titles (substring)
  python3 .opencode/scripts/session_find.py --agent manager     # recent sessions of an agent
  python3 .opencode/scripts/session_find.py --id ses_xxx        # one session: tokens, times, part counts
  python3 .opencode/scripts/session_find.py --parent ses_xxx    # subagent children of a session
  Combine freely: --agent architect <text>; --limit N (default 15).

DB: /root/.local/share/opencode/opencode.db (override with OPENCODE_DB).
Read-only by design: opens with mode=ro, executes SELECTs only.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

DB = os.environ.get("OPENCODE_DB", "/root/.local/share/opencode/opencode.db")


def connect():
    if not os.path.exists(DB):
        sys.exit(f"DB not found: {DB} (set OPENCODE_DB)")
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def ts(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M") if ms else "?"


def tok(n):
    if not n:
        return "0"
    return f"{n/1e6:.1f}M" if n >= 1_000_000 else (f"{n//1000}k" if n >= 1000 else str(n))


def dur(created, updated):
    m = max(0, (updated - created) // 60000)
    return f"{m//60}h{m%60:02d}m" if m >= 60 else f"{m}m"


def row_line(r):
    title = (r["title"] or "")[:52]
    agent = (r["agent"] or "-")[:10]
    return (f"{r['id']}  {ts(r['time_created'])}  {dur(r['time_created'], r['time_updated']):>7}  "
            f"{agent:<10} {tok(r['tokens_input']):>6}/{tok(r['tokens_output']):<6} {title}")


def list_sessions(text, agent, parent, limit):
    con = connect()
    con.row_factory = sqlite3.Row
    q = "SELECT id,title,agent,time_created,time_updated,tokens_input,tokens_output FROM session WHERE 1=1"
    args = []
    if text:
        q += " AND instr(title, ?) > 0"
        args.append(text)
    if agent:
        q += " AND agent = ?"
        args.append(agent)
    if parent:
        q += " AND parent_id = ?"
        args.append(parent)
    q += " ORDER BY time_updated DESC LIMIT ?"
    args.append(limit)
    rows = con.execute(q, args).fetchall()
    if not rows:
        print("No sessions match.")
        return
    for r in rows:
        print(row_line(r))


def show_session(sid):
    con = connect()
    con.row_factory = sqlite3.Row
    r = con.execute(
        "SELECT id,title,agent,directory,parent_id,time_created,time_updated,"
        "tokens_input,tokens_output,tokens_cache_read FROM session WHERE id = ?", (sid,)
    ).fetchone()
    if not r:
        sys.exit(f"session {sid} not found")
    print(f"{r['id']}  {r['title']}")
    print(f"  agent: {r['agent'] or '-'}   dir: {r['directory']}")
    print(f"  created: {ts(r['time_created'])}  updated: {ts(r['time_updated'])}  "
          f"duration: {dur(r['time_created'], r['time_updated'])}")
    print(f"  tokens: in {tok(r['tokens_input'])} / out {tok(r['tokens_output'])} / "
          f"cache-read {tok(r['tokens_cache_read'])}")
    if r["parent_id"]:
        print(f"  parent: {r['parent_id']}")
    msgs = con.execute("SELECT count(*) FROM message WHERE session_id = ?", (sid,)).fetchone()[0]
    parts = con.execute("SELECT count(*) FROM part WHERE session_id = ?", (sid,)).fetchone()[0]
    print(f"  parts: {parts} (messages: {msgs})")
    tools = con.execute(
        "SELECT json_extract(data,'$.tool') AS t, count(*) AS c FROM part "
        "WHERE session_id = ? AND json_extract(data,'$.type') = 'tool' "
        "GROUP BY t ORDER BY c DESC LIMIT 6", (sid,)
    ).fetchall()
    if tools:
        print("  tools: " + ", ".join(f"{t['t']}×{t['c']}" for t in tools))
    kids = con.execute(
        "SELECT id,title,agent FROM session WHERE parent_id = ? LIMIT 10", (sid,)
    ).fetchall()
    for k in kids:
        print(f"  child: {k['id']} [{k['agent'] or '-'}] {(k['title'] or '')[:40]}")


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--agent")
    ap.add_argument("--parent")
    ap.add_argument("--id")
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()
    if args.id:
        show_session(args.id)
    else:
        list_sessions(args.text, args.agent, args.parent, args.limit)


if __name__ == "__main__":
    main()
