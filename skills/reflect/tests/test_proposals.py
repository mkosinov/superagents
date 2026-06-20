"""Tests for proposal filesystem layer."""
from pathlib import Path
from reflect.scripts.lib.proposals import (
    create_proposal,
    list_pending_proposals,
    record_decision,
    list_decisions,
)


def test_create_proposal_writes_file(tmp_path: Path):
    proposal_id = create_proposal(
        base_dir=tmp_path,
        proposal_id="prop-2026-06-19-001",
        title="Update checklist",
        severity="warning",
        confidence=0.85,
        target="agents/spec-reviewer.md",
        rationale="Wave 4.5: 3/5 sessions approved without edge case coverage.",
        diff="+ ## Edge cases\n+ - [ ] Long strings\n+ - [ ] Unicode",
        auto_apply_eligible=False,
    )
    assert proposal_id == "prop-2026-06-19-001"
    files = list(tmp_path.glob("proposals/*.md"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Update checklist" in content
    assert "0.85" in content
    assert "❌" in content


def test_list_pending_proposals(tmp_path: Path):
    create_proposal(tmp_path, "p1", "A", "info", 0.9, "x", "r", "d", False)
    create_proposal(tmp_path, "p2", "B", "warning", 0.7, "y", "r", "d", False)
    pending = list_pending_proposals(tmp_path)
    assert len(pending) == 2
    assert {p["id"] for p in pending} == {"p1", "p2"}


def test_record_decision_moves_file(tmp_path: Path):
    create_proposal(tmp_path, "p1", "A", "info", 0.9, "x", "r", "d", False)
    record_decision(
        base_dir=tmp_path,
        proposal_id="p1",
        outcome="applied",
        reason="Looks good",
        commit_sha="abc123",
    )
    assert not (tmp_path / "proposals" / "p1.md").exists()
    decisions = list(tmp_path.glob("decisions/*.md"))
    assert len(decisions) == 1
    assert "abc123" in decisions[0].read_text()


def test_list_decisions_includes_metadata(tmp_path: Path):
    create_proposal(tmp_path, "p1", "A", "info", 0.9, "x", "r", "d", False)
    record_decision(tmp_path, "p1", "rejected", "Out of scope", None)
    decisions = list_decisions(tmp_path)
    assert len(decisions) == 1
    assert decisions[0]["outcome"] == "rejected"
