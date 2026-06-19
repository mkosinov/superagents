"""Session tree reconstruction from opencode.db flat list."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionNode:
    id: str
    title: str
    parent_id: Optional[str]
    agent: str
    time_created: int
    time_updated: int
    time_archived: Optional[int] = None
    children: list["SessionNode"] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return self.time_updated - self.time_created

    @property
    def is_archived(self) -> bool:
        return self.time_archived is not None

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


def build_tree(sessions: list[dict]) -> dict[str, SessionNode]:
    """Build tree of SessionNodes from flat list. Returns {id: node}."""
    nodes = {
        s["id"]: SessionNode(
            id=s["id"],
            title=s["title"],
            parent_id=s.get("parent_id"),
            agent=s["agent"],
            time_created=s["time_created"],
            time_updated=s["time_updated"],
            time_archived=s.get("time_archived"),
        )
        for s in sessions
    }
    for s in sessions:
        if s.get("parent_id") and s["parent_id"] in nodes:
            nodes[s["parent_id"]].children.append(nodes[s["id"]])
    return nodes


def find_root(sessions: list[dict]) -> list[SessionNode]:
    """Return root (no parent) SessionNodes from a flat list."""
    tree = build_tree(sessions)
    return [n for n in tree.values() if n.is_root]
