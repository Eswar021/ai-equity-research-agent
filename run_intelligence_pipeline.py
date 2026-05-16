"""
run_intelligence_pipeline.py — Intelligence Layer end-to-end runner

Chains Layer 4 → Layer 5 → Layer 6 → Layer 7 → Layer 8 → Layer 9 → Layer 10.

Assumes Layers 1-3 (broad context → canonicalization → intelligence extraction)
have already produced output for the target date, i.e.:
  output/{date}/layer3/intelligence_bundle.json  (produced by L3 runner)

Usage:
  python run_intelligence_pipeline.py                          # full L4→L10, today's date
  python run_intelligence_pipeline.py --date 2026-05-10       # specific date
  python run_intelligence_pipeline.py --skip-to 7             # start from L7 (reuse L4-L6)
  python run_intelligence_pipeline.py --skip-to 9             # rerun only L9+L10
  python run_intelligence_pipeline.py --only 10               # run only L10
  python run_intelligence_pipeline.py --provider openai       # default provider
  python run_intelligence_pipeline.py --provider gemini
  python run_intelligence_pipeline.py --model gpt-4.1-mini    # model override
"""

from __future__ import annotations
import argparse
import sys
import time
import traceback
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.paths import (
    DB_MEMORY_DIR,
    PROJECT_ROOT,
)

_IST = timezone(timedelta(hours=5, minutes=30))

# ── Layer registry (order matters) ───────────────────────────────────────────

_LAYERS = [4, 5, 6, 7, 8, 9, 10]

_LAYER_NAMES = {
    4:  "Memory Qualification",
    5:  "Market & Opportunity Intelligence",
    6:  "Research Target Planner",
    7:  "Targeted Deep-Dive Extraction",
    8:  "Evidence Builder",
    9:  "Specialist Analysis Agents",
    10: "Portfolio Intelligence + Final Report",
}

# Required guard file that must exist before each layer can start
_GUARD_FILES = {
    4:  None,                                   # L4 has no hard upstream dependency
    5:  "layer3/intelligence_bundle.json",      # needs L3 output
    6:  "layer5/market_view.json",              # needs L5 output
    7:  "layer6/deep_dive_plan.json",           # needs L6 output
    8:  "layer7/target_raw_bundles.json",       # needs L7 output
    9:  "layer8/agent_context_packets.json",    # needs L8 output
    10: "layer9/target_specialist_scorecards.json",  # needs L9 output
}

# LLM-consuming layers (shown in ETA estimate)
_LLM_LAYERS = {5, 9, 10}


def run_pipeline(
    target_date: str,
    provider: str = "openai",
    model: str | None = None,
    skip_to: int | None = None,
    only_layer: int | None = None,
) -> None:
    base_out     = PROJECT_ROOT / "output" / target_date
    db_memory    = DB_MEMORY_DIR
    run_id       = f"RUN_{target_date.replace('-','_')}_PIPELINE_{datetime.now(_IST).strftime('%H%M')}"

    # Layer directory map
    layer_dirs = {n: base_out / f"layer{n}" for n in _LAYERS}

    # Decide which layers to run
    if only_layer is not None:
        layers_to_run = [only_layer]
    elif skip_to is not None:
        layers_to_run = [n for n in _LAYERS if n >= skip_to]
    else:
        layers_to_run = list(_LAYERS)

    print(f"\n{'='*65}")
    print(f"Intelligence Pipeline — {target_date}")
    print(f"Run ID    : {run_id}")
    print(f"Provider  : {provider}" + (f"  model={model}" if model else ""))
    print(f"Layers    : {layers_to_run}")
    print(f"Output    : {base_out}")
    print(f"{'='*65}\n")

    results: list[dict] = []
    pipeline_start = time.time()

    for layer_num in layers_to_run:
        name = _LAYER_NAMES[layer_num]
        guard = _GUARD_FILES.get(layer_num)

        # ── Guard check ───────────────────────────────────────────────────────
        if guard:
            guard_path = base_out / guard
            if not guard_path.exists():
                _fail(f"Layer {layer_num}: required input not found: {guard_path}\n"
                      f"  Run the preceding layer first, or use --skip-to {layer_num + 1}.")
                results.append({"layer": layer_num, "status": "skipped_missing_input"})
                break

        _header(layer_num, name, _LLM_LAYERS)
        t0 = time.time()

        try:
            _run_layer(
                layer_num  = layer_num,
                layer_dirs = layer_dirs,
                base_out   = base_out,
                db_memory  = db_memory,
                provider   = provider,
                model      = model,
                run_id     = run_id,
            )
            elapsed = time.time() - t0
            results.append({"layer": layer_num, "status": "success", "elapsed_s": round(elapsed, 1)})
            print(f"\n  ✓ Layer {layer_num} done in {elapsed:.0f}s\n")

            # ── L10 → L4 feedback: apply memory update instructions ───────────
            if layer_num == 10:
                _apply_memory_feedback(base_out / "layer10", db_memory, results)

        except SystemExit as e:
            # Layer runners call sys.exit(1) on fatal errors
            results.append({"layer": layer_num, "status": "failed", "error": f"sys.exit({e.code})"})
            _fail(f"Layer {layer_num} exited with code {e.code}. Stopping pipeline.")
            break

        except Exception as e:
            tb = traceback.format_exc()
            results.append({"layer": layer_num, "status": "failed", "error": str(e)})
            _fail(f"Layer {layer_num} raised: {e}\n{tb}")
            break

    _summary(results, pipeline_start)


def _run_layer(
    layer_num: int,
    layer_dirs: dict,
    base_out: Path,
    db_memory: Path,
    provider: str,
    model: str | None,
    run_id: str,
) -> None:
    """Import and call the run() function for the given layer number."""

    if layer_num == 4:
        from intelligence_layer.memory_qualification.layer4_runner import run as run4
        run4(
            layer3_dir   = base_out / "layer3",
            layer4_dir   = layer_dirs[4],
            db_memory_dir = db_memory,
            run_id       = run_id,
        )

    elif layer_num == 5:
        from intelligence_layer.market_opportunity_intelligence.layer5_runner import run as run5
        run5(
            layer3_dir = base_out / "layer3",
            layer4_dir = layer_dirs[4],
            layer5_dir = layer_dirs[5],
            run_id     = run_id,
            provider   = provider,
        )

    elif layer_num == 6:
        from intelligence_layer.research_target_planner.layer6_runner import run as run6
        run6(
            layer3_dir = base_out / "layer3",
            layer4_dir = layer_dirs[4],
            layer5_dir = layer_dirs[5],
            layer6_dir = layer_dirs[6],
            run_id     = run_id,
        )

    elif layer_num == 7:
        from intelligence_layer.targeted_deep_dive.layer7_runner import run as run7
        run7(
            layer6_dir = layer_dirs[6],
            layer7_dir = layer_dirs[7],
        )

    elif layer_num == 8:
        from intelligence_layer.evidence_builder.layer8_runner import run as run8
        run8(
            layer5_dir = layer_dirs[5],
            layer6_dir = layer_dirs[6],
            layer7_dir = layer_dirs[7],
            layer8_dir = layer_dirs[8],
        )

    elif layer_num == 9:
        from intelligence_layer.specialist_analysis.layer9_runner import run as run9
        run9(
            layer8_dir = layer_dirs[8],
            layer9_dir = layer_dirs[9],
            provider   = provider,
            model      = model,
        )

    elif layer_num == 10:
        from intelligence_layer.final_synthesis_layer.layer10_runner import run as run10
        run10(
            layer9_dir  = layer_dirs[9],
            layer8_dir  = layer_dirs[8],
            layer5_dir  = layer_dirs[5],
            layer6_dir  = layer_dirs[6],
            layer10_dir = layer_dirs[10],
            provider    = provider,
            model       = model,
        )

    else:
        raise ValueError(f"Unknown layer number: {layer_num}")


def _apply_memory_feedback(layer10_dir: Path, db_memory: Path, results: list[dict]) -> None:
    """Apply L10 memory update instructions to the L4 persistent store."""
    from intelligence_layer.memory_qualification.layer10_instruction_consumer import consume
    print(f"{'─'*65}")
    print(f"  L10 → L4 Feedback: applying memory update instructions")
    print(f"{'─'*65}")
    t0 = time.time()
    summary = consume(layer10_dir, db_memory)
    elapsed = time.time() - t0
    status = summary.get("status", "?")
    applied = summary.get("applied", 0)
    skipped = summary.get("skipped", 0)
    errors  = summary.get("errors", 0)
    print(f"        status={status}  applied={applied}  skipped={skipped}  errors={errors}  ({elapsed:.1f}s)")
    results.append({
        "layer":     "10→4 feedback",
        "status":    "success" if errors == 0 else "partial",
        "elapsed_s": round(elapsed, 1),
        "applied":   applied,
        "skipped":   skipped,
        "errors":    errors,
    })
    print(f"\n  ✓ Memory feedback done in {elapsed:.1f}s\n")


def _header(layer_num: int, name: str, llm_layers: set) -> None:
    tag = "  [LLM]" if layer_num in llm_layers else ""
    print(f"{'─'*65}")
    print(f"  Layer {layer_num} — {name}{tag}")
    print(f"{'─'*65}")


def _fail(msg: str) -> None:
    print(f"\n  ✗ {msg}\n", file=sys.stderr)


def _summary(results: list[dict], pipeline_start: float) -> None:
    total = time.time() - pipeline_start
    print(f"\n{'='*65}")
    print(f"Pipeline Summary  (total: {total:.0f}s)")
    print(f"{'='*65}")
    for r in results:
        layer = r["layer"]
        status = r["status"]
        elapsed = f"  {r['elapsed_s']:.0f}s" if "elapsed_s" in r else ""
        icon = "✓" if status == "success" else ("✗" if "failed" in status else "–")
        label = _LAYER_NAMES.get(layer, "")
        prefix = f"Layer {layer}" if isinstance(layer, int) else str(layer)
        display = f"{prefix} — {label}" if label else prefix
        print(f"  {icon} {display:50} {status}{elapsed}")
    print(f"{'='*65}\n")

    failed = [r for r in results if "failed" in r.get("status", "")]
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Intelligence Pipeline — chains Layer 4 through Layer 10"
    )
    parser.add_argument(
        "--date", default=date.today().strftime("%Y-%m-%d"),
        help="Target date (YYYY-MM-DD). Defaults to today."
    )
    parser.add_argument(
        "--provider", default="openai",
        help="LLM provider: openai | gemini | lmstudio"
    )
    parser.add_argument(
        "--model", default=None,
        help="Optional model override (e.g. gpt-4.1-mini, gemini-2.0-flash)."
    )

    skip_group = parser.add_mutually_exclusive_group()
    skip_group.add_argument(
        "--skip-to", type=int, metavar="LAYER",
        help="Skip to layer N (4-10). Earlier layers must already have output."
    )
    skip_group.add_argument(
        "--only", type=int, metavar="LAYER",
        help="Run only layer N (4-10). All inputs must exist."
    )

    args = parser.parse_args()

    if args.skip_to is not None and args.skip_to not in _LAYERS:
        parser.error(f"--skip-to must be one of {_LAYERS}")
    if args.only is not None and args.only not in _LAYERS:
        parser.error(f"--only must be one of {_LAYERS}")

    run_pipeline(
        target_date  = args.date,
        provider     = args.provider,
        model        = args.model,
        skip_to      = args.skip_to,
        only_layer   = args.only,
    )


if __name__ == "__main__":
    main()
