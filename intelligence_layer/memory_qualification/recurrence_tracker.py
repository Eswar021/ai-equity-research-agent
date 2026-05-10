"""
intelligence_layer/memory_qualification/recurrence_tracker.py — Layer 4

Tracks repeated themes/events over 7d / 30d / 90d windows.
Reads existing JSONL memory stores to count occurrences.

Design doc: docs/system_design_docs/layer_4.md §7 recurrence_tracker.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))


def track(candidate: dict, all_records: list[dict]) -> dict:
    """
    Count how many times this candidate's entities/themes appear in existing memory.

    Args:
        candidate:   memory candidate dict
        all_records: flat list of all existing memory records (across all JSONL files)

    Returns:
        {
            candidate_id,
            recurrence: {seen_before, count_7d, count_30d, count_90d,
                         source_diversity_30d, recurrence_level}
        }
    """
    cid      = candidate["candidate_id"]
    entities = {e.lower() for e in (candidate.get("linked_entities") or [])}
    themes   = {t.lower() for t in (candidate.get("linked_themes") or [])}
    obj      = candidate.get("_obj") or {}
    evt_type = obj.get("event_type") or ""

    now   = datetime.now(_IST)
    w7    = now - timedelta(days=7)
    w30   = now - timedelta(days=30)
    w90   = now - timedelta(days=90)

    cnt7 = cnt30 = cnt90 = 0
    sources30: set[str] = set()

    for rec in all_records:
        if rec.get("status") == "expired":
            continue
        last_seen = _parse_dt(rec.get("last_seen_at") or rec.get("created_at") or "")
        if last_seen is None:
            continue

        if not _matches(rec, entities, themes, evt_type):
            continue

        if last_seen >= w7:
            cnt7 += 1
        if last_seen >= w30:
            cnt30 += 1
            for src in (rec.get("source_refs") or []):
                sid = src.get("source_id") or src.get("document_id") or ""
                if sid:
                    sources30.add(sid)
        if last_seen >= w90:
            cnt90 += 1

    seen   = cnt90 > 0
    level  = _level(cnt30, len(sources30))

    return {
        "candidate_id": cid,
        "recurrence": {
            "seen_before":         seen,
            "count_7d":            cnt7,
            "count_30d":           cnt30,
            "count_90d":           cnt90,
            "source_diversity_30d": len(sources30),
            "recurrence_level":    level,
        },
    }


def load_all_records(memory_files: list[Path]) -> list[dict]:
    """Load and concatenate all JSONL memory records from a list of paths."""
    records: list[dict] = []
    for p in memory_files:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


# ── Helpers ───────────────────────────────────────────────────────────────────

def _matches(rec: dict, entities: set[str], themes: set[str], evt_type: str) -> bool:
    rec_entities = {e.lower() for e in (rec.get("linked_entities") or [])}
    rec_themes   = {t.lower() for t in (rec.get("linked_themes") or [])}
    if entities & rec_entities:
        return True
    if themes & rec_themes:
        return True
    if evt_type and evt_type in (rec.get("memory_id") or "").lower():
        return True
    return False


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:26], fmt[:len(s[:26])])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_IST)
            return dt
        except ValueError:
            pass
    return None


def _level(cnt30: int, diversity30: int) -> str:
    if cnt30 >= 5 or diversity30 >= 4:
        return "high"
    if cnt30 >= 3 or diversity30 >= 2:
        return "medium"
    if cnt30 >= 1:
        return "low"
    return "none"
