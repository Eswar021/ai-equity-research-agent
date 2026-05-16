"""
intelligence_layer/memory_qualification/layer10_instruction_consumer.py — Layer 4 extension

Consumes memory_update_instructions.json produced by Layer 10 and applies
them to the persistent db/memory/ store.

Instruction types handled:
  add_watch_memory   — writes a new watch_memory JSONL record
  update_thesis      — updates confidence/status on matching thesis_memory records
  archive_rejected   — marks matching watch/thesis records as archived

Called by run_intelligence_pipeline.py after Layer 10 completes.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_CTR = [0]

_WATCH_FILE  = "watch_memory.jsonl"
_THESIS_FILE = "thesis_memory.jsonl"

_FUTURE_USE_WATCH = ["company deep dive", "thesis monitoring", "risk tracking", "watchlist review"]


def consume(layer10_dir: Path, db_memory_dir: Path) -> dict:
    """
    Read memory_update_instructions.json from layer10_dir and apply to db_memory_dir.
    Returns a summary dict.
    """
    layer10_dir  = Path(layer10_dir)
    db_memory_dir = Path(db_memory_dir)
    instr_path = layer10_dir / "memory_update_instructions.json"

    if not instr_path.exists():
        return {"status": "skipped", "reason": "memory_update_instructions.json not found"}

    instructions: list[dict] = json.loads(instr_path.read_text(encoding="utf-8"))
    if not isinstance(instructions, list):
        return {"status": "skipped", "reason": "invalid instruction file format"}

    summary = {"total": len(instructions), "applied": 0, "skipped": 0, "errors": 0, "detail": []}

    for instr in instructions:
        action = instr.get("memory_action", "")
        try:
            if action == "add_watch_memory":
                result = _add_watch_memory(instr, db_memory_dir)
            elif action == "update_thesis":
                result = _update_thesis(instr, db_memory_dir)
            elif action == "archive_rejected":
                result = _archive_rejected(instr, db_memory_dir)
            else:
                result = {"status": "skipped", "reason": f"unknown action '{action}'"}

            status = result.get("status", "ok")
            if status in ("ok", "written"):
                summary["applied"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
            summary["detail"].append({
                "instruction_id": instr.get("instruction_id"),
                "action": action,
                **result,
            })
        except Exception as e:
            summary["errors"] += 1
            summary["detail"].append({
                "instruction_id": instr.get("instruction_id"),
                "action": action,
                "status": "error",
                "error": str(e)[:120],
            })

    summary["status"] = "ok" if summary["errors"] == 0 else "partial"
    return summary


# ── Instruction handlers ──────────────────────────────────────────────────────

def _add_watch_memory(instr: dict, db_memory_dir: Path) -> dict:
    """Write a new watch_memory record for a watchlist target."""
    now = datetime.now(_IST).isoformat()
    _CTR[0] += 1
    today_str = datetime.now(_IST).strftime("%Y%m%d")
    mid = f"MEM_L10_{today_str}_{_CTR[0]:04d}"

    ticker = instr.get("ticker", "")
    name   = instr.get("target_name", "")
    ret_days = instr.get("retention_days", 30)

    record = {
        "memory_id":    mid,
        "memory_type":  "watch_memory",
        "status":       "active",
        "title":        instr.get("title", f"{name} watch"),
        "summary":      instr.get("summary", ""),
        "memory_scope": ["company"],
        "time_horizon": "short_term",

        "linked_entities": [ticker, name] if ticker else [name],
        "linked_themes":   [],
        "linked_events":   [],
        "linked_facts":    [],
        "linked_claims":   [],

        "source_refs": [{
            "source_id":   "layer10_final_synthesis",
            "document_id": instr.get("research_run_id", ""),
        }],
        "why_stored":      f"Layer 10 recommendation: {instr.get('action_label','watchlist')}",
        "future_use_cases": _FUTURE_USE_WATCH,

        "monitoring_triggers":     instr.get("monitoring_triggers", []),
        "invalidation_conditions": instr.get("invalidation_conditions", []),

        "recurrence": {
            "occurrence_count":      1,
            "source_diversity_count": 1,
        },
        "retention": {
            "retention_days": ret_days,
            "expires_at":     instr.get("expires_on", ""),
            "decay_policy":   "medium_decay",
        },

        "created_at":   now,
        "updated_at":   now,
        "last_seen_at": now,
        "confidence":   instr.get("confidence", 0.6),

        "source_object_type": "layer10_target",
        "source_object_id":   instr.get("target_id", ""),
        "research_run_id":    instr.get("research_run_id", ""),

        "l10_action_label": instr.get("action_label", ""),
        "l10_thesis_status": instr.get("thesis_status", ""),
    }

    _append_jsonl(db_memory_dir / _WATCH_FILE, record)
    _update_index(record, db_memory_dir)
    return {"status": "written", "memory_id": mid}


def _update_thesis(instr: dict, db_memory_dir: Path) -> dict:
    """Find existing thesis_memory records for this ticker and update confidence."""
    ticker  = instr.get("ticker", "")
    name    = instr.get("target_name", "")
    new_conf = float(instr.get("new_confidence", 0.5))
    now      = datetime.now(_IST).isoformat()

    thesis_path = db_memory_dir / _THESIS_FILE
    if not thesis_path.exists():
        return {"status": "skipped", "reason": "thesis_memory.jsonl not found"}

    lines = thesis_path.read_text(encoding="utf-8").splitlines()
    updated_count = 0
    new_lines: list[str] = []

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

        entities = [str(e).upper() for e in (rec.get("linked_entities") or [])]
        match = (ticker.upper() in entities or name.upper() in entities or
                 ticker.replace(".NS", "").upper() in entities)

        if match and rec.get("status") == "active":
            old_conf = float(rec.get("confidence", 0.5))
            rec["confidence"]   = round(new_conf, 3)
            rec["updated_at"]   = now
            rec["last_seen_at"] = now
            rec.setdefault("recurrence", {})["occurrence_count"] = (
                rec.get("recurrence", {}).get("occurrence_count", 1) + 1
            )
            # Append monitoring triggers if new
            existing_triggers = set(rec.get("monitoring_triggers", []))
            for t in instr.get("monitoring_triggers", []):
                if t not in existing_triggers:
                    rec.setdefault("monitoring_triggers", []).append(t)
                    existing_triggers.add(t)
            rec["l10_thesis_status"] = instr.get("thesis_status", "")
            updated_count += 1
            new_lines.append(json.dumps(rec))
        else:
            new_lines.append(line)

    if updated_count:
        thesis_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return {"status": "ok", "records_updated": updated_count}

    return {"status": "skipped", "reason": f"no active thesis_memory found for {ticker or name}"}


def _archive_rejected(instr: dict, db_memory_dir: Path) -> dict:
    """Mark matching watch/thesis records for a rejected target as archived."""
    ticker = instr.get("ticker", "")
    name   = instr.get("target_name", "")
    now    = datetime.now(_IST).isoformat()
    archived = 0

    for fname in (_WATCH_FILE, _THESIS_FILE):
        fpath = db_memory_dir / fname
        if not fpath.exists():
            continue

        lines = fpath.read_text(encoding="utf-8").splitlines()
        new_lines: list[str] = []
        changed = False

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

            entities = [str(e).upper() for e in (rec.get("linked_entities") or [])]
            match = (ticker.upper() in entities or name.upper() in entities or
                     ticker.replace(".NS", "").upper() in entities)

            if match and rec.get("status") == "active":
                rec["status"]     = "archived"
                rec["updated_at"] = now
                rec["archive_reason"] = instr.get("reason", "rejected by L10")
                rec["l10_action_label"] = instr.get("action_label", "")
                archived += 1
                changed = True

            new_lines.append(json.dumps(rec))

        if changed:
            fpath.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    if archived:
        return {"status": "ok", "records_archived": archived}
    return {"status": "skipped", "reason": f"no active records found for {ticker or name}"}


# ── Persistence helpers ───────────────────────────────────────────────────────

def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _update_index(record: dict, db_memory_dir: Path) -> None:
    mid = record["memory_id"]
    ei_path = db_memory_dir / "entity_memory_index.json"
    ei = json.loads(ei_path.read_text()) if ei_path.exists() else {}
    for ent in (record.get("linked_entities") or []):
        key = str(ent).lower()
        ei.setdefault(key, [])
        if mid not in ei[key]:
            ei[key].append(mid)
    ei_path.write_text(json.dumps(ei, indent=2))
