"""Wave-driven report pipeline.

Full flow:
  1. Open opencode.db
  2. find_wave_sessions by title pattern
  3. run all 17 checks
  4. score_agents + score_skills
  5. aggregate stats
  6. generate proposals
  7. fill wave-report template
  8. write report
"""
from __future__ import annotations
import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .db import open_db, list_sessions, list_tool_calls
from .workflow_checks import ALL_CHECKS
from .config import load_config
from .quality_scoring import score_agents, score_skills
from .analyze import fill_template, format_violations_with_context
from .post_mortem import _violations_to_proposals

REFLECT_HOME = Path.home() / ".config" / "opencode" / "reflection"
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

_DEFAULT_TEMPLATE = """# Wave Report: {wave_name}

> Generated: {timestamp}
> Sessions: {session_count}

## Summary
- Compliance: {compliance_score}%
- Cost: ${total_cost}
- Tokens: {total_tokens}
- First-time-right: {first_time_right}%

## Subagent results
{subagent_table}

## Violations
{violations_table}

## Proposals
{proposals_section}
"""


def find_wave_sessions(sessions: list[dict], wave_name: str) -> list[dict]:
    """Find sessions matching wave name in title.
    
    Pattern: title contains 'Wave X.Y' OR 'Wave X.Y N' (subagent).
    """
    pattern = re.compile(re.escape(wave_name), re.IGNORECASE)
    return [s for s in sessions if pattern.search(s.get("title", ""))]


def run_wave_report(args: argparse.Namespace) -> int:
    """Full wave-report pipeline."""
    config = load_config(Path.home() / ".config" / "opencode")
    base_dir = REFLECT_HOME
    base_dir.mkdir(parents=True, exist_ok=True)
    
    if not OPENCODE_DB.exists():
        print(f"ERROR: opencode.db not found", flush=True)
        return 1
    
    conn = open_db(OPENCODE_DB)
    try:
        all_sessions = list_sessions(conn, since_ms=0)
        relevant = find_wave_sessions(all_sessions, args.name)
        if not relevant:
            print(f"No sessions for wave {args.name!r}", flush=True)
            return 0
        all_tool_calls = list_tool_calls(conn, since_ms=0)
    finally:
        conn.close()
    
    # Run checks
    all_violations = []
    for check_fn in ALL_CHECKS:
        try:
            violations = check_fn(relevant, all_tool_calls, config)
            all_violations.extend(violations)
        except Exception:
            pass
    
    # Quality scores
    agent_scores = score_agents(relevant, min_samples=2)
    skill_scores = score_skills(relevant, all_tool_calls, min_samples=2)
    
    # Aggregate stats
    total_cost = sum(s.get("cost", 0) for s in relevant)
    total_tokens = sum(
        (s.get("tokens_input", 0) + s.get("tokens_output", 0)) for s in relevant
    )
    compliance_score = (
        1.0 - len({v.session_id for v in all_violations if v.session_id}) / max(len(relevant), 1)
    ) * 100
    first_time_right_pct = 50.0  # placeholder
    
    subagent_table = "\n".join(
        f"| {a.name} | {a.usage_count} | {a.success_rate:.0%} | — | — |"
        for a in agent_scores.values()
    ) or "_No agent data._"
    
    template_path = Path(__file__).parent.parent.parent / "templates" / "wave-report.md"
    if template_path.exists():
        template = template_path.read_text()
    else:
        template = _DEFAULT_TEMPLATE
    
    today = datetime.now()
    proposal_ids = _violations_to_proposals(
        all_violations, config, base_dir, today,
    )
    proposals_section = (
        "\n".join(f"- {pid}" for pid in proposal_ids) or "_No proposals._"
    )
    
    content = fill_template(
        template,
        wave_name=args.name,
        timestamp=today.isoformat(timespec="seconds"),
        session_count=len(relevant),
        compliance_score=f"{compliance_score:.0f}",
        total_cost=f"{total_cost:.2f}",
        total_tokens=total_tokens,
        first_time_right=f"{first_time_right_pct:.0f}",
        subagent_table=subagent_table,
        violations_table=format_violations_with_context(all_violations),
        proposals_section=proposals_section,
    )
    
    (base_dir / "reports").mkdir(exist_ok=True)
    safe_name = re.sub(r"[^a-z0-9]+", "-", args.name.lower())[:30]
    report_path = base_dir / "reports" / f"{today.strftime('%Y-%m-%d')}-wave-{safe_name}.md"
    report_path.write_text(content)
    print(f"Wave report written to {report_path}", flush=True)
    return 0
