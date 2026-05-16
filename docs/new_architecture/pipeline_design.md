# New Pipeline Design — Layer-by-Layer Reference

This document captures the design decisions and simplification intent for the new
`src/pipeline/` system. Read this before planning or building any layer.

---

## Core Philosophy

**We are building a stock research tool, not a data engineering showcase.**
Every feature, module, and file must earn its place by making the final analysis
better. If it adds complexity without improving the final stock decision, cut it.

---

## Output Files Per Layer (always exactly these)

| File | Purpose |
|---|---|
| `output/{date}/L{N}/<data_file>.json` | Main output — consumed by next layer |
| `output/{date}/L{N}/summary.json` | Record counts, status, elapsed time |
| `output/{date}/L{N}/llm_calls.jsonl` | **Only for LLM layers.** Full prompt + response per call |

`llm_calls.jsonl` is JSONL (one JSON object per line). Written immediately after each
call so partial runs are inspectable. Contains: `call_id`, `timestamp`, `trigger`,
`model`, `prompt` (full), `response` (full), `parsed_ok`, `tokens_in`, `tokens_out`,
`latency_ms`.

**Layers with LLM → must write llm_calls.jsonl:** L3, L5, L9, L10
**Layers without LLM → no llm_calls.jsonl:** L0, L1, L2, L4, L6, L7, L8

---

## How Data Flows

The pipeline splits into two natural phases:

**Phase 1 — Per-document accumulation (L1 → L3)**
Each layer reads the same flat list of records and appends fields to each one.
The list grows richer but doesn't change shape.

```
L1: [{ id, source, content, ... }]
L2: [{ id, source, content, ..., quality_score, is_duplicate, reliability }]
L3: [{ id, source, content, ..., entities, facts, events, themes, signals }]
```

**Phase 2 — Cross-document synthesis (L5 onward)**
Layers here work across all documents and produce *new* objects:
hypotheses, targets, scorecards. These reference document IDs for traceability
but don't try to embed the full document.

```
L5: hypotheses.json      ← one per signal group, spans many docs
L6: selected_targets.json ← one per company selected for deep dive
L9: scorecards.json      ← one per target, specialist agent findings
```

**Key rule: embed context, don't chain IDs.**
Instead of entity_id → chunk_id → document_id → raw_file, just embed
`{ entity_name, supporting_text, source_name, reliability }` directly in the
object. No lookback needed, agents get full context in one place.

---

## Per-Layer Design

### L0 — Run Manifest
**Goal:** Snapshot all config into one file before any layer runs.

- Reads yaml config files → writes `run_manifest.json`
- All downstream layers read config from the manifest, never from yaml directly
- LLM: **no**
- Output: `run_manifest.json`

---

### L1 — Scraping
**Goal:** Collect raw data from all sources into one flat list.

- 12 sources: rss, moneycontrol, economic_times, newsdata_io, mediastack,
  gmail, youtube, india_macro, us_macro, fii_dii, bulk_deals, fno
- No filtering, no dedup, no scoring — just collect
- `market_snapshot` and `corporate_action` records: content = human-readable
  summary string, full data in `metadata.data`
- LLM: **no**
- Output: `raw_records.json` (flat list) + `summary.json`

---

### L2 — Dedup + Quality Filter
**Goal:** Remove noise before expensive LLM calls.

**Keep:**
- SHA-256 dedup on clean text — catches same article from 3 feeds
- Length filter — drop records under ~100 chars (no substance)
- Date filter — flag records with no publication date
- Source reliability tag — moneycontrol/ET = high, random RSS = medium/low

**Drop from old system:**
- Full "canonicalization ceremony" — text normalization, entity pre-extraction, etc.
- `quarantine.json`, `duplicate_map.json` — debug files, not needed in production
- `layer2_manifest.json` + `quality_report.json` — merge into one `summary.json`
- Chunk IDs — never needed downstream, only added complexity

**Data shape:** Same records as L1 + appended fields: `quality_score`, `is_duplicate`,
`reliability`, `passes_filter`. Records that fail filter are excluded from output.

- LLM: **no**
- Output: `filtered_records.json` + `summary.json`

---

### L3 — Intelligence Extraction
**Goal:** Extract structured intel from each document using LLM.

Per document, LLM extracts in one call:
- `entities` — companies, people, indices mentioned
- `facts` — hard data points (revenue, PE, price)
- `events` — things that happened (earnings, merger, regulatory action)
- `themes` — macro/sector themes (tariff uncertainty, rate cut)
- `market_signals` — directional signals relevant to investing

**Simplifications vs old system:**
- No chunk IDs downstream — chunks are created for LLM batching, discarded after
- No `entity_registry.json`, `fact_cards.json`, etc. — everything lives on the record
- No `contradiction_hints.json` (rule-based flag, not worth the complexity)
- LLM logs must include full prompt + response (old system only logged counts)
- Headlines < 200 chars batched together into one call — do not create one call per headline

**Data shape:** Same records as L2 + appended: `entities`, `facts`, `events`,
`themes`, `market_signals`, `extraction_confidence`.

- LLM: **yes** — one call per document (or batched headlines), structured JSON output
- Output: `enriched_records.json` + `summary.json`

---

### L4 — Memory
**Goal:** (1) Pull past relevant memory into this run. (2) Decide what to store.

**Recall:** Entity name lookup in `db/memory/entity_memory_index.json`.
Simple string match — not semantic search. Returns past memory records for
entities seen in this run. Embed the original supporting context in recalled
memories (old system stripped it — that was a bug).

**Store:** Score each extracted object for novelty + importance.
Write worthy objects to `db/memory/` JSONL files.

**Simplifications vs old system:**
- No 10-dimension scoring formula — use a simple 3-factor score: novelty, recency, importance
- No `memory_candidates.json`, `memory_decisions.json`, `new_memory_records.json`,
  `updated_memory_records.json`, `thesis_updates.json`, `memory_decay_report.json`,
  `memory_quality_report.json` — debug files, all dropped
- Output of this layer: one `memory_context.json` (past memories relevant to this run)
  + enriched records pass through unchanged

- LLM: **no** — entirely rule-based scoring and index lookup
- Output: `memory_context.json` (for L5) + `summary.json`
- Persistent side-effect: writes/updates `db/memory/` files

---

### L5 — Hypothesis Generation
**Goal:** Group related signals across documents → generate investable hypotheses.

1. Group signals by shared entities/themes (rule-based)
2. LLM call per group: "What is the investment hypothesis?"
3. Rule-based market regime assessment (from FII flows, VIX, breadth)

**LLM output per hypothesis:**
```json
{
  "hypothesis": "...",
  "beneficiaries": ["TCS", "Infosys"],
  "time_horizon": "medium_term",
  "strength": "medium",
  "deep_dive_questions": ["..."],
  "invalidating_conditions": ["..."]
}
```

**Simplifications vs old system:**
- Move hardcoded priority weights (high=30, medium=15) to `src/config/l5_config.yaml`
- Drop `cross_domain_chains.json` — was never implemented, always empty
- Drop `event_impact_views.json`, `sector_theme_views.json` — not consumed downstream
- Keep: `hypotheses.json` + `market_regime.json`
- Cap LLM calls configurable in manifest (default 50), not hardcoded in source

- LLM: **yes** — one call per signal group
- Output: `hypotheses.json` + `market_regime.json` + `summary.json`

---

### L6 — Target Selection
**Goal:** Score hypotheses → select targets worth deep-diving.

Pure rule-based scoring on each hypothesis. Produces three buckets:
`deep_dive`, `watchlist`, `skip`.

**Simplifications vs old system:**
- Move all weights and thresholds to `src/config/l6_config.yaml` (old system had magic
  numbers hardcoded in source — any tuning required editing code)
- No LLM

**Data shape:** New objects — targets with score, bucket, deep_dive_questions.

- LLM: **no**
- Output: `selected_targets.json` + `summary.json`

---

### L7 — Targeted Deep Dive
**Goal:** Collect company-specific data for each selected target.

Collectors per target:
- Market data — price, volume, 52-week range
- Fundamentals — P/E, ROE, debt/equity, revenue CAGR (from screener.in or similar)
- Peer comparison — sector peers
- Analyst estimates — consensus ratings
- Exchange filings — latest NSE filing
- Corporate actions — dividends, splits

**Key rule:** Build the code fresh in `src/`. Old `context_ext_layer/phaseC_*` modules
are reference only — do not import them.

- LLM: **no**
- Output: `target_bundles.json` (one entry per target, all collected data) + `summary.json`

---

### L8 — Evidence Builder
**Goal:** Join L3 intelligence + L7 fundamentals + L5 hypotheses into
self-contained agent packets.

Pure Python joins — no LLM. Each packet has everything an agent needs to
assess one target without reading any other file.

**Simplifications vs old system:**
- No intermediate files — go straight from inputs to `evidence_packets.json`
- Packets are intentionally self-contained (some duplication is fine — agents need context)

- LLM: **no**
- Output: `evidence_packets.json` (one per target) + `summary.json`

---

### L9 — Specialist Analysis Agents
**Goal:** Four agents assess each target from different angles.

| Agent | Question |
|---|---|
| `fundamental` | Is this a quality business? Revenue, margins, moat, management |
| `valuation` | Is it cheap? PE vs sector, upside to fair value |
| `risk` | Real risks + data gaps + red flags |
| `thesis_validation` | Does the evidence support the original hypothesis? |

Thesis agent runs **last** — receives the other three assessments as context.

**LLM calls:** 4 agents × N targets. Run concurrently per agent type.

- LLM: **yes** — 4 calls per target
- Output: `scorecards.json` (one per target, all four agent outputs) + `summary.json`

---

### L10 — Final Report
**Goal:** Synthesize scorecards → final decision + human-readable report.

1. Scoring formula (rule-based):
   `score = 0.25×fundamental + 0.20×valuation + 0.20×thesis + 0.20×(100-risk) + 0.15×market_alignment`
   All weights in `src/config/l10_config.yaml` — not hardcoded.
2. LLM call per target: final narrative synthesis + bull/base/bear scenarios
3. Report written in Markdown

**LLM calls:** 2 per target (synthesis + scenarios). Everything else is rule-based.

- LLM: **yes** — 2 calls per target
- Output: `final_report.md` + `watchlist_actions.json` + `summary.json`
- Persistent side-effect: writes memory instructions back to `db/memory/`

---

## What NOT to Build (for any layer)

- Per-layer audit log files — they exist for debugging, not for production
- Separate files for subsets of the same data (e.g., `new_records.json` +
  `updated_records.json` when one `decisions.json` would do)
- Chunk IDs — chunks are a batching mechanism, not a data concept
- Scoring formulas with magic numbers in source code — all weights go in config
- Cross-layer data lookups via ID chains — embed context directly
- Any module that doesn't contribute to the final analysis quality
