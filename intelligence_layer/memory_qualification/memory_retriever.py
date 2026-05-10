"""
intelligence_layer/memory_qualification/memory_retriever.py — Layer 4

Retrieves relevant past memory records for current run entities/themes.
Builds memory_context_packet.json consumed by Layer 5 and Layer 6.

Design doc: docs/system_design_docs/layer_4.md §14 memory_retriever.py
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))

_MEMORY_FILES = {
    "short_term_market_memory": "short_term_market_memory.jsonl",
    "watch_memory":             "watch_memory.jsonl",
    "long_term_investment_memory": "long_term_investment_memory.jsonl",
    "thesis_memory":            "thesis_memory.jsonl",
}


def build_context_packet(current_entities: list[str], current_themes: list[str],
                          db_memory_dir: Path, run_id: str = "",
                          lookback_days: int = 90) -> dict:
    """
    Build the memory context packet for Layer 5 / Layer 6 consumption.

    Returns:
        {
            research_run_id, created_at,
            relevant_short_term_memory,
            relevant_watch_memory,
            relevant_long_term_memory,
            relevant_thesis_memory,
            summary_stats
        }
    """
    entity_set = {e.lower() for e in current_entities}
    theme_set  = {t.lower() for t in current_themes}
    now        = datetime.now(_IST)
    cutoff     = now - timedelta(days=lookback_days)

    short_term: list[dict] = []
    watch:      list[dict] = []
    long_term:  list[dict] = []
    theses:     list[dict] = []

    for mem_type, fname in _MEMORY_FILES.items():
        fpath = db_memory_dir / fname
        if not fpath.exists():
            continue
        for rec in _read_jsonl(fpath):
            if rec.get("status") not in ("active", "stale"):
                continue
            last_seen = _parse_dt(rec.get("last_seen_at") or rec.get("updated_at") or "")
            if last_seen and last_seen < cutoff and mem_type != "thesis_memory":
                continue
            if not _relevant(rec, entity_set, theme_set):
                continue
            summary = _summarise(rec)
            if mem_type == "short_term_market_memory":
                short_term.append(summary)
            elif mem_type == "watch_memory":
                watch.append(summary)
            elif mem_type == "long_term_investment_memory":
                long_term.append(summary)
            elif mem_type == "thesis_memory":
                theses.append(summary)

    # Sort by confidence desc
    for lst in (short_term, watch, long_term, theses):
        lst.sort(key=lambda r: r.get("confidence", 0), reverse=True)

    return {
        "research_run_id":           run_id,
        "created_at":                now.isoformat(),
        "relevant_short_term_memory": short_term[:20],
        "relevant_watch_memory":      watch[:20],
        "relevant_long_term_memory":  long_term[:20],
        "relevant_thesis_memory":     theses[:10],
        "summary_stats": {
            "total_relevant":       len(short_term) + len(watch) + len(long_term) + len(theses),
            "short_term_count":     len(short_term),
            "watch_count":          len(watch),
            "long_term_count":      len(long_term),
            "thesis_count":         len(theses),
            "entities_queried":     len(entity_set),
            "themes_queried":       len(theme_set),
        },
    }


def retrieve(query_entities: list[str], query_themes: list[str],
             db_memory_dir: Path,
             memory_types: list[str] | None = None,
             limit: int = 20) -> list[dict]:
    """
    Simple retrieval API for use by other modules.
    Returns a flat list of relevant memory summaries.
    """
    entity_set = {e.lower() for e in query_entities}
    theme_set  = {t.lower() for t in query_themes}
    types      = set(memory_types) if memory_types else set(_MEMORY_FILES.keys())
    results: list[dict] = []

    for mem_type, fname in _MEMORY_FILES.items():
        if mem_type not in types:
            continue
        fpath = db_memory_dir / fname
        if not fpath.exists():
            continue
        for rec in _read_jsonl(fpath):
            if rec.get("status") not in ("active", "stale"):
                continue
            if _relevant(rec, entity_set, theme_set):
                results.append(_summarise(rec))

    results.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    return results[:limit]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _relevant(rec: dict, entity_set: set[str], theme_set: set[str]) -> bool:
    rec_ents   = {e.lower() for e in (rec.get("linked_entities") or [])}
    rec_themes = {t.lower() for t in (rec.get("linked_themes") or [])}
    return bool((entity_set & rec_ents) or (theme_set & rec_themes))


def _summarise(rec: dict) -> dict:
    return {
        "memory_id":          rec.get("memory_id", ""),
        "memory_type":        rec.get("memory_type", ""),
        "summary":            rec.get("summary", ""),
        "linked_entities":    rec.get("linked_entities") or [],
        "linked_themes":      rec.get("linked_themes") or [],
        "last_seen_at":       rec.get("last_seen_at", ""),
        "occurrence_count":   (rec.get("recurrence") or {}).get("occurrence_count", 1),
        "confidence":         rec.get("confidence", 0),
        "status":             rec.get("status", "active"),
        "time_horizon":       rec.get("time_horizon", "unknown"),
        # thesis-specific
        "thesis_id":          rec.get("thesis_id"),
        "thesis_type":        rec.get("thesis_type"),
        "title":              rec.get("title"),
    }


def _read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


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
