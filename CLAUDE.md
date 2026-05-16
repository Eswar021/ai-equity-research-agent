# Stock Researcher — Claude Code Instructions

This file is loaded automatically by Claude Code at the start of every session.
Follow everything here before generating any code.

**Before planning or building any layer:** read
`docs/new_architecture/pipeline_design.md` — it contains the per-layer design
intent, what to simplify, and what NOT to build. Do not start implementing a
layer without reading that first.

---

## Project Architecture

We are building a clean, layered stock research pipeline under `src/pipeline/`.
The old system under `context_ext_layer/` and `intelligence_layer/` exists only as
reference — **never import from it**. We are building everything fresh in `src/`.

```
src/
├── config/
│   ├── settings.py          ← global constants: PROJECT_ROOT, OUTPUT_BASE, IST
│   └── l1_sources.yaml      ← L1 source config (each layer adds its own yaml later)
└── pipeline/
    ├── L0_manifest/
    │   └── runner.py        ← reads config files → writes run_manifest.json
    ├── L1_scraping/
    │   ├── runner.py        ← reads manifest → calls scrapers → writes raw_records.json
    │   └── scrapers/        ← one file per source, each exposes collect(cfg) -> list[dict]
    └── L{N}_*/
        └── runner.py        ← reads manifest + prior layer output → writes this layer's output
```

**Data flow per run:**
```
L0: output/{date}/run_manifest.json        ← config snapshot for the entire run
L1: output/{date}/L1/raw_records.json      ← all scraped records, flat list
L2: output/{date}/L2/...                   ← dedup + quality filter
...
```

**Golden rules:**
- Each layer writes **one data file** + **one summary.json** — nothing else
- Every layer reads config from `run_manifest.json`, not from yaml files directly
- Each layer's output is the **only** input the next layer reads
- No layer imports from another layer's module — only from `src/config/` and `src/pipeline/L{N}/`

---

## Coding Philosophy

### Keep It Visible
- Small, focused functions — one logical unit each
- No deep call chains; the reader should be able to trace a full execution path in one file
- Use `if __name__ == "__main__"` as a manual test harness during development

### Fail Hard
Do not silently continue when assumptions break:
- Missing expected input file → `FileNotFoundError`, stop
- Config key missing → `KeyError`, stop  
- Broken schema / unexpected data shape → raise immediately
- Bad env var (missing API key) → `RuntimeError("X env var not set")`, stop

Silent fallbacks hide bugs that surface much later in much harder-to-trace forms.

### No Premature Abstraction
- Write the direct solution first
- Three similar lines are better than a premature helper
- Extract a function only when you need it in a second place
- No base classes, no registries with dynamic dispatch, no plugin systems — not yet

### Config Lives in the Manifest
- Source config (enabled, days_back, queries, etc.) comes from `run_manifest.json`
- Scrapers accept `cfg: dict` as a parameter — they do not load yaml files themselves
- Thresholds and tuning values go in per-layer yaml files in `src/config/`

---

## Standard Record Format (L1 output)

Every scraper returns `list[dict]`. The L1 runner assigns `id` and writes to output.

```python
{
    "id":           "L1_20260517_0001",   # assigned by runner
    "source":       "moneycontrol",       # matches yaml/manifest key
    "source_type":  "news_article",       # see below
    "title":        str | None,
    "url":          str | None,
    "published_at": str | None,           # ISO-8601, IST preferred
    "content":      str,                  # full text — this is what LLMs read
    "metadata":     dict,                 # source-specific extras, keep minimal
}
```

**source_type values:**
- `news_article` — moneycontrol, economic_times, rss, newsdata_io, mediastack
- `newsletter` — gmail
- `video_transcript` — youtube
- `market_snapshot` — india_macro, us_macro, fii_dii, fno
- `corporate_action` — bulk_deals

For `market_snapshot` and `corporate_action`: `content` is a human-readable summary
string. Full structured data goes in `metadata.data`.

---

## Module Pattern for Scrapers

```python
# Each scraper follows this exact shape:

def collect(cfg: dict) -> list[dict]:
    """
    cfg: this scraper's slice from run_manifest["layer_1"]["<source_name>"]
    Returns list of standard records (without "id" — runner assigns that).
    Raises on hard failures. Returns empty list only when genuinely no data.
    """
    ...
```

Scrapers **do not** load yaml files. They receive config as a dict parameter.

---

## Layer Runner Pattern

```python
def run(run_date: str | None = None) -> Path:
    date    = run_date or today()
    manifest = load_manifest(date)          # raises if missing — fail hard
    cfg      = manifest["layer_N"]

    # ... do the work ...

    out_path = output_dir(date) / "LN" / "output_file.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    summary_path = output_dir(date) / "LN" / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    return out_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    run(args.date)
```

---

## LLM Call Logging

Every layer that calls an LLM **must** write a full log of every call.

**Location:** `output/{date}/L{N}/llm_calls.jsonl`
One line per call (JSONL). Appended as calls complete — do not batch-write at the end.

**Required fields per entry:**
```python
{
    "call_id":     "L3_20260517_0042",          # layer + date + sequential counter
    "timestamp":   "2026-05-17T09:45:32+05:30", # IST, ISO-8601
    "layer":       "L3",
    "trigger":     "record L1_20260517_0123",    # what caused this call (record id, group id, etc.)
    "model":       "claude-sonnet-4-6",
    "prompt":      "...",                        # full prompt sent — no truncation
    "response":    "...",                        # full raw response received
    "parsed_ok":   True,                         # did response parse into expected schema?
    "tokens_in":   1240,
    "tokens_out":  380,
    "latency_ms":  1820
}
```

**Rules:**
- Log the **full** prompt and **full** response — never truncate. If a log is big, that's fine.
- Write the entry immediately after the call returns, not at layer end (so partial runs are inspectable)
- If parsing the response fails, still log it with `"parsed_ok": false` and `"parse_error": "..."`
- `llm_calls.jsonl` is the **third** output file allowed per layer (in addition to data + summary)
  — it does not violate the one-data-file rule

**Layers that must write llm_calls.jsonl:** L3, L5, L9, L10 (any layer with LLM calls).
**Layers with no LLM:** L0, L1, L2, L4, L6, L7, L8 — no llm_calls.jsonl needed.

---

## Run Manifest Shape

`output/{date}/run_manifest.json` — written by L0 before any other layer runs.

```json
{
  "run_date": "2026-05-17",
  "run_id":   "RUN_20260517_0930",
  "created_at": "2026-05-17T09:30:00+05:30",
  "layer_1": {
    "rss":            { "enabled": true,  "feeds": [...] },
    "moneycontrol":   { "enabled": true,  "days_back": 2, "max_pages": 5, "categories": [...] },
    "economic_times": { "enabled": true,  "days_back": 2, "max_pages": 5, "categories": [...] },
    "newsdata_io":    { "enabled": true,  "queries": [...] },
    "mediastack":     { "enabled": true,  "queries": [...] },
    "gmail":          { "enabled": true,  "max_per_source": 5, "sources": [...] },
    "youtube":        { "enabled": true,  "days_back": 3, "channels": [...] },
    "india_macro":    { "enabled": true  },
    "us_macro":       { "enabled": true  },
    "fii_dii":        { "enabled": true  },
    "bulk_deals":     { "enabled": true  },
    "fno":            { "enabled": true,  "symbols": ["NIFTY", "BANKNIFTY"] }
  }
}
```

Each new layer appends its own key (`layer_2`, `layer_3`, ...) as it is built.

**How to add a new layer's config to the manifest (do this every time):**

1. Create `src/config/l{N}_<name>.yaml` with the layer's thresholds and settings.
   Top-level key must be `layer_{N}:` (e.g. `layer_2:`, `layer_3:`).
2. Add a `_load_l{N}_config()` function to `src/pipeline/L0_manifest/runner.py`
   that loads the yaml and validates the top-level key exists.
3. Call it in `run()` and add the result to the manifest dict as `"layer_{N}": l{N}_cfg`.
4. Update the L0 docstring (Reads: / Module execution order:) to mention the new yaml.
5. Re-run L0 before running the new layer — the manifest must contain the key.

Layers with no configurable thresholds (e.g. a pure-transform layer) can skip the yaml
and instead write their config directly as a literal dict inside `_load_l{N}_config()`.

---

## Layers Are Self-Contained Applications

Each layer (`L0`, `L1`, `L2`, ...) is a standalone application. It has one job,
one input contract, and one output contract. Treat it that way:

**What a layer owns:**
- Its own runner (`runner.py`) and all internal modules under `src/pipeline/L{N}_*/`
- Its own section in `run_manifest.json` for config
- Its own output directory `output/{date}/L{N}/`

**How layers communicate — data files only, never code:**
- A layer reads its upstream's output file (e.g. L2 reads `L1/raw_records.json`)
- It writes its own output file (e.g. L2 writes `L2/filtered_records.json`)
- That output file is the only thing the next layer touches
- No layer ever imports a function or class from another layer's source code

**The data accumulates forward:**
- Records gain fields as they move through layers — L2 adds `quality_score`,
  L3 adds `signals`, L4 adds `memory_tags`, etc.
- Later layers append to the record shape; they do not look backwards to reconstruct
  what an earlier layer had
- If a layer needs something from two layers back, it means the intermediate layer
  should have carried that field forward

**Consequences of this design:**
- You can re-run any single layer independently (given its input file exists)
- You can inspect what any layer produced without running the whole pipeline
- A bug in L5 cannot corrupt L1–L4 output
- Adding a new layer never requires modifying an existing one

---

## Runner Docstring Standard

Every `runner.py` must have a module-level docstring that answers these questions:

```python
"""
L{N} <Layer Name> — one-line description of what this layer does.

Reads:
    output/{date}/run_manifest.json        → layer_{n} config key
    output/{date}/L{N-1}/<input_file>.json → upstream data

Writes:
    output/{date}/L{N}/<output_file>.json  → main output (consumed by next layer)
    output/{date}/L{N}/summary.json        → record counts, status, elapsed time
    output/{date}/L{N}/llm_calls.jsonl     → (LLM layers only) full prompt+response per call

LLM: yes / no  (if yes: which provider/model, what it is called for)

Module execution order (internal):
    1. load manifest + upstream input
    2. <first processing step — e.g. dedup>
    3. <second step — e.g. quality filter>
    4. write output

Usage:
    python -m src.pipeline.L{N}_<name>.runner              # today
    python -m src.pipeline.L{N}_<name>.runner --date YYYY-MM-DD
"""
```

Keep the docstring factual and short. It is the first thing anyone reads when
they open the file — it should answer "what does this do, what does it need,
and does it call an LLM" in under 20 lines.

---

## What NOT to Do

- Do not import anything from `context_ext_layer/` or `intelligence_layer/`
- Do not import code from another layer (e.g. L3 must not import from L2's modules)
- Do not write multiple output files per layer (no audit logs, no redundant copies)
- Do not add silent `except: pass` or `except: return []` inside core logic
- Do not hardcode config values — they belong in yaml → manifest
- Do not add error handling for impossible cases
- Do not add comments explaining what the code does — name things well instead
- Do not create helper abstractions before you have two real callers
