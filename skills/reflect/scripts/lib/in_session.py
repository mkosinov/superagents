"""In-session reflection pipeline.

Analyzes the CURRENT opencode session + all its subagent sessions.
Like post_mortem but session-centric instead of file-centric.

Useful for: 
- /reflect slash command (architect runs this on its own session)
- Real-time reflection during/after a wave
- Bug post-mortem where target is the session, not a file
"""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path

from .db import open_db, list_sessions, list_tool_calls
from .workflow_checks import ALL_CHECKS
from .config import load_config
from .analyze import fill_template, format_violations_with_context
from .post_mortem import _violations_to_proposals

REFLECT_HOME = Path.home() / ".config" / "opencode" / "reflection"
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

_DEFAULT_TEMPLATE = """# In-Session Reflection: {session_title}

> Generated: {timestamp}
> Mode: in-session
> Session: `{session_id}`
> Subagent sessions analyzed: {subagent_count}

## User notes
{user_notes}

## Workflow gaps found

| Gap | Severity | Check |
|-----|----------|-------|
{gaps_table}

## Subagent activity
{subagent_summary}

## Detailed analysis
{detailed_analysis}

## Proposed workflow changes
{proposals_section}

## Action required
- [ ] Review proposals
- [ ] Approve selected
- [ ] Apply diffs
"""


def _get_session_and_subagents(conn, session_id: str) -> tuple[dict, list[dict]]:
    """Get main session + all its subagent sessions (recursively)."""
    all_sessions = list_sessions(conn, since_ms=0)
    main = next((s for s in all_sessions if s["id"] == session_id), None)
    if not main:
        return None, []

    # Get all descendants
    subagents = []
    to_process = [session_id]
    seen = {session_id}
    while to_process:
        parent = to_process.pop()
        for s in all_sessions:
            if s.get("parent_id") == parent and s["id"] not in seen:
                subagents.append(s)
                seen.add(s["id"])
                to_process.append(s["id"])
    return main, subagents


def run_in_session(args: argparse.Namespace) -> int:
    """In-session reflection pipeline."""
    config = load_config(Path.home() / ".config" / "opencode")
    base_dir = REFLECT_HOME
    base_dir.mkdir(parents=True, exist_ok=True)

    if not OPENCODE_DB.exists():
        print(f"ERROR: opencode.db not found", flush=True)
        return 1

    session_id = args.session
    notes = getattr(args, "notes", "") or ""

    conn = open_db(OPENCODE_DB)
    try:
        main_session, subagents = _get_session_and_subagents(conn, session_id)
        if not main_session:
            print(f"ERROR: session {session_id} not found", flush=True)
            return 1
        all_sessions = [main_session] + subagents
        all_tool_calls = list_tool_calls(conn, since_ms=0)
        # Filter tool calls to this session + subagents only
        relevant_tcs = [tc for tc in all_tool_calls if tc["session_id"] in {s["id"] for s in all_sessions}]
    finally:
        conn.close()

    # Run all 17 checks
    all_violations = []
    for check_fn in ALL_CHECKS:
        try:
            violations = check_fn(all_sessions, relevant_tcs, config)
            all_violations.extend(violations)
        except Exception as e:
            print(f"Check {check_fn.__name__} failed: {e}", flush=True)

    # Generate proposals
    today = datetime.now()
    proposal_ids = _violations_to_proposals(
        all_violations, config, base_dir, today,
    )

    # Subagent summary
    subagent_lines = []
    for s in subagents:
        duration_s = (s["time_updated"] - s["time_created"]) / 1000
        subagent_lines.append(f"  - `{s['id'][:12]}` ({s.get('agent', 'unknown')}, {duration_s:.0f}s, title: {s.get('title', '')[:40]})")
    subagent_summary = "\n".join(subagent_lines) or "_No subagents._"

    # Fill template
    template_path = Path(__file__).parent.parent.parent / "templates" / "in-session-report.md"
    if template_path.exists():
        template = template_path.read_text()
    else:
        template = _DEFAULT_TEMPLATE

    user_notes_section = notes if notes else "_No notes provided._"
    proposals_section = (
        "\n".join(f"- {pid}" for pid in proposal_ids) or "_No proposals._"
    )

    content = fill_template(
        template,
        session_title=main_session.get("title", "(untitled)"),
        timestamp=today.isoformat(timespec="seconds"),
        session_id=session_id,
        subagent_count=len(subagents),
        user_notes=user_notes_section,
        gaps_table=format_violations_with_context(all_violations),
        subagent_summary=subagent_summary,
        detailed_analysis=f"{len(all_violations)} violations found across main + {len(subagents)} subagent sessions.",
        proposals_section=proposals_section,
    )

    (base_dir / "reports").mkdir(exist_ok=True)
    safe_id = session_id.replace("/", "_")[:20]
    report_path = base_dir / "reports" / f"{today.strftime('%Y-%m-%d')}-in-session-{safe_id}.md"
    report_path.write_text(content)
    print(f"In-session report written to {report_path}", flush=True)
    print(f"  {len(subagents)} subagents, {len(all_violations)} violations, {len(proposal_ids)} proposals", flush=True)
    return 0
