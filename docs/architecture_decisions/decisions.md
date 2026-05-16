# Architecture Decision Log

Tracks every deliberate deviation from the system design docs.
Format: what the doc proposed → what we built → why.

---

## Layer 6 — Research Target Planner

### ADR-L6-001: No LLM in Layer 6
- **Design doc proposed:** Not explicitly stated — doc described complex target mapping
- **What we built:** Fully rule-based pipeline, zero LLM calls
- **Why:** L5 LLM already names real NSE companies with tickers in `likely_beneficiaries_or_targets`. L6 just structures, validates, deduplicates, and scores that output. Adding an LLM here would add cost and latency with no meaningful improvement in quality.

### ADR-L6-002: fund_vehicle_mapper is a stub (returns [])
- **Design doc proposed:** Fund/ETF/REIT/InvIT mapping for fund-type unresolved targets
- **What we built:** Stub that returns `[]`
- **Why:** No fund/ETF data layer exists yet. L5 doesn't produce fund-type hypotheses in practice. Will build when L5 starts generating fund opportunities.

### ADR-L6-003: proxy_mapper uses sibling beneficiaries only (no LLM)
- **Design doc proposed:** LLM-generated proxy tickers for private/unlisted companies
- **What we built:** Collects sibling beneficiaries from the same hypothesis that already have tickers — no LLM
- **Why:** Calling LLM to identify proxies adds latency and hallucination risk. The hypothesis already lists other beneficiaries with tickers; those are better proxies than anything an LLM would generate cold.

### ADR-L6-004: target_type_classifier normalizes 80+ L5 type strings
- **Design doc proposed:** Clean target types from L5
- **What we built:** Priority-ordered keyword mapping (exchange suffix → direct map → opp_type map → keyword scan on hint → keyword scan on name → ticker present → unknown)
- **Why:** L5 LLM produces inconsistent type strings ("listed NSE company", "NSE-listed", "stock", "equity", etc.). A normalization layer is necessary. 80+ strings → 8 canonical types.

### ADR-L6-005: Deduplication by ticker then normalized name
- **Design doc proposed:** Deduplication (no specific algorithm prescribed)
- **What we built:** Primary key = ticker (strips .NS/.BO suffix), secondary key = normalized name (lowercase, strip Ltd/Limited/Corp/India/Technologies). Groups are merged: highest confidence wins, source_opportunity_ids combined.
- **Why:** L5 produces 101 resolved candidates for the same 24 actual companies because each hypothesis generates its own beneficiary list. Without this dedup, priority scoring and selection are skewed toward companies mentioned in many hypotheses.

---

## Layer 7 — Targeted Deep-Dive Extraction

### ADR-L7-001: parameter_validator.py — not built as separate module
- **Design doc proposed:** Separate `parameter_validator.py` to validate ticker format, date ranges, target type compatibility before execution
- **What we built:** Inline validation in `target_task_expander.py` — tasks with missing required params are skipped with a recorded reason
- **Why:** All current L6-selected targets are `listed_company` with valid `.NS` tickers. There are no edge cases to validate (no SEC-only modules, no private companies without tickers, no F&O-ineligible checks). Separate module adds boilerplate without value at this stage.

### ADR-L7-002: layer7_audit_logger.py — not built as separate module
- **Design doc proposed:** Separate `layer7_audit_logger.py` for lineage and execution audit trail
- **What we built:** Execution audit merged into the runner summary + `target_extraction_status.json` already captures per-task lineage
- **Why:** The status tracker already records task_id, module, target_id, status, error, record_count, output_path. That IS the audit trail. A separate logger module would just duplicate this data.

### ADR-L7-003: Call fetch_* functions, not save_* functions, from Phase C collectors
- **Design doc proposed:** `collector_registry_adapter.py` maps to `save_market_snapshot`, `save_price_history`, etc.
- **What we built:** Maps to `fetch_stock`, `fetch_history`, `fetch_peer_comparison`, `fetch_analyst_estimates`, `fetch_announcements`, `extract_company` — then Layer 7 writes the result to its own target directory
- **Why:** Phase C `save_*` functions hardcode output to Phase C directories (`MARKET_DATA_OUTPUT_DIR`, etc.). Layer 7 must write to `layer7/targets/TARGET_xxx/`. The `fetch_*` functions return the data dict; Layer 7 controls where it lands. This keeps both pipelines independent.

### ADR-L7-004: screener_in uses URL derived from ticker
- **Design doc proposed:** `screener_in` task params include `ticker` and optionally `screener_url`
- **What we built:** Layer 7 derives `https://www.screener.in/company/{BARE_SYMBOL}/` from the ticker (strip `.NS`/`.BO`) and passes it to `extract_company(url)`
- **Why:** `screener_in.extract_company()` takes a URL, not a ticker. The mapping from NSE ticker to screener URL is deterministic and reliable. No need for a separate URL lookup.

### ADR-L7-005: Parallel tasks within target, sequential targets
- **Design doc proposed:** `max_parallel_targets: 3`, `max_parallel_tasks_per_target: 4`
- **What we built:** Targets run sequentially; tasks within each target run with `ThreadPoolExecutor(max_workers=4)`
- **Why:** Running multiple targets in parallel would simultaneously stress screener.in and NSE APIs. Sequential targets with parallel tasks per target achieves meaningful speed-up (6 tasks → ~4 in parallel) while being gentler on external APIs and easier to debug when one target fails.

### ADR-L7-006: Non-listed-company collectors not built
- **Design doc proposed:** Build collectors for private_company, sector_theme, macro_target, fund/ETF, commodity, real_estate
- **What we built:** Only listed_company collectors (via Phase C fetch functions)
- **Why:** All 7 L6-selected targets for 2026-05-10 are `listed_company`. No other target type was selected (sector/macro targets scored below selection threshold). Build when L6 starts selecting those types.

### ADR-L7-007: targeted_news.py not built
- **Design doc proposed:** Step 4 in implementation order — every selected target gets recent target-specific news
- **What we built:** Not included in this layer
- **Why:** `targeted_news` is not in L6's `deep_dive_module_mapper.py` output for `standard` depth. The correct fix is to add it to the L6 module mapper and then build the collector. Building a collector not used by the plan would produce orphaned data.

### ADR-L7-008: filing_docs.py, stock_fno_data.py, sec_filings.py not built
- **Design doc proposed:** Part of listed company Type 1 collector group
- **What we built:** Not included
- **Why:** Not assigned by L6's standard depth module mapper. `filing_docs` (concall transcripts) is expensive and slow. `sec_filings` is for US tickers. `stock_fno_data` is for deep depth only. Will include when L6 assigns them.

### ADR-L7-009: coverage_validator uses keyword-based question → module mapping
- **Design doc proposed:** Coverage validator checks whether collected data can answer L6's research questions
- **What we built:** Keyword-based mapping from question text to modules that would cover it (e.g., "margin" → screener_in + analyst_estimates, "management" → filing_docs, "valuation" → peer_comparison + screener_in)
- **Why:** There is no semantic NLP needed here — the question categories are narrow and predictable. A dict-based keyword matcher is fast, transparent, and sufficient for flagging coverage gaps. Semantic matching is overkill.

---

## Layer 8 — Evidence Builder

### ADR-L8-001: Layer 8 reads L7 raw JSON directly — no L2-targeted or L3-targeted pass
- **Design doc proposed:** L7 output → L2 (Source Canonicalization, targeted pass) → L3 (Intelligence Extraction, targeted pass) → L8. The idea is that every raw collected data must be canonicalized and have intelligence extracted before L8 can build evidence from it.
- **What we built:** Layer 8 reads L7 target JSON files directly (`market_data.json`, `screener_in.json`, `peer_comparison.json`, `analyst_estimates.json`, `price_history.json`, `exchange_filings.json`). No L2-targeted or L3-targeted pass is executed.
- **Why:** L7's output for listed companies is entirely structured JSON — there is no unstructured text that needs canonicalization or NLP intelligence extraction. The design doc's L2/L3 targeted pass is necessary only when L7 collects long-form text (concall transcripts from `filing_docs`, investor presentations, annual report PDFs). Since `filing_docs` is not assigned in L6's `standard` depth plan, L7 produced zero unstructured text. Running L2/L3 on already-structured financial JSON would add pipeline steps with no benefit. When L6 starts assigning `filing_docs` or `targeted_news`, the L2-targeted + L3-targeted passes should be built and inserted between L7 and L8.
- **Impact:** L8 evidence cards reference L7 file paths as their source lineage (e.g., `output/.../layer7/targets/.../screener_in.json`) rather than L2 canonical document IDs. This is a simplification — source traceability still exists, just at the L7 file level rather than L2 canonical level.
- **When to revisit:** When `filing_docs`, `targeted_news`, or any text-heavy collector is added to the L6 standard depth plan. At that point, build L2-targeted (text normalization, deduplication, source ledger) and L3-targeted (fact/claim/event extraction from transcripts and filings) as separate pipeline stages.

### ADR-L8-002: text_chunker, vector_index_builder, retrieval_index_registry not built
- **Design doc proposed:** Chunk long-form text documents, build vector embeddings, create retrieval index for targeted question answering
- **What we built:** Not built
- **Why:** Directly follows from ADR-L8-001. No long-form text exists in L7 output. Exchange filings are structured announcement lists (date, subject, category) — not full text bodies. Building a text pipeline with nothing to chunk would produce empty artifacts. These modules should be built together with the L2/L3 targeted pass when `filing_docs` is added.

### ADR-L8-003: event_price_reaction_feature_engineer not built
- **Design doc proposed:** For each L3 event card (earnings release, management change, regulatory event, etc.), compute stock price return on event day, +1d, +3d, +5d, +10d and volume spike ratio
- **What we built:** Not built
- **Why:** This requires L3-targeted event cards — structured `EVT_*` objects that identify which event happened on which date for which company. Since we skipped the L3-targeted pass (ADR-L8-001), no event cards exist. The raw data is available (exchange_filings has announcement dates and subjects; price_history has daily prices), but we'd be partially reconstructing L3's job inside L8. Build this when L3-targeted is added.

### ADR-L8-004: macro_feature_engineer replaced by inline L5 market_view extraction
- **Design doc proposed:** Separate `macro_feature_engineer.py` that reads FII/DII flow records, VIX history, USD/INR series, bond yield series, inflation data from macro_records and market_signal_cards
- **What we built:** Inline macro feature extraction in `evidence_input_loader.py` from L5's `market_view` object (which already has FII/DII net, VIX, USD/INR, regime, favored_sectors, avoid_sectors, breadth A/D ratio)
- **Why:** L5's `market_view` is already a computed market state summary. Re-reading the L1/phase-A macro raw files to recompute the same things L5 already computed would be redundant. L5 is the authoritative macro signal source.

### ADR-L8-005: contradiction_anomaly_checker not built
- **Design doc proposed:** Compare management claims (from L3 claim cards) against computed numeric features — e.g., management says "margin improving" but fundamental_feature_engineer shows operating margin declining
- **What we built:** Not built
- **Why:** Requires L3 claim cards (structured `CLAIM_*` objects with claim_text and sentiment direction). Without the L3-targeted pass, no claim cards exist for targeted companies. The numeric features to compare against DO exist (from our feature engineers), but there's nothing to compare them with on the text side. Build when L3-targeted is added.

### ADR-L8-006: evidence_deduplicator not built
- **Design doc proposed:** Deduplicate evidence cards where the same fact appears from multiple sources
- **What we built:** Not built — evidence cards generated without duplication
- **Why:** Each source file (market_data, screener_in, etc.) is used exactly once per target. There is no cross-source overlap that could produce the same numeric feature twice. Deduplication becomes necessary when multiple collectors or multiple articles assert the same fact about the same metric.

### ADR-L8-007: source_traceability_mapper not built as standalone module
- **Design doc proposed:** Separate `source_traceability_mapper.py` that creates a formal lineage map: fact → document → source
- **What we built:** Source refs attached inline in `evidence_card_builder.py` directly referencing L7 output paths
- **Why:** Formal lineage maps (fact → L2 document ID → L2 source record ID → L1 raw file) are meaningful only when L2/L3 canonical IDs exist. Since we bypassed those (ADR-L8-001), there are no `DOC_*` or `CSRC_*` IDs to link to. Instead each evidence card carries `source_path` (the L7 JSON file) and `source_module` (e.g., "screener_in"). That IS the lineage at our current pipeline depth.

### ADR-L8-008: evidence_schema_validator and lineage_validator not built as standalone modules
- **Design doc proposed:** Separate validator modules to check evidence card schema completeness and source lineage
- **What we built:** Inline validation in evidence_card_builder and layer8_runner
- **Why:** At current scale (7 targets × ~6 evidence cards each = ~42 cards), standalone validator modules add more file overhead than value. The required fields (evidence_id, target_id, source_path) are guaranteed by construction in the builder. Standalone validators become valuable when evidence card count grows into hundreds.

### ADR-L8-009: agent_context_packet_builder builds 4 agent types, not 8
- **Design doc proposed:** Packets for 8 specialist agents: Market Agent, Sector Agent, Stock Fundamental Agent, Valuation Agent, Event Impact Agent, Risk Agent, Opportunity Proxy Agent, Thesis Agent
- **What we built:** 4 agent types: fundamental_agent, valuation_agent, risk_agent, thesis_agent
- **Why:** Market Agent and Sector Agent need sector/theme targets — we have none selected (all 7 are listed companies). Event Impact Agent needs event_price_reaction features (not built, ADR-L8-003). Opportunity Proxy Agent needs proxy mappings and cross-domain chains — no private company targets selected. The 4 agents we build cover the full evidence surface for all 7 selected listed company targets.

---

## Cross-Layer

### ADR-CROSS-001: Folder convention — intelligence_layer/ for L4–L7
- **Design doc proposed:** `targeted_deep_dive_layer/` for Layer 7
- **What we built:** `intelligence_layer/targeted_deep_dive/`
- **Why:** Consistent with L4 (`memory_qualification/`), L5 (`market_opportunity_intelligence/`), L6 (`research_target_planner/`). All intelligence-layer modules live under `intelligence_layer/`. Diverging to a top-level folder for L7 would break the pattern without benefit.

### ADR-CROSS-002: Phase naming continues alongside Layer naming
- **Design doc proposed:** Full rename to layer-based naming
- **What we built:** Phase A/B/C directories continue; Layer 1–7 directories added in parallel
- **Why:** Too many import sites reference `phaseX_*` paths. Renaming would break existing working collectors. The Layer N outputs are the canonical contract surfaces; Phase outputs remain internal.

---

## Layer 9 — Specialist Analysis Agents

### ADR-L9-001: Thesis agent runs last and receives prior_assessments
- **Design doc proposed:** Unclear ordering; implied parallel execution of all agents
- **What we built:** Orchestrator separates prereq_tasks (fundamental, valuation, risk) from thesis_tasks; thesis always receives `prior_assessments` from the other 3
- **Why:** Thesis validation synthesizes ALL specialist views — it cannot run in parallel. Running it last ensures it sees the full picture of fundamental quality, valuation attractiveness, and risk before assessing thesis strength.

### ADR-L9-002: Inline guardrails in orchestrator — no dedicated guardrail module
- **Design doc proposed:** Separate `schema_validator.py`, `evidence_reference_checker.py`, `hallucination_guardrail.py` modules
- **What we built:** `_enforce_not_final_recommendation`, `_ensure_required_fields`, `_check_forbidden_language` inline in `agent_execution_orchestrator.py`
- **Why:** At 4 agent types and 7 targets, separate guardrail modules add file overhead without benefit. The inline checks are 30 lines total and handle the core invariants. Forbidden-phrase detection catches the main failure mode (agents slipping into final-recommendation language).

### ADR-L9-003: 4 agent types, not 8-13 as designed
- **Design doc proposed:** 8-13 specialist agents including Market Agent, Sector Agent, Event Impact Agent, Opportunity Proxy Agent, etc.
- **What we built:** 4 agents: fundamental_agent, valuation_agent, risk_agent, thesis_agent
- **Why:** Matches ADR-L8-009. Market/Sector agents need sector/theme targets (none selected). Event Impact agent needs event_price_reaction features (not built). Opportunity Proxy agent needs private company targets (none). The 4 agents fully cover the evidence surface for all 7 selected listed company targets.

### ADR-L9-004: method="function_calling" for all LLM structured outputs
- **Design doc proposed:** Default `with_structured_output` (which uses OpenAI's structured output mode)
- **What we built:** `llm.with_structured_output(Schema, method="function_calling")` for all 4 agents
- **Why:** OpenAI's strict structured output mode rejects schemas with `dict[str, int]` and other flexible types. Function calling is more permissive and allows the custom validation logic we need. The tradeoff (slightly less strict JSON schema enforcement) is acceptable given we validate with Pydantic on receipt.

### ADR-L9-005: Flat score fields in Pydantic models instead of nested dict
- **Design doc proposed:** `dimension_scores: dict[str, int]` in all agent schemas
- **What we built:** Individual score fields (`growth_score`, `profitability_score`, etc.) in Pydantic models; `run()` assembles them into `dimension_scores: dict` in the output
- **Why:** OpenAI function_calling mode with nested dicts causes the model to return scores as top-level fields (flattened) rather than nested. Explicit individual fields in the schema produces correct outputs. The caller (scorecard builder) receives the correct nested dict format unchanged.

### ADR-L9-006: field_validator coercion for str→list and int→float
- **Design doc proposed:** Strict Pydantic types with no coercion
- **What we built:** `@field_validator` on all `list[str]` fields (coerces string "None" → []) and `confidence` fields (coerces 0-100 integer → 0.0-1.0 float)
- **Why:** gpt-5-nano occasionally returns `invalidating_conditions_triggered: "None found."` (string) instead of `[]`, and returns `confidence: 75` (integer, 0-100 scale) instead of `0.75`. Both are semantic failures that validators can safely recover from rather than crashing the agent task.
