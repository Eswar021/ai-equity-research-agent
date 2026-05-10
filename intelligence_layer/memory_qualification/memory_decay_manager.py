"""
intelligence_layer/memory_qualification/memory_decay_manager.py — Layer 4

Handles expiration and relevance decay of memory records.
Run daily (at end of pipeline) against all JSONL memory files.

Decay states: active → stale → archived → expired

Design doc: docs/system_design_docs/layer_4.md §13 memory_decay_manager.py
"""

from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path

_MEMORY_FILES = [
    "short_term_market_memory.jsonl",
    "watch_memory.jsonl",
    "long_term_investment_memory.jsonl",
    "thesis_memory.jsonl",
    "portfolio_memory.jsonl",
]


def run_decay(db_memory_dir: Path, as_of_date: str | None = None) -> dict:
    """
    Apply decay rules to all JSONL memory stores.

    Args:
        db_memory_dir: path to db/memory/
        as_of_date:    YYYY-MM-DD string (defaults to today)

    Returns:
        {expired_count, archived_count, stale_count, unchanged_count, files_processed}
    """
    today_str = as_of_date or date.today().isoformat()
    today     = date.fromisoformat(today_str)

    expired = archived = stale = unchanged = 0
    files_processed = 0

    for fname in _MEMORY_FILES:
        fpath = db_memory_dir / fname
        if not fpath.exists():
            continue
        files_processed += 1
        lines     = fpath.read_text().splitlines()
        new_lines = []
        changed   = False

        for line in lines:
            line = line.strip()
            if not line:
                new_lines.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue

            # Thesis memory and portfolio memory have no fixed expiry
            if rec.get("memory_type") in ("thesis_memory", "portfolio_memory"):
                new_lines.append(line)
                unchanged += 1
                continue

            old_status  = rec.get("status", "active")
            new_status  = _compute_status(rec, today)

            if new_status != old_status:
                rec["status"] = new_status
                changed = True
                if new_status == "expired":
                    expired += 1
                elif new_status == "archived":
                    archived += 1
                elif new_status == "stale":
                    stale += 1
                new_lines.append(json.dumps(rec))
            else:
                unchanged += 1
                new_lines.append(line)

        if changed:
            fpath.write_text("\n".join(new_lines) + "\n")

    return {
        "expired_count":    expired,
        "archived_count":   archived,
        "stale_count":      stale,
        "unchanged_count":  unchanged,
        "files_processed":  files_processed,
    }


def _compute_status(rec: dict, today: date) -> str:
    """Determine new status based on expires_at and decay_policy."""
    current   = rec.get("status", "active")
    if current in ("expired", "invalidated"):
        return current

    retention = rec.get("retention") or {}
    expires_at_str = retention.get("expires_at") or ""
    decay_policy   = retention.get("decay_policy", "medium_decay")

    if not expires_at_str:
        return current

    try:
        expires_at = date.fromisoformat(expires_at_str)
    except ValueError:
        return current

    days_left = (expires_at - today).days

    if days_left <= 0:
        return "expired"

    if decay_policy == "fast_decay":
        stale_threshold   = 1
        archive_threshold = 0
    elif decay_policy == "slow_decay":
        stale_threshold   = 30
        archive_threshold = 7
    else:  # medium_decay
        stale_threshold   = 14
        archive_threshold = 3

    if days_left <= archive_threshold:
        return "archived"
    if days_left <= stale_threshold:
        return "stale"
    return "active"
