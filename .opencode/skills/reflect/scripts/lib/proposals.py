"""Proposal + decision filesystem layer."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

PROPOSAL_TEMPLATE = """# Proposal: {title}

**ID:** {proposal_id}
**Generated:** {timestamp}
**Severity:** {severity}
**Confidence:** {confidence}
**Auto-apply eligible:** {auto_apply_mark}

## Target
`{target}`

## Rationale
{rationale}

## Proposed diff
```diff
{diff}
```

## Action
- [ ] Approve (apply diff)
- [ ] Reject (reason: ___)
- [ ] Modify (specify changes)
"""

DECISION_TEMPLATE = """# Decision: {proposal_id}

**Outcome:** {outcome}
**Decided at:** {timestamp}
**Reason:** {reason}
**Commit SHA:** {commit_sha}
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_id(proposal_id: str) -> None:
    if not re.match(r"^[a-zA-Z0-9\-_.]+$", proposal_id):
        raise ValueError(f"Invalid proposal_id: {proposal_id!r}")


def _base_paths(base_dir: Path) -> tuple[Path, Path]:
    proposals = base_dir / "proposals"
    decisions = base_dir / "decisions"
    proposals.mkdir(parents=True, exist_ok=True)
    decisions.mkdir(parents=True, exist_ok=True)
    return proposals, decisions


def create_proposal(
    base_dir: Path,
    proposal_id: str,
    title: str,
    severity: str,
    confidence: float,
    target: str,
    rationale: str,
    diff: str,
    auto_apply_eligible: bool,
) -> str:
    _validate_id(proposal_id)
    proposals, _ = _base_paths(base_dir)
    mark = "✅" if auto_apply_eligible else "❌"
    content = PROPOSAL_TEMPLATE.format(
        title=title,
        proposal_id=proposal_id,
        timestamp=_now_iso(),
        severity=severity,
        confidence=confidence,
        auto_apply_mark=mark,
        target=target,
        rationale=rationale,
        diff=diff,
    )
    (proposals / f"{proposal_id}.md").write_text(content)
    return proposal_id


def list_pending_proposals(base_dir: Path) -> list[dict]:
    proposals, _ = _base_paths(base_dir)
    out = []
    for f in sorted(proposals.glob("*.md")):
        content = f.read_text()
        out.append({
            "id": f.stem,
            "path": f,
            "content": content,
        })
    return out


def record_decision(
    base_dir: Path,
    proposal_id: str,
    outcome: str,
    reason: str,
    commit_sha: str | None,
) -> None:
    if outcome not in ("applied", "rejected", "modified"):
        raise ValueError(f"Invalid outcome: {outcome}")
    _validate_id(proposal_id)
    proposals, decisions = _base_paths(base_dir)
    src = proposals / f"{proposal_id}.md"
    if not src.exists():
        raise FileNotFoundError(f"Proposal not found: {proposal_id}")
    original = src.read_text()
    decision_content = (
        original
        + "\n\n---\n\n"
        + DECISION_TEMPLATE.format(
            proposal_id=proposal_id,
            outcome=outcome,
            timestamp=_now_iso(),
            reason=reason,
            commit_sha=commit_sha or "n/a",
        )
    )
    (decisions / f"{proposal_id}.md").write_text(decision_content)
    src.unlink()


def list_decisions(base_dir: Path) -> list[dict]:
    _, decisions = _base_paths(base_dir)
    out = []
    for f in sorted(decisions.glob("*.md")):
        content = f.read_text()
        outcome_match = re.search(r"\*\*Outcome:\*\*\s*(\w+)", content)
        out.append({
            "id": f.stem,
            "path": f,
            "outcome": outcome_match.group(1) if outcome_match else "unknown",
            "content": content,
        })
    return out
