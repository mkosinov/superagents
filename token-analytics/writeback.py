"""writeback.py — board write-back via managed gh CLI.

Writes snapshot metrics to GitHub Project boards using `gh project
item-edit` / `field-list` / `item-list` (field binding by NAME, per
config.json). Skeleton only; implemented by later tasks of #26.
"""


def run_writeback(config: dict) -> None:
    """Stub: board write-back pass; filled in by later tasks of #26."""


def run_after_rebuild(config: dict, data_dir) -> None:
    """Post-rebuild write-back hook (spec §Collection runs, §Board write-back).

    Pushes snapshot metrics to every project board with write_back
    enabled; called by collector.run_collect at the end of each
    collection pass, under the same data/.lock. No-op stub — filled in
    by Task 8 of #26.
    """
