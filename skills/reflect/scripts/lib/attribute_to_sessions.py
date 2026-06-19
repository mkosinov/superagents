"""File → sessions attribution via git log + path matching."""
from __future__ import annotations
import subprocess
from pathlib import Path


def match_session_to_path(session: dict, repo_path: str | Path) -> bool:
    """True if session.path matches repo_path."""
    session_path = session.get("path") or ""
    return str(repo_path) in session_path or session_path.startswith(str(repo_path))


def get_git_commits_for_file(repo_path: Path, file: str) -> list[dict]:
    """Run `git log` for a file, return list of {sha, time_ms, author}."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H|%ct|%an", "--", file],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            sha, time_unix, author = parts
            commits.append({
                "sha": sha,
                "time_ms": int(time_unix) * 1000,
                "author": author,
            })
    return commits


def find_sessions_for_file(
    *,
    sessions: list[dict],
    target_file: str,
    repo_path: Path,
    window_ms: int = 24 * 60 * 60 * 1000,
) -> list[dict]:
    """Find sessions that likely touched target_file.

    Algorithm:
      1. git log target_file → list of commits with timestamps
      2. for each commit, find session(s) where:
         - session.path matches repo_path
         - session.time_created within ±window_ms of commit time
    """
    commits = get_git_commits_for_file(repo_path, target_file)
    if not commits:
        return []
    matching = []
    seen = set()
    for commit in commits:
        ct = commit["time_ms"]
        for s in sessions:
            if s["id"] in seen:
                continue
            if not match_session_to_path(s, repo_path):
                continue
            if abs(s["time_created"] - ct) > window_ms:
                continue
            if abs(s["time_updated"] - ct) > window_ms:
                continue
            matching.append({**s, "matched_commit": commit["sha"]})
            seen.add(s["id"])
    return matching
