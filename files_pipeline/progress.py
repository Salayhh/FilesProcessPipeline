"""Small helpers for console progress output."""

from __future__ import annotations


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(seconds, 60)
    return f"{int(minutes)}m{remaining:.0f}s"
