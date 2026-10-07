"""collector.py — source readers, mapping, aggregation, snapshot writing.

Reads the host zcode DB and the opencode container DB, maps sessions to
issues, attributes design/IMPL phases, aggregates tokens and active time,
and writes atomic snapshots under data/. Skeleton only; implemented by
later tasks of #26.
"""


def run_collect(config: dict) -> None:
    """Stub: one collection pass; filled in by later tasks of #26."""
