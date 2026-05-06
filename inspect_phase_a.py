"""
inspect_phase_a.py — Phase A output health check

Reads every file in output/phaseA/ and prints a complete picture:
  - Text sources (used by Phase B LLM signal extraction)
  - Market data sources (used by Phase B market regime)
  - Issues (empty files, missing content, etc.)

Usage:
  python inspect_phase_a.py
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent))
from config.paths import PHASE_A_DIR

_IST = timezone(timedelta(hours=5, minutes=30))

W = 62  # line width


def _bar(label: str, char: str = "─") -> None:
    print(f"\n{char * 2} {label} {char * max(0, W - len(label) - 4)}")


def _ok(msg: str)   -> None: print(f"  ✓  {msg}")
def _warn(msg: str) -> None: print(f"  ⚠  {msg}")
def _miss(msg: str) -> None: print(f"  ✗  {msg}")


def _load(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text())
    except Exception as e:
        return {"_error": str(e)}


def _latest(dir_path: Path, pattern: str = "*.json") -> Path | None:
    files = sorted(dir_path.glob(pattern))
    return files[-1] if files else None


# ── Text source checkers ──────────────────────────────────────────────────────

def check_article_source(name: str, dir_path: Path,
                          body_key: str = "body",
                          fallback_key: str = "description") -> dict:
    """Moneycontrol / Economic Times style: files with articles[] list."""
    files   = sorted(dir_path.glob("*.json"))
    total   = 0
    with_content = 0
    issues  = []
    rows    = []

    for f in files:
        data = _load(f)
        if "_error" in data:
            issues.append(f"{f.name}: parse error")
            continue
        arts = data.get("articles", [])
        count = len(arts)
        has_body = sum(
            1 for a in arts
            if (a.get(body_key) or a.get(fallback_key) or "").strip()
        )
        total        += count
        with_content += has_body
        rows.append((f.stem, count, has_body))
        if count > 0 and has_body == 0:
            issues.append(f"{f.name}: {count} articles but NO body content")

    return {"files": len(files), "total": total,
            "with_content": with_content, "rows": rows, "issues": issues}


def check_rss(dir_path: Path) -> dict:
    """RSS: one file per feed, articles[] with title + summary."""
    files   = sorted(dir_path.glob("*.json"))
    total   = 0
    with_content = 0
    rows    = []

    for f in files:
        data = _load(f)
        if "_error" in data:
            continue
        arts   = data.get("articles", [])
        count  = len(arts)
        has_sm = sum(
            1 for a in arts
            if (a.get("summary") or a.get("description") or "").strip()
        )
        feed = data.get("feed_name", f.stem)
        total        += count
        with_content += has_sm
        rows.append((feed, count, has_sm))

    return {"files": len(files), "total": total,
            "with_content": with_content, "rows": rows, "issues": []}


def check_news_api(name: str, dir_path: Path) -> dict:
    """Newsdata.io / Mediastack: articles[] with title + description."""
    files  = sorted(dir_path.glob("*.json"))
    total  = 0
    with_content = 0
    rows   = []

    for f in files:
        data = _load(f)
        if "_error" in data:
            continue
        arts  = data.get("articles", [])
        count = len(arts)
        has_d = sum(
            1 for a in arts
            if (a.get("description") or a.get("content") or "").strip()
        )
        total        += count
        with_content += has_d
        rows.append((f.stem, count, has_d))

    return {"files": len(files), "total": total,
            "with_content": with_content, "rows": rows, "issues": []}


def check_youtube(dir_path: Path) -> dict:
    """YouTube: one JSON per video with transcript field."""
    files  = sorted(dir_path.glob("*.json"))
    total  = len(files)
    with_tr  = 0
    empty_tr = 0
    avg_len  = 0
    rows   = []

    for f in files:
        data = _load(f)
        if "_error" in data:
            continue
        tr  = data.get("transcript", "").strip()
        vid = data.get("video_id", f.stem)
        title = data.get("title", "")[:50]
        if tr:
            with_tr += 1
            avg_len += len(tr)
            rows.append((vid, title, len(tr), "✓"))
        else:
            empty_tr += 1
            rows.append((vid, title, 0, "no-cc"))

    avg = avg_len // with_tr if with_tr else 0
    issues = [f"{empty_tr} video(s) have no transcript"] if empty_tr else []
    return {"files": total, "total": total, "with_content": with_tr,
            "avg_chars": avg, "rows": rows, "issues": issues}


def check_gmail(dir_path: Path) -> dict:
    """Gmail newsletters: newsletters[] inside each file."""
    files  = sorted(dir_path.glob("*.json"))
    total  = 0
    with_body = 0
    rows   = []

    for f in files:
        data = _load(f)
        if "_error" in data:
            continue
        nls   = data.get("newsletters", data.get("emails", []))
        count = len(nls)
        has_b = sum(1 for n in nls if (n.get("body") or n.get("snippet") or "").strip())
        total    += count
        with_body += has_b
        rows.append((f.stem, count, has_b))

    return {"files": len(files), "total": total,
            "with_content": with_body, "rows": rows, "issues": []}


# ── Market data checkers ──────────────────────────────────────────────────────

def check_macro(dir_path: Path) -> None:
    india = _load(dir_path / "india_macro_2026-05-05.json") if \
            (dir_path / "india_macro_2026-05-05.json").exists() else \
            _load(_latest(dir_path, "india_macro_*.json"))
    us    = _load(dir_path / "us_macro_2026-05-05.json") if \
            (dir_path / "us_macro_2026-05-05.json").exists() else \
            _load(_latest(dir_path, "us_macro_*.json"))

    if "_error" not in india and india:
        rd = india.get("market_rates", {})
        br = india.get("market_breadth", {})
        vix   = rd.get("vix_india", {}).get("value", "?")
        nifty = rd.get("nifty_50",  {}).get("value", "?")
        inr   = rd.get("usd_inr",   {}).get("value", "?")
        adv   = br.get("advances", "?")
        dec   = br.get("declines", "?")
        _ok(f"India macro  │ Nifty={nifty}  VIX={vix}  USD/INR={inr}  A/D={adv}/{dec}")
    else:
        _miss("India macro  │ file missing or empty")

    if "_error" not in us and us:
        y10  = us.get("us_10y_treasury", {}).get("latest_value", "?")
        fed  = us.get("fed_funds_rate",  {}).get("latest_value", "?")
        yc   = us.get("yield_curve_10y_2y", {}).get("latest_value", "?")
        _ok(f"US macro     │ 10Y={y10}%  Fed={fed}%  Yield curve={yc}")
    else:
        _miss("US macro     │ file missing or empty")


def check_fii(dir_path: Path) -> None:
    f = _latest(dir_path)
    if not f:
        _miss("FII/DII │ no file found")
        return
    data = _load(f)
    if "_error" in data:
        _miss(f"FII/DII │ parse error")
        return
    fii = data.get("fii", {})
    dii = data.get("dii", {})
    fn  = fii.get("net", "?")
    dn  = dii.get("net", "?")
    _ok(f"FII/DII  │ FII net=₹{fn}cr  DII net=₹{dn}cr  ({f.name})")


def check_fno(dir_path: Path) -> None:
    f = _latest(dir_path, "NIFTY_fno_*.json")
    if not f:
        _miss("FNO data │ no NIFTY file found (normal outside market hours)")
        return
    data = _load(f)
    if "_error" in data:
        _miss(f"FNO data │ parse error")
        return
    pcr      = data.get("pcr", "?")
    mp       = data.get("max_pain", "?")
    atm_iv   = data.get("atm_iv", "?")
    underly  = data.get("underlying_value", "?")
    _ok(f"FNO NIFTY │ spot={underly}  PCR={pcr}  max_pain={mp}  ATM_IV={atm_iv}%")


def check_bulk(dir_path: Path) -> None:
    f = _latest(dir_path)
    if not f:
        _miss("Bulk deals │ no file found")
        return
    data = _load(f)
    if "_error" in data:
        _miss("Bulk deals │ parse error")
        return
    bulk  = len(data.get("bulk_deals",  []))
    block = len(data.get("block_deals", []))
    if bulk + block:
        _ok(f"Bulk deals │ {bulk} bulk  +  {block} block deals  ({f.name})")
    else:
        _warn(f"Bulk deals │ file exists but 0 deals  ({f.name})")


# ── Print helpers for text sources ───────────────────────────────────────────

def _print_text_source(name: str, result: dict, row_label: str = "file") -> None:
    files = result["files"]
    total = result["total"]
    wc    = result["with_content"]
    issues = result["issues"]

    if files == 0:
        _miss(f"{name:18s} │ no files found")
        return

    status = "✓" if (total > 0 and wc > 0) else ("⚠" if total > 0 else "✗")
    extra  = f"  {wc}/{total} with content" if total > 0 else ""
    print(f"  {status}  {name:18s} │ {files} file(s) │ {total} items{extra}")

    for row in result.get("rows", []):
        label, count, has_c = row[0], row[1], row[2]
        flag = "" if has_c == count else f"  ← {has_c} with content"
        if count > 0:
            print(f"       {label[:40]:40s} {count:4d} items{flag}")

    for issue in issues:
        _warn(f"  {issue}")


# ── Main ──────────────────────────────────────────────────────────────────────

def inspect() -> None:
    now = datetime.now(_IST).strftime("%d %b %Y  %I:%M %p IST")
    print(f"\n{'═'*W}")
    print(f"  Phase A — Output Inspection")
    print(f"  {now}")
    print(f"{'═'*W}")

    all_text_results = {}

    # ── Text sources ──────────────────────────────────────────────────────────
    _bar("Text Sources  (Phase B signal extraction input)")

    mc = check_article_source("moneycontrol", PHASE_A_DIR / "moneycontrol")
    _print_text_source("moneycontrol", mc)
    all_text_results["moneycontrol"] = mc

    et = check_article_source("economic_times", PHASE_A_DIR / "economic_times")
    _print_text_source("economic_times", et)
    all_text_results["economic_times"] = et

    rss = check_rss(PHASE_A_DIR / "rss")
    _print_text_source("rss", rss)
    all_text_results["rss"] = rss

    nd = check_news_api("newsdata_io", PHASE_A_DIR / "newsdata_io")
    _print_text_source("newsdata_io", nd)
    all_text_results["newsdata_io"] = nd

    ms = check_news_api("mediastack", PHASE_A_DIR / "mediastack")
    _print_text_source("mediastack", ms)
    all_text_results["mediastack"] = ms

    yt = check_youtube(PHASE_A_DIR / "youtube")
    files = yt["files"]
    wc    = yt["with_content"]
    avg   = yt["avg_chars"]
    status = "✓" if wc > 0 else "✗"
    print(f"  {status}  {'youtube':18s} │ {files} file(s) │ {wc} with transcript  (avg {avg:,} chars)")
    for vid, title, chars, flag in yt["rows"][:5]:
        print(f"       {vid}  {title[:38]:38s}  {flag}  ({chars:,} chars)")
    if len(yt["rows"]) > 5:
        print(f"       … and {len(yt['rows'])-5} more")
    all_text_results["youtube"] = yt

    gm = check_gmail(PHASE_A_DIR / "gmail")
    _print_text_source("gmail", gm)
    all_text_results["gmail"] = gm

    # ── Market data ───────────────────────────────────────────────────────────
    _bar("Market Data  (Phase B regime input)")
    check_macro(PHASE_A_DIR / "macro_data")
    check_fii(PHASE_A_DIR / "fii_dii")
    check_fno(PHASE_A_DIR / "fno_data")
    check_bulk(PHASE_A_DIR / "bulk_deals")

    # ── Summary ───────────────────────────────────────────────────────────────
    _bar("Summary", "═")

    text_sources = ["moneycontrol", "economic_times", "rss",
                    "newsdata_io", "mediastack", "youtube", "gmail"]
    total_items   = sum(all_text_results[s]["total"]        for s in text_sources)
    total_content = sum(all_text_results[s]["with_content"] for s in text_sources)

    print(f"\n  Total text items for Phase B : {total_items}")
    print(f"  Items with usable content    : {total_content}")
    print(f"  Items missing content        : {total_items - total_content}")

    problems = []
    for src in text_sources:
        r = all_text_results[src]
        if r["files"] > 0 and r["total"] == 0:
            problems.append(f"{src} — files exist but 0 articles (scraper may have failed)")
        elif r["total"] > 0 and r["with_content"] == 0:
            problems.append(f"{src} — articles exist but all have empty content")
        elif r["issues"]:
            problems.extend([f"{src} — {i}" for i in r["issues"]])

    if problems:
        print(f"\n  Issues to fix:")
        for p in problems:
            print(f"    ⚠  {p}")
    else:
        print(f"\n  No issues found — Phase A looks healthy ✓")

    print(f"\n{'═'*W}\n")


if __name__ == "__main__":
    inspect()
