"""Tests for session tree reconstruction."""
from reflect.scripts.lib.reconstruct_tree import (
    build_tree,
    SessionNode,
    find_root,
)


def test_build_tree_simple_chain():
    """main → subagent1 → subagent2"""
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "b", "title": "Wave 1 1", "parent_id": "a", "agent": "frontend-coder", "time_created": 10, "time_updated": 50, "time_archived": 50},
        {"id": "c", "title": "Wave 1 2", "parent_id": "b", "agent": "spec-reviewer", "time_created": 60, "time_updated": 90, "time_archived": 90},
    ]
    tree = build_tree(sessions)
    assert "a" in tree
    assert tree["a"].agent == "architect"
    assert len(tree["a"].children) == 1
    assert tree["a"].children[0].id == "b"
    assert tree["b"].children[0].id == "c"


def test_find_root_main_sessions():
    sessions = [
        {"id": "a", "title": "Wave 1", "parent_id": None, "agent": "architect", "time_created": 1, "time_updated": 100, "time_archived": 100},
        {"id": "b", "title": "Wave 1 1", "parent_id": "a", "agent": "frontend-coder", "time_created": 10, "time_updated": 50, "time_archived": 50},
    ]
    roots = find_root(sessions)
    assert len(roots) == 1
    assert roots[0].id == "a"


def test_session_node_duration():
    node = SessionNode(
        id="x", title="t", parent_id=None, agent="a",
        time_created=1000, time_updated=5000, time_archived=5000,
    )
    assert node.duration_ms == 4000
    assert node.is_archived
