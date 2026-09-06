"""Bug-driven post-mortem pipeline.

Full flow:
  1. Open opencode.db read-only
  2. find_sessions_for_file (git log + path match)
  3. build_tree
  4. run ALL 17 workflow checks
  5. find_related_decisions (closing-the-loop)
  6. generate proposals via LLM
  7. fill post-mortem template
  8. write report
"""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .db import open_db, list_sessions, list_tool_calls
from .attribute_to_sessions import find_sessions_for_file
from .reconstruct_tree import build_tree
from .workflow_checks import ALL_CHECKS
from .config import load_config
from .closing_the_loop import find_related_decisions
from .analyze import (
    fill_template,
    format_violations_with_context,
    batch_violations_to_proposals,
    generate_proposal_id,
)
from .proposals import create_proposal

REFLECT_HOME = Path.home() / ".config" / "opencode" / "reflection"
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

_DEFAULT_TEMPLATE = """# Post-mortem: {bug_title}

> Generated: {timestamp}
> Target: `{target_file}`

## Bug summary
{bug_description}

## Originating workflow
{subagent_tree}

## Workflow gaps
{gaps_table}

## Detailed analysis
{detailed_analysis}

## Proposed workflow changes
{proposals_section}

## Related past decisions
{related_decisions_section}
"""


def _violations_to_proposals(
    violations: Iterable,
    config,
    base_dir: Path,
    date: datetime,
    seq_start: int = 1,
) -> list[str]:
    """Convert violations to proposal IDs using batched LLM call."""
    violation_list = list(violations)
    proposal_specs = batch_violations_to_proposals(violation_list, config)
    proposal_ids = []
    for i, spec in enumerate(proposal_specs):
        pid = generate_proposal_id(date=date, seq=seq_start + i)
        v = violation_list[i] if i < len(violation_list) else None
        eligible = (
            v and v.severity == "info"
            and config.auto_apply.enabled
        )
        create_proposal(
            base_dir=base_dir,
            proposal_id=pid,
            title=spec.get("title", "(batch)"),
            severity=v.severity if v else "info",
            confidence=0.7,
            target=spec.get("target", "unknown"),
            rationale=spec.get("rationale", ""),
            diff=spec.get("diff", ""),
            auto_apply_eligible=eligible,
        )
        proposal_ids.append(pid)
    return proposal_ids


def run_post_mortem(args: argparse.Namespace) -> int:
    """Full post-mortem pipeline."""
    repo = Path(args.repo) if args.repo else Path.cwd()
    target_file = args.target
    config = load_config(Path.home() / ".config" / "opencode")
    base_dir = REFLECT_HOME
    base_dir.mkdir(parents=True, exist_ok=True)
    
    if not OPENCODE_DB.exists():
        print(f"ERROR: opencode.db not found at {OPENCODE_DB}", flush=True)
        return 1
    
    conn = open_db(OPENCODE_DB)
    try:
        all_sessions = list_sessions(conn, since_ms=0)
        relevant = find_sessions_for_file(
            sessions=all_sessions, target_file=target_file, repo_path=repo,
        )
        if not relevant:
            print(f"No sessions found for {target_file}", flush=True)
            return 0
        all_tool_calls = list_tool_calls(conn, since_ms=0)
    finally:
        conn.close()
    
    # Build tree
    build_tree(relevant)
    
    # Run all 17 checks
    all_violations = []
    for check_fn in ALL_CHECKS:
        try:
            violations = check_fn(relevant, all_tool_calls, config)
            all_violations.extend(violations)
        except Exception as e:
            print(f"Check {check_fn.__name__} failed: {e}", flush=True)
    
    # Find related past decisions
    related = find_related_decisions(
        base_dir=base_dir, target=target_file,
    )
    
    # Generate proposals
    today = datetime.now()
    proposal_ids = _violations_to_proposals(
        all_violations, config, base_dir, today,
    )
    
    # Build tree text
    tree_text_parts = []
    for s in relevant:
        if s.get("parent_id") is None:
            tree_text_parts.append(
                f"  - {s['id']} ({s.get('agent', 'unknown')})"
            )
    tree_text = "\n".join(tree_text_parts) or "  - (no main session)"
    
    # Fill template
    template_path = Path(__file__).parent.parent.parent / "templates" / "post-mortem.md"
    if template_path.exists():
        template = template_path.read_text()
    else:
        template = _DEFAULT_TEMPLATE
    
    gaps_table = format_violations_with_context(all_violations)
    proposals_section = (
        "\n".join(f"- {pid}" for pid in proposal_ids) or "_No proposals._"
    )
    related_section = (
        "\n".join(
            f"- {r['id']} ({r['outcome']}, {r['days_since_decision']}d ago)"
            for r in related
        )
        or "_None._"
    )
    
    content = fill_template(
        template,
        bug_title=f"Bug in {target_file}",
        timestamp=today.isoformat(timespec="seconds"),
        target_file=target_file,
        bug_description="User reported a bug. Investigating originating workflow.",
        wave_name="unknown",
        main_session_id=tree_text.split("\n")[0] if tree_text else "none",
        subagent_tree=tree_text,
        gaps_table=gaps_table,
        detailed_analysis=f"{len(all_violations)} violations found across {len(relevant)} sessions.",
        proposals_section=proposals_section,
        related_decisions_section=related_section,
    )
    
    # Write report
    (base_dir / "reports").mkdir(exist_ok=True)
    report_path = base_dir / "reports" / f"{today.strftime('%Y-%m-%d')}-postmortem-{Path(target_file).stem}.md"
    report_path.write_text(content)
    print(f"Post-mortem written to {report_path}", flush=True)
    print(f"  {len(all_violations)} violations, {len(proposal_ids)} proposals", flush=True)
    return 0
