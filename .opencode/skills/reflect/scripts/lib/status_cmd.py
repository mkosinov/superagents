"""Status command — show reflection health."""
from __future__ import annotations
import argparse
from pathlib import Path
from ..lib import REFLECT_HOME
from ..lib.metrics import compute_proposal_metrics


def run_status(args: argparse.Namespace) -> int:
    """Print reflection health summary."""
    base_dir = REFLECT_HOME
    metrics = compute_proposal_metrics(base_dir)
    
    print("Reflection Status", flush=True)
    print(f"  REFLECT_HOME: {base_dir}", flush=True)
    print(f"  Proposals total: {metrics['total']}", flush=True)
    print(f"    Applied: {metrics['applied']}", flush=True)
    print(f"    Rejected: {metrics['rejected']}", flush=True)
    print(f"    Modified: {metrics['modified']}", flush=True)
    print(f"    Pending: {metrics['pending']}", flush=True)
    print(f"  Adoption rate: {metrics['adoption_rate']:.0%}", flush=True)
    print(f"  False positive rate: {metrics['false_positive_rate']:.0%}", flush=True)
    return 0
