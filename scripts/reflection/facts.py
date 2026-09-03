#!/usr/bin/env python3
"""Reflection v4 — deterministic facts extractor.

Reads the opencode database inside the `opencode` container (read-only)
and emits a compact "facts pack" (JSON + markdown) about the memo project:
wave anatomy, incidents, discipline signals, distributions and outliers,
user interventions and error clusters.

This script deliberately does NOT judge. It maps; the nightly analyst
session interprets (see rules-digest.md and the cron protocol).

Usage:
  python3 facts.py --days 3 [--out facts.json] [--md facts.md]
  python3 facts.py --since 2026-08-01 --until 2026-08-20
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict

CONTAINER = "opencode"
DB = "/root/.local/share/opencode/opencode.db"
MEMO_DIR = "/root/workspace/memo"

REVIEWER_AGENTS = {
    "spec-reviewer", "code-quality-reviewer",
    "spec-review-completeness", "spec-review-consistency",
    "spec-review-feasibility", "spec-review-simplicity",
    "spec-review-best-practices",
}
CODER_AGENTS = {"frontend-coder", "backend-coder"}
CONTROLLERS = {"architect", "manager"}
TEST_RUNNERS = re.compile(r"vitest|pytest|playwright|npm test|pnpm test|npx jest", re.I)
ENV_FORENSICS = re.compile(
    r"\bsleep \d|curl[^\n]*(health|localhost|127\.0\.0\.1)|\blsof\b|"
    r"pkill|kill -9|nc -z|wait-for-it|stale.{0,12}pid",
    re.I,
)
IMPL_EXT = re.compile(r"\.(ts|tsx|js|jsx|py|css|scss|html|sql|go|rs)$", re.I)


# ---------------------------------------------------------------- infra

def q(sql: str) -> list[dict]:
    cmd = ["docker", "exec", CONTAINER, "sqlite3", "-json",
           "-cmd", ".timeout 30000", f"file:{DB}?mode=ro", sql]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(f"sqlite3 failed: {res.stderr[:400]}")
    out = res.stdout.strip()
    return json.loads(out) if out else []


def chunk(ids, size=150):
    for i in range(0, len(ids), size):
        yield ids[i:i + size]


def in_list(ids) -> str:
    return ",".join("'" + i.replace("'", "''") + "'" for i in ids)


def human_dur(sec) -> str:
    sec = int(sec or 0)
    if sec < 90:
        return f"{sec}s"
    if sec < 5400:
        return f"{sec // 60}m"
    return f"{sec / 3600:.1f}h"


def fmt_tok(n) -> str:
    n = int(n or 0)
    return f"{n / 1000:.0f}k" if n >= 1000 else str(n)


def trunc(s, n=160):
    s = (s or "").replace("\n", " ⏎ ")
    return s[:n] + ("…" if len(s) > n else "")


# ---------------------------------------------------------------- collect

def collect(since_ms: int, until_ms: int) -> dict:
    raw: dict = {}

    rows = q(
        f"SELECT id, parent_id, agent, title, time_created, time_updated, "
        f"tokens_input, tokens_output, tokens_cache_read, cost, model, "
        f"summary_additions, summary_deletions, summary_files "
        f"FROM session WHERE directory='{MEMO_DIR}' "
        f"AND time_created >= {since_ms} AND time_created < {until_ms} "
        f"ORDER BY time_created ASC"
    )
    S = {}
    for r in rows:
        r["dur_s"] = max(0, (r["time_updated"] or r["time_created"]) - r["time_created"]) / 1000
        r["tok"] = (r["tokens_input"] or 0) + (r["tokens_output"] or 0)
        r["tool_calls"] = 0
        r["errors"] = 0
        S[r["id"]] = r
    raw["sessions"] = S
    all_ids = list(S)
    root_ids = [i for i, s in S.items() if not s["parent_id"]]
    raw["root_ids"] = root_ids

    # tool-call aggregates
    agg: dict[str, Counter] = defaultdict(Counter)
    first_tool: dict[str, tuple] = {}
    for ids in chunk(all_ids):
        for r in q(
            f"SELECT p.session_id sid, json_extract(p.data,'$.tool') tool, "
            f"json_extract(p.data,'$.state.status') st, count(*) c, "
            f"min(m.time_created) first_at "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE p.session_id IN ({in_list(ids)}) "
            f"AND json_extract(p.data,'$.type')='tool' GROUP BY 1,2,3"
        ):
            agg[r["sid"]][f"{r['tool']}:{r['st']}"] += r["c"]
            ft = first_tool.get(r["sid"])
            if not ft or r["first_at"] < ft[0]:
                first_tool[r["sid"]] = (r["first_at"], r["tool"])
    for sid, c in agg.items():
        if sid in S:
            S[sid]["tool_calls"] = sum(c.values())
            S[sid]["errors"] = sum(v for k, v in c.items() if k.endswith(":error"))
            S[sid]["tools"] = dict(c)
    raw["first_tool"] = first_tool

    # bash commands
    bash: dict[str, list] = defaultdict(list)
    for ids in chunk(all_ids):
        for r in q(
            f"SELECT p.session_id sid, m.time_created at, "
            f"json_extract(p.data,'$.state.input.command') cmd "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE p.session_id IN ({in_list(ids)}) "
            f"AND json_extract(p.data,'$.tool')='bash' ORDER BY m.time_created"
        ):
            if r.get("cmd"):
                bash[r["sid"]].append((r["at"], r["cmd"]))
    raw["bash"] = bash

    # file edits
    edits: dict[str, list] = defaultdict(list)
    for ids in chunk(all_ids):
        for r in q(
            f"SELECT p.session_id sid, m.time_created at, "
            f"json_extract(p.data,'$.state.input.filePath') fp "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE p.session_id IN ({in_list(ids)}) "
            f"AND json_extract(p.data,'$.tool') IN ('edit','write') "
            f"ORDER BY m.time_created"
        ):
            if r.get("fp"):
                edits[r["sid"]].append((r["at"], r["fp"]))
    raw["edits"] = edits

    # final text per session
    final_text: dict[str, dict] = {}
    for ids in chunk(all_ids):
        for r in q(
            f"SELECT sid, at, txt FROM ("
            f"SELECT p.session_id sid, m.time_created at, "
            f"substr(json_extract(p.data,'$.text'),1,400) txt, "
            f"row_number() OVER (PARTITION BY p.session_id "
            f"ORDER BY m.time_created DESC, p.id DESC) rn "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE p.session_id IN ({in_list(ids)}) "
            f"AND json_extract(p.data,'$.type')='text') WHERE rn=1"
        ):
            final_text[r["sid"]] = r
    raw["final_text"] = final_text

    # user messages in root sessions
    user_msgs: list[dict] = []
    for ids in chunk(root_ids):
        user_msgs.extend(q(
            f"SELECT m.session_id sid, m.time_created at, "
            f"substr(json_extract(p.data,'$.text'),1,600) txt "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE m.session_id IN ({in_list(ids)}) "
            f"AND json_extract(m.data,'$.role')='user' "
            f"AND json_extract(p.data,'$.type')='text' "
            f"AND length(json_extract(p.data,'$.text'))>0"
        ))
    raw["user_msgs"] = [
        u for u in user_msgs if not u["txt"].startswith(("<", "[", "task_id:", "Caveat:"))
    ]

    # pty-exit endings
    pty_end: dict[str, int] = {}
    for ids in chunk(all_ids):
        for r in q(
            f"SELECT p.session_id sid, max(m.time_created) at "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE p.session_id IN ({in_list(ids)}) "
            f"AND json_extract(p.data,'$.type')='text' "
            f"AND json_extract(p.data,'$.text') LIKE '<pty_exited>%' GROUP BY 1"
        ):
            pty_end[r["sid"]] = r["at"]
    raw["pty_end"] = pty_end

    # error outputs (cluster material)
    err_rows: list[dict] = []
    for ids in chunk(all_ids):
        err_rows.extend(q(
            f"SELECT p.session_id sid, json_extract(p.data,'$.tool') tool, "
            f"substr(ifnull(json_extract(p.data,'$.state.output'), "
            f"ifnull(json_extract(p.data,'$.state.error'), "
            f"json(json_extract(p.data,'$.state.input')))),1,200) out "
            f"FROM part p JOIN message m ON m.id=p.message_id "
            f"WHERE p.session_id IN ({in_list(ids)}) "
            f"AND json_extract(p.data,'$.state.status')='error'"
        ))
    raw["err_rows"] = err_rows
    return raw


# ---------------------------------------------------------------- analyze

def subtree(roots: list[str], S: dict) -> dict[str, list[str]]:
    children: dict[str, list[str]] = defaultdict(list)
    for s in S.values():
        if s["parent_id"]:
            children[s["parent_id"]].append(s["id"])
    out = {}
    for r in roots:
        seen, stack = [], [r]
        while stack:
            cur = stack.pop()
            seen.append(cur)
            stack.extend(children.get(cur, []))
        out[r] = seen
    return out


def analyze(raw: dict) -> dict:
    S = raw["sessions"]
    bash, edits = raw["bash"], raw["edits"]
    ft, pty_end = raw["final_text"], raw["pty_end"]
    first_tool = raw["first_tool"]
    A: dict = {"incidents": [], "signals": {}, "waves": [], "distrib": {},
               "error_clusters": [], "user_interventions": []}

    # waves
    waves = []
    for rid, members in subtree(raw["root_ids"], S).items():
        root = S[rid]
        kids = [S[m] for m in members if m != rid]
        by_agent = Counter(k["agent"] or "?" for k in kids)
        waves.append({
            "root": rid, "title": root["title"], "started": root["time_created"],
            "n_children": len(kids), "by_agent": dict(by_agent),
            "tok": root["tok"] + sum(k["tok"] for k in kids),
            "cache": (root["tokens_cache_read"] or 0) + sum(k["tokens_cache_read"] or 0 for k in kids),
            "dur_s": max([root["dur_s"]] + [k["dur_s"] for k in kids] or [0]),
            "members": members,
        })
    waves.sort(key=lambda w: w["started"])
    A["waves"] = waves

    # incidents
    inc = A["incidents"]
    now_ms = max(s["time_updated"] or 0 for s in S.values() if s["time_updated"])

    def pty_wait_abandoned(sid: str, final: str) -> bool:
        """Session's LAST words are the pty notification itself → the agent
        ended its turn waiting and never returned to interpret the exit.
        (If the agent had returned, its report would be the final text part.)
        Skips still-live sessions (updated < 6h ago)."""
        if not final.startswith("<pty_exited>"):
            return False
        s = S[sid]
        return (now_ms - (s["time_updated"] or 0)) > 6 * 3600 * 1000

    for sid, s in S.items():
        sub = bool(s["parent_id"])
        final = ft.get(sid, {}).get("txt") or ""
        interrupted = "You were interrupted" in final
        if sub and s["tool_calls"] > 0 and s["dur_s"] > 120 and (not final.strip() or interrupted):
            inc.append({"type": "DEAD_SUBAGENT" + ("(interrupted)" if interrupted else ""),
                        "sid": sid, "agent": s["agent"], "title": s["title"],
                        "dur_s": s["dur_s"], "tok": s["tok"], "final": final[:200]})
        if sub and s["tool_calls"] == 0 and s["tok"] < 500 and s["dur_s"] < 300:
            inc.append({"type": "SPAWN_DEATH", "sid": sid, "agent": s["agent"],
                        "title": s["title"], "dur_s": s["dur_s"], "tok": s["tok"], "final": ""})
        if sid in pty_end and pty_wait_abandoned(sid, final):
            inc.append({"type": "PTY_WAIT_END", "sid": sid, "agent": s["agent"],
                        "title": s["title"], "dur_s": s["dur_s"], "tok": s["tok"], "final": final[:200]})
        for marker in ("TEST_TIMEOUT", "ENV_BLOCKED"):
            if marker in final:
                inc.append({"type": marker, "sid": sid, "agent": s["agent"],
                            "title": s["title"], "dur_s": s["dur_s"], "tok": s["tok"],
                            "final": final[:200]})

    # discipline signals
    sig: dict[str, list] = defaultdict(list)

    # stuck-in-retry: same cmd >= 3× in one session
    for sid, cmds in bash.items():
        norm = Counter(c.strip() for _, c in cmds)
        for cmd, n in norm.items():
            if n >= 3 and len(cmd) > 8:
                sig["stuck_retry"].append({"sid": sid, "n": n, "cmd": trunc(cmd, 120)})
                break

    # env-forensics in coder sessions (before first edit)
    for sid, s in S.items():
        if s["agent"] not in CODER_AGENTS:
            continue
        e_times = [t for t, _ in edits.get(sid, [])]
        cutoff = min(e_times) if e_times else None
        hits = [c for at, c in bash.get(sid, [])
                if ENV_FORENSICS.search(c) and (cutoff is None or at < cutoff)]
        if len(hits) >= 3:
            sig["env_forensics"].append({"sid": sid, "n_cmds": len(hits),
                                         "examples": [trunc(h, 100) for h in hits[:3]]})

    # salvage ladder usage
    audit_calls = [(sid, at) for sid, cmds in bash.items()
                   for at, c in cmds if "subagent-audit.py" in c]
    A["salvage_audit_calls"] = [{"sid": sid} for sid, _ in audit_calls]

    # TDD order in coder sessions
    for sid, s in S.items():
        if s["agent"] not in CODER_AGENTS:
            continue
        e_times = [t for t, _ in edits.get(sid, [])]
        t_times = [at for at, c in bash.get(sid, []) if TEST_RUNNERS.search(c)]
        if e_times and (not t_times or min(e_times) < min(t_times)):
            sig["code_before_test"].append({"sid": sid, "n_edits": len(e_times),
                                            "n_test_runs": len(t_times)})

    # review discipline per parent
    children_by_parent: dict[str, list] = defaultdict(list)
    for s in S.values():
        if s["parent_id"]:
            children_by_parent[s["parent_id"]].append(s)
    task_label = re.compile(r"(?:task|T)\s*#?(\d+)", re.I)
    for pid, kids in children_by_parent.items():
        impl = [k for k in kids if k["agent"] in CODER_AGENTS]
        revs = [k for k in kids if k["agent"] in REVIEWER_AGENTS]
        impl_diff = sum((k["summary_additions"] or 0) + (k["summary_deletions"] or 0) for k in impl)
        if impl and not revs:
            sig["implementers_without_review"].append(
                {"parent": pid, "n_impl": len(impl), "impl_diff_lines": impl_diff,
                 "agents": sorted({k["agent"] for k in impl})})
        # review iterations are PER TASK, not per parent: group reviewer
        # dispatches by task label in the title ("Spec review T7 …"); unlabeled
        # dispatches each count as their own group.
        groups: dict[tuple, int] = defaultdict(int)
        for k in revs:
            m = task_label.search(k["title"] or "")
            key = (k["agent"], m.group(1) if m else k["title"] or "?")
            groups[key] += 1
        for (agent, label), n in groups.items():
            if n > 3:
                sig["review_loop_over_limit"].append(
                    {"parent": pid, "agent": agent, "task": label, "n": n})

    # controller-never-implements
    for sid, s in S.items():
        if s["agent"] not in CONTROLLERS:
            continue
        bad = [fp for _, fp in edits.get(sid, []) if IMPL_EXT.search(fp)]
        if bad:
            sig["controller_implements"].append({"sid": sid, "agent": s["agent"],
                                                 "files": [fp.split("/")[-1] for fp in bad[:5]]})

    A["signals"] = dict(sig)

    # distributions & outliers (waves)
    toks = [w["tok"] for w in waves if w["tok"] > 0]
    if toks:
        med = statistics.median(toks)
        A["distrib"]["wave_tokens"] = {
            "n": len(toks), "median": int(med),
            "p90": int(sorted(toks)[int(len(toks) * 0.9)]),
            "outliers": [
                {"root": w["root"], "title": trunc(w["title"], 80), "tok": w["tok"],
                 "x_median": round(w["tok"] / med, 1), "dur": human_dur(w["dur_s"]),
                 "n_children": w["n_children"]}
                for w in waves if w["tok"] > 2 * med
            ],
        }
    durs = [w["dur_s"] for w in waves if w["dur_s"] > 60]
    if durs:
        med = statistics.median(durs)
        A["distrib"]["wave_dur_s"] = {"n": len(durs), "median": int(med),
                                      "p90": int(sorted(durs)[int(len(durs) * 0.9)])}

    # error clusters (same tool+prefix across >= 3 sessions)
    cluster = Counter()
    for e in raw["err_rows"]:
        key = (e["tool"], trunc((e.get("out") or "unknown").replace("\n", " "), 60))
        cluster[key] += 1
    sess_by_cluster: dict = defaultdict(set)
    for e in raw["err_rows"]:
        key = (e["tool"], trunc((e.get("out") or "unknown").replace("\n", " "), 60))
        sess_by_cluster[key].add(e["sid"])
    A["error_clusters"] = [
        {"tool": t, "sample": s, "n": n, "n_sessions": len(sess_by_cluster[(t, s)])}
        for (t, s), n in cluster.most_common(10)
        if len(sess_by_cluster[(t, s)]) >= 2
    ]

    # user interventions
    A["user_interventions"] = sorted(raw["user_msgs"], key=lambda u: u["at"])
    return A


# ---------------------------------------------------------------- emit

def emit_md(raw: dict, A: dict, since: dt.datetime, until: dt.datetime) -> str:
    S = raw["sessions"]
    L: list[str] = []
    tok_in = sum(s["tokens_input"] or 0 for s in S.values())
    tok_out = sum(s["tokens_output"] or 0 for s in S.values())
    cache = sum(s["tokens_cache_read"] or 0 for s in S.values())
    n_sub = sum(1 for s in S.values() if s["parent_id"])
    L.append(f"# Facts pack — {since:%Y-%m-%d} → {until:%Y-%m-%d}")
    L.append(f"Сессий: {len(S)} (root {len(raw['root_ids'])}, subagents {n_sub}) · "
             f"токены in {fmt_tok(tok_in)} / out {fmt_tok(tok_out)} / cache-read {fmt_tok(cache)}")
    L.append("")
    L.append(f"## Волны ({len(A['waves'])})")
    L.append("| root | старт | дети (по агентам) | токены | длительность |")
    L.append("|---|---|---|---|---|")
    for w in A["waves"]:
        agents = ", ".join(f"{a}×{n}" for a, n in sorted(w["by_agent"].items()))
        t = dt.datetime.fromtimestamp(w["started"] / 1000).strftime("%m-%d %H:%M")
        L.append(f"| {trunc(w['title'], 60)} | {t} | {w['n_children']}: {agents} | "
                 f"{fmt_tok(w['tok'])} | {human_dur(w['dur_s'])} |")
    L.append("")
    L.append(f"## Инциденты ({len(A['incidents'])})")
    for i in A["incidents"]:
        L.append(f"- **{i['type']}** `{i['sid']}` ({i['agent']}, {human_dur(i['dur_s'])}, "
                 f"{fmt_tok(i['tok'])} tok) — {trunc(i['title'], 70)} · final: {trunc(i['final'], 100)}")
    if not A["incidents"]:
        L.append("- (нет)")
    L.append("")
    L.append("## Дисциплина (детерминированные сигналы)")
    for name, label in [("stuck_retry", "Одна команда ≥3× (stuck-in-retry)"),
                        ("env_forensics", "Env-forensics у кодеров до первого edit"),
                        ("code_before_test", "Edit раньше первого запуска тестов (TDD)"),
                        ("implementers_without_review", "Имплементеры без ревьюеров в волне"),
                        ("review_loop_over_limit", "Review-петля > 3 итераций"),
                        ("controller_implements", "Контроллер правил код")]:
        items = A["signals"].get(name, [])
        L.append(f"- **{label}**: {len(items)}")
        for it in items[:8]:
            L.append(f"  - `{it.get('sid', it.get('parent'))}` {trunc(json.dumps(it, ensure_ascii=False), 180)}")
    audits = A.get("salvage_audit_calls", [])
    L.append(f"- **subagent-audit.py вызовов**: {len(audits)}"
             + (f" в сессиях {sorted({a['sid'] for a in audits})[:5]}" if audits else ""))
    L.append("")
    d = A["distrib"]
    if "wave_tokens" in d:
        w = d["wave_tokens"]
        L.append(f"## Распределения: волна-токены median {fmt_tok(w['median'])}, "
                 f"p90 {fmt_tok(w['p90'])}, выбросов (>2×median): {len(w['outliers'])}")
        for o in w["outliers"][:8]:
            L.append(f"- {o['x_median']}× median — {fmt_tok(o['tok'])} tok, {o['dur']} — "
                     f"`{o['root']}` {o['title']}")
    if "wave_dur_s" in d:
        L.append(f"Длительность волн: median {human_dur(d['wave_dur_s']['median'])}, "
                 f"p90 {human_dur(d['wave_dur_s']['p90'])}")
    L.append("")
    L.append(f"## Кластеры ошибок ({len(A['error_clusters'])})")
    for c in A["error_clusters"][:8]:
        L.append(f"- `{c['tool']}` ×{c['n']} в {c['n_sessions']} сесс.: {trunc(c['sample'], 100)}")
    if not A["error_clusters"]:
        L.append("- (нет значимых)")
    L.append("")
    L.append(f"## Вмешательства пользователя ({len(A['user_interventions'])})")
    for u in A["user_interventions"][:15]:
        t = dt.datetime.fromtimestamp(u["at"] / 1000).strftime("%m-%d %H:%M")
        L.append(f"- {t} `{u['sid']}`: {trunc(u['txt'], 200)}")
    L.append("")
    L.append("## Топ-сессий по токенам (для drill-down)")
    for s in sorted(S.values(), key=lambda x: -x["tok"])[:12]:
        L.append(f"- `{s['id']}` {s['agent'] or 'root'} {fmt_tok(s['tok'])} tok "
                 f"{human_dur(s['dur_s'])} — {trunc(s['title'], 70)}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--since", type=str, default=None)
    ap.add_argument("--until", type=str, default=None)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--md", type=str, default=None)
    args = ap.parse_args()

    until_dt = dt.datetime.fromisoformat(args.until) if args.until else dt.datetime.now()
    since_dt = (dt.datetime.fromisoformat(args.since) if args.since
                else until_dt - dt.timedelta(days=args.days))
    since_ms, until_ms = int(since_dt.timestamp() * 1000), int(until_dt.timestamp() * 1000)

    print(f"[facts] window {since_dt:%Y-%m-%d %H:%M} → {until_dt:%Y-%m-%d %H:%M}",
          file=sys.stderr)
    raw = collect(since_ms, until_ms)
    A = analyze(raw)

    pack = {
        "window": {"since": since_dt.isoformat(), "until": until_dt.isoformat()},
        "n_sessions": len(raw["sessions"]),
        "waves": A["waves"], "incidents": A["incidents"], "signals": A["signals"],
        "salvage_audit_calls": A["salvage_audit_calls"], "distrib": A["distrib"],
        "error_clusters": A["error_clusters"],
        "user_interventions": A["user_interventions"],
        "sessions": [{k: s.get(k) for k in
                      ("id", "parent_id", "agent", "title", "time_created", "dur_s",
                       "tok", "tokens_cache_read", "tool_calls", "errors", "cost",
                       "summary_additions", "summary_deletions", "summary_files")}
                     for s in raw["sessions"].values()],
        "bash": raw["bash"], "edits": raw["edits"], "final_text": raw["final_text"],
        "first_tool": raw["first_tool"],
    }
    md = emit_md(raw, A, since_dt, until_dt)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(pack, f, ensure_ascii=False, indent=1)
        print(f"[facts] JSON → {args.out}", file=sys.stderr)
    if args.md:
        with open(args.md, "w") as f:
            f.write(md)
        print(f"[facts] MD → {args.md}", file=sys.stderr)
    if not args.out and not args.md:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
