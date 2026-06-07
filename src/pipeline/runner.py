"""
Master pipeline runner — run layers by number.

Layer selection is required. Nothing runs if omitted.
Layers always execute in canonical order regardless of input order.

Available layers:
    0  — Manifest        config YAMLs → run_manifest.json
    1  — Scraping        scrapers     → raw_records.json
    2  — Dedup + Filter  dedup+quality→ filtered_records.json
    3  — Intelligence    LLM extract  → enriched_records.json  (LLM)
    4  — Memory          recall+score → memory_context.json
    5  — Hypothesis      groups+LLM   → hypotheses.json        (LLM)
    6  — Target Select   score+bucket → selected_targets.json
    7  — Deep Dive       data collect → target_evidence_bundles.json
    8  — Evidence Build  join+assemble→ evidence_packets.json
    9  — Specialist      4 LLM agents → scorecards.json        (LLM)
    10 — Final Report   composite score + 2 LLM agents → final_report.md (LLM)

Usage:
    python -m src.pipeline.runner 0 1 2 3 4 5 6 7 8 9  # specific layers, today
    python -m src.pipeline.runner 9                     # just L9, today
    python -m src.pipeline.runner all                   # entire pipeline, today
    python -m src.pipeline.runner 7 8 9 10 --date 2026-05-23  # specific date
"""

import sys
import time
from datetime import datetime

from src.config.settings import IST, today

LAYERS = {
    0: ("L0", "src.pipeline.L0_manifest.runner"),
    1: ("L1", "src.pipeline.L1_scraping.runner"),
    2: ("L2", "src.pipeline.L2_dedup_quality.runner"),
    3: ("L3", "src.pipeline.L3_intelligence.runner"),
    4: ("L4", "src.pipeline.L4_memory.runner"),
    5: ("L5", "src.pipeline.L5_hypothesis.runner"),
    6: ("L6", "src.pipeline.L6_target_selection.runner"),
    7: ("L7", "src.pipeline.L7_deep_dive.runner"),
    8: ("L8", "src.pipeline.L8_evidence_builder.runner"),
    9:  ("L9",  "src.pipeline.L9_specialist.runner"),
    10: ("L10", "src.pipeline.L10_final_report.runner"),
}


def _run_layer(num: int, date: str) -> None:
    import importlib
    _, module_path = LAYERS[num]
    mod = importlib.import_module(module_path)
    mod.run(date)


def _fmt(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(
            "Usage: python -m src.pipeline.runner <layer> [layer ...] | all [--date YYYY-MM-DD]\n"
            f"Layers: {', '.join(str(n) for n in LAYERS)}  or  all\n"
            "Example: python -m src.pipeline.runner 0 1 2 3\n"
            "         python -m src.pipeline.runner 7 8 9 10 --date 2026-05-23"
        )
        sys.exit(1)

    # Extract --date YYYY-MM-DD if present
    date_override = None
    if "--date" in args:
        idx = args.index("--date")
        if idx + 1 >= len(args):
            print("--date requires a value: --date YYYY-MM-DD")
            sys.exit(1)
        date_override = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if args == ["all"]:
        requested = sorted(LAYERS.keys())
    else:
        requested = []
        for a in args:
            if not a.isdigit() or int(a) not in LAYERS:
                valid = ", ".join(str(n) for n in LAYERS)
                print(f"Unknown layer: {a!r}. Valid: {valid}  or  all")
                sys.exit(1)
            requested.append(int(a))
        requested = sorted(set(requested))

    date = date_override or today()
    layer_labels = [LAYERS[n][0] for n in requested]

    print(f"Date: {date}  |  Layers: {' → '.join(layer_labels)}")
    print("=" * 60)

    run_start = time.time()
    results: list[tuple[str, float, str]] = []

    for num in requested:
        label = LAYERS[num][0]
        t0 = time.time()
        start_clock = datetime.now(IST).strftime("%H:%M:%S")
        print(f"\n[{start_clock}] >>> {label}")
        try:
            _run_layer(num, date)
            elapsed = time.time() - t0
            results.append((label, elapsed, "ok"))
            print(f"  └─ {label} done in {_fmt(elapsed)}")
        except Exception as e:
            elapsed = time.time() - t0
            results.append((label, elapsed, f"FAILED: {e}"))
            print(f"  └─ {label} FAILED after {_fmt(elapsed)}: {e}")
            sys.exit(1)

    total = time.time() - run_start
    print("\n" + "=" * 60)
    print(f"Total: {_fmt(total)}")
    for label, elapsed, status in results:
        mark = "✓" if status == "ok" else "✗"
        print(f"  {mark} {label:4s}  {_fmt(elapsed):>8s}  {status}")


if __name__ == "__main__":
    main()
