"""Time-driven nightly digest pipeline."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import open_db, list_sessions, list_tool_calls
from .workflow_checks import ALL_CHECKS
from .config import load_config
from .quality_scoring import score_agents, score_skills
from .metrics import compute_proposal_metrics, compute_compliance_trend
from .analyze import fill_template, format_violations_with_context
from .post_mortem import _violations_to_proposals
from .notify import notify_telegram

REFLECT_HOME = Path.home() / ".config" / "opencode" / "reflection"
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

_DEFAULT_TEMPLATE = """# Nightly Digest: {date}

> Generated: {timestamp}
> Mode: time-driven
> Period: last {days} days
> Sessions analyzed: {session_count}

## Top issues
{top_issues}

## Reflection Health
{reflection_health}

## Trends
{trends}

## Workflow violations
{violations_table}

## Proposals
{proposals_section}
"""


def _since_ms(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)


def _detect_regressions(agg_now: dict, agg_prev: dict, threshold_pct: float) -> list[dict]:
    """Compare current vs previous period; return tools with delta > threshold."""
    regressions = []
    for tool, now_stats in agg_now.items():
        if tool not in agg_prev:
            continue
        prev_ms = agg_prev[tool].get("avg_duration_ms", 0) or 0
        now_ms = now_stats.get("avg_duration_ms", 0) or 0
        if prev_ms == 0:
            continue
        delta_pct = ((now_ms - prev_ms) / prev_ms) * 100
        if abs(delta_pct) > threshold_pct:
            regressions.append({
                "tool": tool,
                "prev_ms": prev_ms,
                "now_ms": now_ms,
                "delta_pct": delta_pct,
            })
    return regressions


def run_nightly(args: argparse.Namespace) -> int:
    """Full nightly pipeline."""
    config = load_config(Path.home() / ".config" / "opencode")
    base_dir = REFLECT_HOME
    base_dir.mkdir(parents=True, exist_ok=True)
    
    if not OPENCODE_DB.exists():
        print(f"ERROR: opencode.db not found", flush=True)
        return 1
    
    days = args.days
    now_ms = _since_ms(0)
    period_ms = _since_ms(days)
    prev_ms = _since_ms(days * 2)
    
    conn = open_db(OPENCODE_DB)
    try:
        recent_sessions = list_sessions(conn, since_ms=period_ms)
        recent_tool_calls = list_tool_calls(conn, since_ms=period_ms)
        prev_sessions = list_sessions(conn, since_ms=prev_ms)
    finally:
        conn.close()
    
    # Run checks
    all_violations = []
    for check_fn in ALL_CHECKS:
        try:
            violations = check_fn(recent_sessions, recent_tool_calls, config)
            all_violations.extend(violations)
        except Exception:
            pass
    
    # Quality
    agent_scores = score_agents(recent_sessions, min_samples=config.thresholds.min_samples_for_quality_score)
    skill_scores = score_skills(recent_sessions, recent_tool_calls, min_samples=config.thresholds.min_samples_for_quality_score)
    
    # Metrics
    proposal_metrics = compute_proposal_metrics(base_dir)
    compliance_trend = compute_compliance_trend(recent_sessions, all_violations, days=days)
    
    # Aggregations for report
    total_cost = sum(s.get("cost", 0) for s in recent_sessions)
    total_tokens = sum(
        (s.get("tokens_input", 0) + s.get("tokens_output", 0)) for s in recent_sessions
    )
    
    # Build report
    today = datetime.now()
    proposal_ids = _violations_to_proposals(
        all_violations, config, base_dir, today,
    )
    proposals_section = (
        "\n".join(f"- {pid}" for pid in proposal_ids) or "_No proposals._"
    )
    
    top_issues = "\n".join(
        f"- **{v.severity.upper()}** {v.check_name} (session `{v.session_id}`): {v.message}"
        for v in all_violations[:10]
    ) or "_No issues._"
    
    reflection_health = (
        f"| Adoption rate | {proposal_metrics['adoption_rate']:.0%} | "
        f"{'✅' if proposal_metrics['adoption_rate'] > 0.5 else '⚠️'} |\n"
        f"| False positive rate | {proposal_metrics['false_positive_rate']:.0%} | "
        f"{'✅' if proposal_metrics['false_positive_rate'] < 0.3 else '⚠️'} |\n"
        f"| Proposals total | {proposal_metrics['total']} | — |\n"
        f"| Applied | {proposal_metrics['applied']} | — |\n"
        f"| Pending | {proposal_metrics['pending']} | — |"
    )
    
    trends_md = "| Date | Sessions | Violations | Compliance |\n|------|----------|------------|------------|\n"
    for t in compliance_trend:
        trends_md += f"| {t['date']} | {t['total_sessions']} | {t['violations']} | {t['compliance']:.0%} |\n"
    
    template_path = Path(__file__).parent.parent.parent / "templates" / "nightly-digest.md"
    if template_path.exists():
        template = template_path.read_text()
    else:
        template = _DEFAULT_TEMPLATE
    
    content = fill_template(
        template,
        date=today.strftime("%Y-%m-%d"),
        timestamp=today.isoformat(timespec="seconds"),
        days=days,
        session_count=len(recent_sessions),
        top_issues=top_issues,
        reflection_health=reflection_health,
        trends=trends_md,
        violations_table=format_violations_with_context(all_violations),
        proposals_section=proposals_section,
    )
    
    (base_dir / "reports").mkdir(exist_ok=True)
    report_path = base_dir / "reports" / f"{today.strftime('%Y-%m-%d')}-nightly.md"
    report_path.write_text(content)
    print(f"Nightly digest written to {report_path}", flush=True)
    print(f"  {len(recent_sessions)} sessions, {len(all_violations)} violations, {len(proposal_ids)} proposals", flush=True)
    
    # Telegram notification
    if any(v.severity == "critical" for v in all_violations):
        msg = f"🚨 Reflection: {len(all_violations)} violations, {sum(1 for v in all_violations if v.severity == 'critical')} critical"
        notify_telegram(msg, config.notify.telegram_chat_id)
    
    return 0
