"""Tests for file → sessions attribution."""
from pathlib import Path
from reflect.scripts.lib.attribute_to_sessions import (
    find_sessions_for_file,
    match_session_to_path,
)


def test_match_session_to_path_same_path():
    session = {
        "id": "a", "path": "/root/workspace/memo",
        "time_created": 1700000000000, "time_updated": 1700001000000,
    }
    assert match_session_to_path(session, "/root/workspace/memo")


def test_match_session_to_path_different_path():
    session = {
        "id": "a", "path": "/root/workspace/memo",
        "time_created": 1700000000000, "time_updated": 1700001000000,
    }
    assert not match_session_to_path(session, "/root/workspace/superagents")


def test_find_sessions_for_file_via_git_log(tmp_path: Path):
    """Test git log integration; skips if no git repo."""
    repo = Path("/root/workspace/superagents")
    if not (repo / ".git").exists():
        import pytest
        pytest.skip("No git repo at /root/workspace/superagents")

    # Get actual latest commit time for README.md so the session window matches
    import subprocess
    result = subprocess.run(
        ["git", "log", "--format=%ct", "-1", "--", "README.md"],
        cwd=repo, capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0 or not result.stdout.strip():
        import pytest
        pytest.skip("No commits for README.md in repo")
    commit_time_ms = int(result.stdout.strip()) * 1000

    sessions = [
        {"id": "a", "path": str(repo), "time_created": commit_time_ms, "time_updated": commit_time_ms},
    ]
    result = find_sessions_for_file(
        sessions=sessions,
        target_file="README.md",
        repo_path=repo,
    )
    assert isinstance(result, list)
    assert any(r["id"] == "a" for r in result)
