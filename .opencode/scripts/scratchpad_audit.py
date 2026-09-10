#!/usr/bin/env python3
"""scratchpad_audit.py — Scratchpad Discipline v2 sanitizer (report-only by default).

Why: the scratchpad accumulates finished trajectories, stale triggers and dead
policies. v2 keeps it lean — DESIGN writes nothing; an IMPL/FasTP section lives
while its worktree exists; finishing collapses it into one "## Recently merged"
line. This script finds what can be collapsed safely and what needs the user.

Findings (AUTO_SAFE — written only with --apply):
  [a] idle-collapse      section headed "## ses_<id>: Idle." with body content
                         -> collapse to the header line.
  [b] duplicate-session  the same ses_<id> in 2+ section headers -> keep the
                         newest (last) occurrence, delete the earlier ones —
                         only when the kept section self-declares Idle.
  [c] stale item         a PENDING/awaiting/RESUME/TRIGGER line whose #refs are
                         all complete (PR merged / issue closed per gh)
                         -> delete the line.
  [d] expired policy     block whose header carries a past date + a RESOLVED
                         marker -> keep the header + the RESOLVED line(s).
  [e] closed follow-up   "## Follow-ups" block entry whose #refs are all
                         complete -> delete the entry line.

NEEDS_USER (reported, never applied):
  [f] a referenced path that no longer exists on disk.
  [g] non-Idle session section with no DB activity > 7 days (suggestion).
  [h] a stale item ([c]/[e] condition) inside a non-Idle section — the section
      is live, so it is never touched automatically.

SKIP (concurrency guard): a section is skipped when it contains today's date,
or — session sections — when the session was active today per the opencode DB,
or is absent from the DB (freshness unknown). Blocks have no single live
writer, so only the date check applies to them.

Safety: AUTO_SAFE never touches a non-Idle session section; default mode is
report only; --apply first backs the file up to "<name>.bak-YYYYMMDD-HHMM".
gh lookups are cached; any failure counts as unverified, and unverified items
are never deleted.

Usage (from the repo root):
    python3 .opencode/scripts/scratchpad_audit.py [--apply] [--file PATH]
              [--repo PATH] [--no-network] [--no-db] [--today YYYY-MM-DD]

DB (default): ~/.local/share/opencode/opencode.db  (override: $OPENCODE_DB)
"""
import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = os.environ.get("OPENCODE_DB", str(Path.home() / ".local/share/opencode/opencode.db"))
KEYWORDS = re.compile(r"\b(PENDING|awaiting|RESUME|TRIGGER)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REF_RE = re.compile(r"#(\d+)")
SESSION_RE = re.compile(r"ses_\w+")
PROTECTED_BLOCK = "## recently merged"

ABS_PREFIXES = ("/root/", "/tmp/", "/home/", "~/")
REL_PREFIXES = ("docs/", ".opencode/", ".zcode/", "frontend/", "backend/",
                "packages/", "scripts/", ".worktrees/", "worktrees/")


# ---------------------------------------------------------------- model

class Section:
    """A level-2 ("## ") section: header + body (trailing blanks excluded)."""

    def __init__(self, start: int, end: int, lines: list[str]):
        self.start = start          # index of the header line
        self.end = end              # last non-blank line >= start (== start if empty)
        self.header = lines[start]
        self.lines = lines[start:end + 1]
        self.body = lines[start + 1:end + 1]
        self.sid = SESSION_RE.search(self.header).group(0) \
            if self.header.lstrip().startswith("## ses_") else None
        self.idle = bool(re.search(r"\bIdle\.", self.header))
        self.is_followups = "follow-up" in self.header.lower()
        self.is_protected = self.header.strip().lower() == PROTECTED_BLOCK
        self.is_policy = bool(DATE_RE.search(self.header))
        self.body_nonblank = [ln for ln in self.body if ln.strip()]


def parse_sections(lines: list[str]) -> list[Section]:
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    sections = []
    for n, h in enumerate(heads):
        limit = heads[n + 1] - 1 if n + 1 < len(heads) else len(lines) - 1
        end = h
        for i in range(limit, h, -1):
            if lines[i].strip():
                end = i
                break
        sections.append(Section(h, end, lines))
    return sections


# ---------------------------------------------------------------- refs / gh

class RefChecker:
    """Cached #N -> 'merged'|'closed'|'open'|'unverified' resolver."""

    def __init__(self, repo_root: Path, network: bool):
        self.repo_root = repo_root
        self.network = network
        self.cache: dict[int, str] = {}

    def state(self, number: int) -> str:
        if number in self.cache:
            return self.cache[number]
        if not self.network:
            self.cache[number] = "unverified"
            return "unverified"
        st = self._try(["gh", "pr", "view", str(number), "--json", "state", "-q", ".state"])
        if st is None:
            st = self._try(["gh", "issue", "view", str(number), "--json", "state", "-q", ".state"])
        self.cache[number] = st or "unverified"
        return self.cache[number]

    def _try(self, cmd: list[str]) -> str | None:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=self.repo_root, timeout=25)
        except Exception:
            return None
        if r.returncode != 0:
            return None
        s = r.stdout.strip().lower()
        return {"merged": "merged", "closed": "closed", "open": "open"}.get(s)

    def refs(self, line: str) -> list[int]:
        return sorted({int(n) for n in REF_RE.findall(line)})

    def verdict(self, line: str) -> tuple[str, list[tuple[int, str]]]:
        """('all_complete'|'partial'|'open'|'none'|'unverified', [(n, state)])"""
        refs = self.refs(line)
        if not refs:
            return "none", []
        states = [(n, self.state(n)) for n in refs]
        complete = [s for _, s in states if s in ("merged", "closed")]
        if len(complete) == len(states):
            return "all_complete", states
        if complete:
            return "partial", states
        if all(s == "unverified" for _, s in states):
            return "unverified", states
        return "open", states


# ---------------------------------------------------------------- db

class DB:
    def __init__(self, enabled: bool):
        self.conn = None
        self.available = False
        if not enabled or not Path(DB_PATH).exists():
            return
        try:
            self.conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=15)
            self.conn.execute("PRAGMA busy_timeout = 15000")
            self.available = True
        except Exception:
            self.conn = None
        self.cache: dict[str, date | None] = {}

    def last_activity(self, sid: str) -> date | None:
        """Date of the session's last DB activity; None when unknown/absent."""
        if not self.available:
            return None
        if sid in self.cache:
            return self.cache[sid]
        try:
            row = self.conn.execute(
                "SELECT time_updated FROM session WHERE id = ?", (sid,)).fetchone()
        except Exception:
            row = None
        val = datetime.fromtimestamp(row[0] / 1000).date() if row and row[0] else None
        self.cache[sid] = val
        return val

    def known_missing(self, sid: str) -> bool:
        if not self.available:
            return False
        self.last_activity(sid)  # prime cache
        try:
            row = self.conn.execute("SELECT 1 FROM session WHERE id = ?", (sid,)).fetchone()
        except Exception:
            return False
        return row is None


# ---------------------------------------------------------------- audit

def path_candidates(line: str) -> list[str]:
    out = []
    for tok in re.findall(r"[^\s`\"'()\[\]{}«»]+", line):
        t = tok.rstrip(".,;:!?—–")
        if len(t) < 5 or "/" not in t or t.startswith(("http://", "https://")):
            continue
        if any(ch in t for ch in "<>*=$…"):
            continue
        if "YYYY" in t or "..." in t:
            continue
        if not (t.startswith(ABS_PREFIXES) or t.startswith(REL_PREFIXES)):
            continue
        out.append(t)
    return out


def audit(sections: list[Section], all_lines: list[str], repo: Path, refs: RefChecker,
          db: DB, today: date):
    """Return (ops, needs_user, skipped) where ops are dicts of edits to apply."""
    ops: list[dict] = []
    needs_user: list[str] = []
    skipped: list[tuple[Section, str]] = []
    section_ops: set[int] = set()
    skip_cache: dict[int, tuple[bool, str]] = {}

    def skip_status(i: int, sec: Section) -> tuple[bool, str]:
        if i in skip_cache:
            return skip_cache[i]
        text = "\n".join(sec.lines)
        if today.strftime("%F") in text:
            res = (True, "contains today's date")
        elif sec.sid and db.available:
            if db.known_missing(sec.sid):
                res = (True, "session absent from DB (freshness unknown)")
            elif db.last_activity(sec.sid) == today:
                res = (True, "session active today (DB)")
            else:
                res = (False, "")
        else:
            res = (False, "")
        skip_cache[i] = res
        if res[0]:
            skipped.append((sec, res[1]))
        return res

    # [b] duplicate session sections ------------------------------------
    by_id: dict[str, list[int]] = {}
    for i, sec in enumerate(sections):
        if sec.sid:
            by_id.setdefault(sec.sid, []).append(i)
    for sid, idxs in by_id.items():
        if len(idxs) < 2:
            continue
        kept = idxs[-1]
        if not sections[kept].idle:
            needs_user.append(
                f"{sections[kept].start + 1}: duplicate sections for {sid} — newest is "
                f"NOT Idle (session active?); resolve manually")
            continue
        if skip_status(kept, sections[kept])[0]:
            continue
        for i in idxs[:-1]:
            if skip_status(i, sections[i])[0]:
                needs_user.append(
                    f"{sections[i].start + 1}: duplicate section {sid} updated today — left alone")
                continue
            ops.append({"kind": "b", "section": i})
            section_ops.add(i)

    # [a] idle collapse, [c] stale items, [e] follow-ups, [d] policy ----
    for i, sec in enumerate(sections):
        if i in section_ops or sec.is_protected:
            continue
        blocked, _reason = skip_status(i, sec)
        eligible = (not blocked) and (sec.sid is None or sec.idle)

        if sec.sid is None and sec.is_policy and eligible:
            dates = [d for d in DATE_RE.findall(sec.header)]
            keep = [j for j in range(sec.start + 1, sec.end + 1)
                    if "RESOLVED" in all_lines[j]]
            if dates and max(dates) < today.strftime("%F") and keep \
                    and len(keep) < len(sec.body_nonblank):
                ops.append({"kind": "d", "section": i, "keep": keep})
                section_ops.add(i)
                continue

        for j in range(sec.start + 1, sec.end + 1):
            line = all_lines[j]
            if KEYWORDS.search(line) and REF_RE.search(line):
                verdict, states = refs.verdict(line)
                if verdict == "all_complete":
                    if not eligible:
                        needs_user.append(
                            f"{j + 1}: stale item in non-Idle section ({_fmt_states(states)}): "
                            f"{_short(line)}")
                    elif sec.sid is None:
                        ops.append({"kind": "c", "line": j, "states": states})
                    # an Idle section with a body is collapsed wholesale by [a]
                elif verdict == "partial" and not eligible:
                    needs_user.append(
                        f"{j + 1}: partially completed refs ({_fmt_states(states)}): {_short(line)}")
            if sec.is_followups and line.lstrip().startswith(("- ", "* ")) \
                    and REF_RE.search(line):
                verdict, states = refs.verdict(line)
                if verdict == "all_complete":
                    if eligible:
                        ops.append({"kind": "e", "line": j, "states": states})
                    else:
                        needs_user.append(
                            f"{j + 1}: closed follow-up in non-Idle section "
                            f"({_fmt_states(states)}): {_short(line)}")

        # [a] idle collapse (wholesale; only when no narrower op applied)
        if i not in section_ops and sec.sid and sec.idle and sec.body_nonblank \
                and not blocked:
            ops.append({"kind": "a", "section": i})
            section_ops.add(i)

    # [f] dead paths -----------------------------------------------------
    seen_paths: set[str] = set()
    for j, line in enumerate(all_lines):
        for t in path_candidates(line):
            if t in seen_paths:
                continue
            seen_paths.add(t)
            target = Path(t).expanduser() if t.startswith(ABS_PREFIXES) \
                else repo / t
            if not target.exists():
                needs_user.append(f"{j + 1}: path not on disk: {t}")

    # [g] stale non-Idle sessions ----------------------------------------
    if db.available:
        cutoff = today - timedelta(days=7)
        for i, sec in enumerate(sections):
            if not sec.sid or sec.idle or sec.is_protected:
                continue
            if skip_cache.get(i, (False, ""))[0]:
                continue
            la = db.last_activity(sec.sid)
            if la and la < cutoff:
                needs_user.append(
                    f"{sec.start + 1}: non-Idle section {sec.sid} — no DB activity "
                    f"since {la.strftime('%F')} (>7 days); candidate for manual removal")

    return ops, needs_user, skipped, section_ops


def _fmt_states(states: list[tuple[int, str]]) -> str:
    return " ".join(f"#{n}={s}" for n, s in states)


def _short(text: str, n: int = 90) -> str:
    t = " ".join(text.split())
    return t[:n] + ("…" if len(t) > n else "")


# ---------------------------------------------------------------- apply

def apply_ops(lines: list[str], ops: list[dict], sections: list[Section]) -> list[str]:
    deleted: set[int] = set()
    for op in ops:
        if op["kind"] == "a":
            sec = sections[op["section"]]
            deleted.update(range(sec.start + 1, sec.end + 1))
        elif op["kind"] == "b":
            sec = sections[op["section"]]
            deleted.update(range(sec.start, sec.end + 1))
        elif op["kind"] == "c" or op["kind"] == "e":
            deleted.add(op["line"])
        elif op["kind"] == "d":
            sec = sections[op["section"]]
            keep = set(op["keep"])
            deleted.update(j for j in range(sec.start + 1, sec.end + 1) if j not in keep)

    out: list[str] = []
    prev_blank = False
    for i, line in enumerate(lines):
        if i in deleted:
            continue
        blank = not line.strip()
        if blank and prev_blank:
            continue            # collapse blank runs left by deletions
        out.append(line)
        prev_blank = blank
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Scratchpad v2 sanitizer (report-only by default)")
    ap.add_argument("--apply", action="store_true", help="write changes (backs up first)")
    ap.add_argument("--file", help="scratchpad path (default: <repo>/.opencode/scratchpad.md)")
    ap.add_argument("--repo", help="repo root (default: derived from the script location)")
    ap.add_argument("--no-network", action="store_true", help="skip gh verification (nothing deleted on refs)")
    ap.add_argument("--no-db", action="store_true", help="skip opencode DB freshness checks")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD; testing)")
    args = ap.parse_args()

    repo = Path(args.repo).resolve() if args.repo else Path(__file__).resolve().parents[2]
    path = Path(args.file) if args.file else repo / ".opencode" / "scratchpad.md"
    if not path.exists():
        sys.exit(f"error: scratchpad not found at {path}")
    today = date.fromisoformat(args.today) if args.today else date.today()

    text = path.read_text(encoding="utf-8")
    lines = text.rstrip("\n").split("\n")
    sections = parse_sections(lines)
    refs = RefChecker(repo, network=not args.no_network)
    db = DB(enabled=not args.no_db)

    ops, needs_user, skipped, section_ops = audit(
        sections, lines, repo, refs, db, today)

    # ---------------------------------------------------------- report
    print(f"scratchpad_audit — {'APPLY' if args.apply else 'REPORT ONLY'}"
          f"{'' if args.apply else ' (use --apply to write)'}")
    print(f"file:   {path}")
    print(f"lines:  {len(lines)}   sections: {len(sections)} "
          f"(sessions {sum(1 for s in sections if s.sid)}, "
          f"blocks {sum(1 for s in sections if not s.sid)})")
    if not db.available and not args.no_db:
        print("note:   opencode DB unavailable — session freshness from date strings only")
    print(f"skipped: {len(skipped)} section(s) (concurrency guard)")

    by_kind: dict[str, list[dict]] = {}
    for op in ops:
        by_kind.setdefault(op["kind"], []).append(op)
    print()
    print(f"AUTO_SAFE findings: {len(ops)}")
    kind_label = {
        "a": "idle-collapse", "b": "duplicate-session", "c": "stale item",
        "d": "expired policy", "e": "closed follow-up",
    }
    for kind in "abcde":
        for op in by_kind.get(kind, []):
            if kind == "a":
                sec = sections[op["section"]]
                print(f"  [a] L{sec.start + 1} collapse '{_short(sec.header, 60)}' "
                      f"({len(sec.body_nonblank)} body line(s))")
            elif kind == "b":
                sec = sections[op["section"]]
                print(f"  [b] L{sec.start + 1}-{sec.end + 1} delete duplicate section "
                      f"{sec.sid} ({len(sec.lines)} line(s))")
            elif kind == "c":
                print(f"  [c] L{op['line'] + 1} delete stale item ({_fmt_states(op['states'])}) "
                      f"{_short(lines[op['line']])}")
            elif kind == "d":
                sec = sections[op["section"]]
                print(f"  [d] L{sec.start + 1}-{sec.end + 1} expired policy — keep header + "
                      f"{len(op['keep'])} RESOLVED line(s)")
            elif kind == "e":
                print(f"  [e] L{op['line'] + 1} delete closed follow-up ({_fmt_states(op['states'])}) "
                      f"{_short(lines[op['line']])}")

    print()
    print(f"NEEDS_USER: {len(needs_user)}")
    for item in needs_user:
        print(f"  - {item}")

    print()
    for sec, reason in skipped:
        label = sec.sid or _short(sec.header, 50)
        print(f"SKIP L{sec.start + 1} {label}: {reason}")

    # ---------------------------------------------------------- apply
    if args.apply:
        if not ops:
            print("\nnothing to apply.")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        backup = path.with_name(f"{path.name}.bak-{stamp}")
        shutil.copy2(path, backup)
        new_lines = apply_ops(lines, ops, sections)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print()
        print(f"applied {len(ops)} change(s); lines: {len(lines)} -> {len(new_lines)}")
        print(f"backup: {backup}")
    elif ops:
        print()
        print("report only — re-run with --apply to write (a .bak backup is made first).")


if __name__ == "__main__":
    main()
