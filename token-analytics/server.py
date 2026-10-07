"""server.py — `collect serve`: static viewer + JSON + POST /api/bind.

Serves the static viewer/ directory plus snapshot JSON, and accepts
session->issue binding overrides via POST /api/bind. Stdlib
http.server; no build step. Skeleton only; implemented by later tasks
of #26.
"""


def run_serve(config: dict) -> None:
    """Stub: serve the viewer; filled in by later tasks of #26."""
