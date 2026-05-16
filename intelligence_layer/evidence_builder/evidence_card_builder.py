"""
intelligence_layer/evidence_builder/evidence_card_builder.py — Layer 8

Builds atomic evidence cards from computed feature groups and L7 raw data.

Each evidence card = one verifiable fact/metric with source traceability.
Cards are typed: numeric_feature, filing_fact, analyst_estimate, peer_comparison,
                 market_signal, missing_data_gap
"""

from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_EVID_COUNTER = [0]


def _next_id(date_str: str) -> str:
    _EVID_COUNTER[0] += 1
    return f"EVID_{date_str}_{_EVID_COUNTER[0]:04d}"


def build_all_cards(
    scope:        dict,
    price_feats:  dict,
    fund_feats:   dict,
    val_feats:    dict,
    peer_feats:   dict,
    analyst_feats: dict,
    date_str:     str,
) -> list[dict]:
    """Build all evidence cards for one target. Returns list of card dicts."""
    cards: list[dict] = []
    tid  = scope["target_id"]
    name = scope["target_name"]
    ticker = scope["ticker"]

    pf = price_feats.get("features", {})
    ff = fund_feats.get("features", {})
    vf = val_feats.get("features", {})
    peer_f = peer_feats.get("features", {})
    af = analyst_feats.get("features", {})

    target_dir = scope.get("target_dir", "")

    # ── 1. Price cards ─────────────────────────────────────────────────────────
    cur_price = pf.get("current_price")
    h52 = pf.get("52w_high")
    l52 = pf.get("52w_low")
    dist_high = pf.get("distance_from_52w_high_pct")

    if cur_price is not None:
        stmt = f"{name} is trading at ₹{cur_price:,.1f}"
        if dist_high is not None:
            stmt += f", {abs(dist_high):.1f}% below its 52-week high of ₹{h52:,.1f}" if dist_high < 0 else f", near its 52-week high of ₹{h52:,.1f}"
        if h52 and l52:
            stmt += f" (52w range: ₹{l52:,.1f}–₹{h52:,.1f})"
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="price",
            statement=stmt,
            data={"current_price": cur_price, "52w_high": h52, "52w_low": l52,
                  "distance_from_52w_high_pct": dist_high},
            supports=["price_analysis", "valuation_analysis"],
            source_path=f"{target_dir}/market_data.json",
            feature_group_id=price_feats["feature_group_id"],
            confidence=0.95,
        ))

    returns = {k: pf.get(k) for k in ("return_1m_pct", "return_3m_pct", "return_1y_pct") if pf.get(k) is not None}
    if returns:
        parts = [f"{k.replace('_pct','').replace('return_','')}: {v:+.1f}%" for k, v in returns.items()]
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="price",
            statement=f"Recent returns for {name}: {', '.join(parts)}",
            data=returns,
            supports=["price_analysis", "momentum_analysis"],
            source_path=f"{target_dir}/market_data.json",
            feature_group_id=price_feats["feature_group_id"],
            confidence=0.95,
        ))

    max_dd = pf.get("max_drawdown_1y_pct")
    vol    = pf.get("volatility_30d")
    if max_dd is not None:
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="price",
            statement=f"{name} max drawdown over 1Y: {max_dd:.1f}%, 30-day daily volatility: {vol:.4f}" if vol else f"{name} max drawdown over 1Y: {max_dd:.1f}%",
            data={"max_drawdown_1y_pct": max_dd, "volatility_30d": vol},
            supports=["risk_analysis"],
            source_path=f"{target_dir}/price_history.json",
            feature_group_id=price_feats["feature_group_id"],
            confidence=0.92,
        ))

    sma200 = pf.get("sma_200")
    vs_sma200 = pf.get("price_vs_sma_200_pct")
    if sma200 and vs_sma200 is not None:
        trend_hint = "above" if vs_sma200 > 0 else "below"
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="price",
            statement=f"{name} is {abs(vs_sma200):.1f}% {trend_hint} its 200-day SMA (₹{sma200:,.1f})",
            data={"sma_200": sma200, "price_vs_sma_200_pct": vs_sma200},
            supports=["price_analysis"],
            source_path=f"{target_dir}/price_history.json",
            feature_group_id=price_feats["feature_group_id"],
            confidence=0.92,
        ))

    # ── 2. Fundamental cards ───────────────────────────────────────────────────
    if ff.get("roe_pct") is not None:
        roe = ff["roe_pct"]
        roce = ff.get("roce_pct")
        stmt = f"{name} ROE: {roe:.1f}%"
        if roce:
            stmt += f", ROCE: {roce:.1f}%"
        roe_5y = ff.get("roe_5y_pct")
        if roe_5y:
            stmt += f" (5-year avg: {roe_5y:.0f}%)"
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="fundamentals",
            statement=stmt,
            data={"roe_pct": roe, "roce_pct": roce, "roe_5y_pct": roe_5y},
            supports=["fundamental_analysis", "quality_analysis"],
            source_path=f"{target_dir}/screener_in.json",
            feature_group_id=fund_feats["feature_group_id"],
            confidence=0.9,
        ))

    sc5 = ff.get("sales_cagr_5y_pct")
    pc5 = ff.get("profit_cagr_5y_pct")
    if sc5 is not None or pc5 is not None:
        data = {k: ff.get(k) for k in ("sales_cagr_5y_pct", "profit_cagr_5y_pct", "sales_cagr_3y_pct", "profit_cagr_3y_pct") if ff.get(k) is not None}
        parts = []
        if sc5: parts.append(f"sales CAGR 5Y: {sc5:.0f}%")
        if pc5: parts.append(f"profit CAGR 5Y: {pc5:.0f}%")
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="fundamentals",
            statement=f"{name} growth profile: {', '.join(parts)}",
            data=data,
            supports=["fundamental_analysis", "growth_analysis"],
            source_path=f"{target_dir}/screener_in.json",
            feature_group_id=fund_feats["feature_group_id"],
            confidence=0.88,
        ))

    de = ff.get("debt_to_equity")
    opm = ff.get("opm_latest_pct")
    opm_trend = ff.get("opm_trend")
    if de is not None or opm is not None:
        data = {k: ff.get(k) for k in ("debt_to_equity", "opm_latest_pct", "opm_trend", "net_profit_yoy_growth_pct") if ff.get(k) is not None}
        parts = []
        if de is not None: parts.append(f"D/E: {de:.2f}")
        if opm is not None: parts.append(f"OPM: {opm:.1f}% ({opm_trend or 'N/A'})")
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="fundamentals",
            statement=f"{name} balance sheet/margin: {', '.join(parts)}",
            data=data,
            supports=["fundamental_analysis", "risk_analysis"],
            source_path=f"{target_dir}/screener_in.json",
            feature_group_id=fund_feats["feature_group_id"],
            confidence=0.88,
        ))

    prom_chg = ff.get("promoter_holding_change_4q_pct")
    prom_lat  = ff.get("promoter_holding_latest_pct")
    if prom_lat is not None:
        trend_lbl = "increased" if (prom_chg or 0) > 0 else ("decreased" if (prom_chg or 0) < 0 else "unchanged")
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="fundamentals",
            statement=f"{name} promoter holding: {prom_lat:.1f}% ({trend_lbl} by {abs(prom_chg or 0):.1f}% over 4Q)",
            data={"promoter_holding_latest_pct": prom_lat, "promoter_holding_change_4q_pct": prom_chg},
            supports=["management_confidence", "fundamental_analysis"],
            weakens=["risk_analysis"] if (prom_chg or 0) < -1 else [],
            source_path=f"{target_dir}/screener_in.json",
            feature_group_id=fund_feats["feature_group_id"],
            confidence=0.85,
        ))

    # ── 3. Valuation cards ─────────────────────────────────────────────────────
    pe = vf.get("pe_ratio")
    pb = vf.get("pb_ratio")
    ey = vf.get("earnings_yield_pct")
    if pe is not None or pb is not None:
        data = {k: vf.get(k) for k in ("pe_ratio", "pb_ratio", "earnings_yield_pct", "dividend_yield_pct",
                                         "pe_vs_peer_median_pct", "pb_vs_peer_median_pct") if vf.get(k) is not None}
        parts = []
        if pe: parts.append(f"PE: {pe:.1f}x")
        if pb: parts.append(f"PB: {pb:.1f}x")
        if ey: parts.append(f"earnings yield: {ey:.1f}%")
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="numeric_feature", evidence_category="valuation",
            statement=f"{name} valuation: {', '.join(parts)}",
            data=data,
            supports=["valuation_analysis"],
            source_path=f"{target_dir}/screener_in.json",
            feature_group_id=val_feats["feature_group_id"],
            confidence=0.9,
        ))

    upside = vf.get("analyst_target_upside_pct")
    if upside is not None:
        direction = "upside" if upside > 0 else "downside"
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="analyst_estimate", evidence_category="valuation",
            statement=f"Analyst consensus implies {abs(upside):.1f}% {direction} for {name} (mean target: ₹{vf.get('analyst_target_price_mean', 'N/A')})",
            data={"analyst_target_upside_pct": upside,
                  "analyst_target_price_mean": vf.get("analyst_target_price_mean"),
                  "analyst_target_price_high": vf.get("analyst_target_price_high"),
                  "analyst_target_price_low":  vf.get("analyst_target_price_low")},
            supports=["valuation_analysis"] if upside > 5 else [],
            weakens=["valuation_analysis"] if upside < -5 else [],
            source_path=f"{target_dir}/analyst_estimates.json",
            feature_group_id=val_feats["feature_group_id"],
            confidence=0.75,
        ))

    # ── 4. Peer comparison cards ───────────────────────────────────────────────
    peer_count = peer_f.get("peer_count", 0)
    quality_hint = peer_f.get("quality_vs_peer_hint")
    val_hint = peer_f.get("valuation_vs_peer_hint")
    roe_pctile = peer_f.get("roe_percentile")
    if peer_count and quality_hint:
        data = {k: peer_f.get(k) for k in ("peer_count", "roe_percentile", "revenue_growth_percentile",
                                              "profit_margins_percentile", "quality_vs_peer_hint",
                                              "valuation_vs_peer_hint", "pe_vs_peer_median_pct") if peer_f.get(k) is not None}
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="peer_comparison", evidence_category="valuation",
            statement=f"{name} vs {peer_count} peers: quality {quality_hint}, valuation {val_hint}. ROE in {roe_pctile}th percentile." if roe_pctile else f"{name} vs {peer_count} peers: quality {quality_hint}, valuation {val_hint}.",
            data=data,
            supports=["valuation_analysis", "quality_analysis"],
            source_path=f"{target_dir}/peer_comparison.json",
            feature_group_id=peer_feats["feature_group_id"],
            confidence=0.82,
        ))

    # ── 5. Analyst recommendation cards ───────────────────────────────────────
    buy_ratio = af.get("buy_rating_ratio")
    coverage  = af.get("coverage_count")
    if buy_ratio is not None and coverage:
        buy_pct = round(buy_ratio * 100)
        sell_ratio = af.get("sell_rating_ratio", 0) or 0
        sell_pct   = round(sell_ratio * 100)
        rev_dir    = af.get("eps_revision_direction", "unknown")
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="analyst_estimate", evidence_category="analyst_consensus",
            statement=f"{coverage} analysts cover {name}: {buy_pct}% Buy, {sell_pct}% Sell. EPS revisions: {rev_dir}",
            data={"buy_rating_ratio": buy_ratio, "hold_rating_ratio": af.get("hold_rating_ratio"),
                  "sell_rating_ratio": sell_ratio, "coverage_count": coverage,
                  "eps_revision_direction": rev_dir, "revision_balance": af.get("revision_balance")},
            supports=["valuation_analysis"] if buy_ratio > 0.6 else [],
            weakens=["valuation_analysis"] if sell_ratio > 0.3 else [],
            source_path=f"{target_dir}/analyst_estimates.json",
            feature_group_id=analyst_feats["feature_group_id"],
            confidence=0.78,
        ))

    eps_chg = af.get("eps_revision_pct_30d_nq")
    if eps_chg is not None and abs(eps_chg) > 0.5:
        direction = "upward" if eps_chg > 0 else "downward"
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="analyst_estimate", evidence_category="earnings_revision",
            statement=f"{name} near-term EPS estimates revised {direction} by {abs(eps_chg):.1f}% over last 30 days",
            data={"eps_revision_pct_30d_nq": eps_chg, "upgrades_last_30d": af.get("upgrades_last_30d"),
                  "downgrades_last_30d": af.get("downgrades_last_30d")},
            supports=["fundamental_analysis"] if eps_chg > 0 else [],
            weakens=["fundamental_analysis"] if eps_chg < 0 else [],
            source_path=f"{target_dir}/analyst_estimates.json",
            feature_group_id=analyst_feats["feature_group_id"],
            confidence=0.72,
        ))

    # ── 6. Exchange filings cards ──────────────────────────────────────────────
    ef = scope["files"].get("exchange_filings") or {}
    announcements = ef.get("announcements", [])
    if announcements:
        # Take up to 5 most recent
        recent = announcements[:5]
        for ann in recent:
            subj    = ann.get("subject") or ann.get("description") or ann.get("body", "")[:80]
            cat     = ann.get("type") or ann.get("category", "")
            ann_date = ann.get("exchDisseminationTime") or ann.get("date", "")
            if not subj:
                continue
            cards.append(_card(
                _next_id(date_str), tid, name, ticker,
                evidence_type="filing_fact", evidence_category="exchange_filing",
                statement=f"NSE filing ({cat}): {subj[:120]}",
                data={"subject": subj, "category": cat, "date": ann_date},
                supports=["event_analysis"],
                source_path=f"{target_dir}/exchange_filings.json",
                feature_group_id=None,
                confidence=0.9,
            ))
    else:
        # Gap card
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="missing_data_gap", evidence_category="exchange_filing",
            statement=f"No NSE exchange filings collected for {name}",
            data={"module": "exchange_filings", "count": 0},
            supports=[],
            weakens=["event_analysis", "risk_analysis"],
            source_path=None,
            feature_group_id=None,
            confidence=0.0,
        ))

    # ── 7. Missing data gap cards from L7 ─────────────────────────────────────
    for miss in scope.get("missing_data", []):
        module = miss.get("module", "unknown")
        reason = miss.get("reason") or miss.get("error", "")
        if module == "exchange_filings":
            continue  # already handled above
        cards.append(_card(
            _next_id(date_str), tid, name, ticker,
            evidence_type="missing_data_gap", evidence_category=module,
            statement=f"Missing data: {module} for {name} — {reason[:120]}",
            data={"module": module, "reason": reason},
            supports=[],
            weakens=[],
            source_path=None,
            feature_group_id=None,
            confidence=0.0,
        ))

    return cards


def _card(
    evid_id: str,
    target_id: str,
    target_name: str,
    ticker: str,
    evidence_type: str,
    evidence_category: str,
    statement: str,
    data: dict,
    supports: list[str],
    source_path: str | None,
    feature_group_id: str | None,
    confidence: float,
    weakens: list[str] | None = None,
) -> dict:
    now = datetime.now(_IST).isoformat()
    card = {
        "evidence_id":        evid_id,
        "target_id":          target_id,
        "target_name":        target_name,
        "ticker":             ticker,
        "evidence_type":      evidence_type,
        "evidence_category":  evidence_category,
        "statement":          statement,
        "data":               data,
        "supports":           supports,
        "weakens":            weakens or [],
        "source_refs": [{"source_path": source_path}] if source_path else [],
        "derived_from": {"feature_group_id": feature_group_id} if feature_group_id else {},
        "confidence":         confidence,
        "created_at":         now,
    }
    return card
