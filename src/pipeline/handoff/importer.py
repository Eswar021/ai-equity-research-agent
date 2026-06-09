"""
Handoff importer — saves AI analysis response as the pipeline's final output.

After running the after_l8 handoff and getting a response from ChatGPT/Claude:
  1. Save the AI's filled output file as a .md file on disk
  2. Run this importer — it registers the file as the final report for the date

Writes:
    output/{date}/handoff/after_l8/ai_analysis.md    — the analysis (copy of response file)
    output/{date}/handoff/after_l8/import_summary.json

Usage:
    python -m src.pipeline.handoff.importer --date 2026-06-09 --response path/to/filled_template.md
    python -m src.pipeline.handoff.importer --response path/to/filled_template.md   # uses today's date
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.config.settings import IST, output_dir, today


def run(run_date: str | None, response_file: str) -> Path:
    date = run_date or today()
    src  = Path(response_file)
    if not src.exists():
        raise FileNotFoundError(f"Response file not found: {src}")

    out_dir = output_dir(date) / "handoff" / "after_l8"
    out_dir.mkdir(parents=True, exist_ok=True)

    content = src.read_text(encoding="utf-8")
    dest    = out_dir / "ai_analysis.md"
    dest.write_text(content, encoding="utf-8")

    summary = {
        "date":        date,
        "imported_at": datetime.now(IST).isoformat(),
        "source_file": str(src.resolve()),
        "saved_as":    str(dest),
        "char_count":  len(content),
        "note":        "Manual AI analysis — replaces L9 + L10 pipeline output.",
    }
    summary_path = out_dir / "import_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nHandoff imported:")
    print(f"  Analysis:  {dest}")
    print(f"  Summary:   {summary_path}")
    print(f"  Size:      {len(content):,} chars")
    print(f"\nFinal report for {date} is at:")
    print(f"  {dest}\n")
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import AI response as the pipeline's final report")
    parser.add_argument("--date",     default=None, help="Run date YYYY-MM-DD (default: today)")
    parser.add_argument("--response", required=True, help="Path to the AI's filled analysis file")
    args = parser.parse_args()
    run(args.date, args.response)
