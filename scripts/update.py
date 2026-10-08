#!/usr/bin/env python3
"""Rebuild data/ltc_flows.json — daily net creation flows for US spot Litecoin ETFs.

Method
------
No aggregator publishes LTC ETF flows (Farside covers BTC/ETH/SOL/HYP/ZEC only;
CoinGlass and SoSoValue have no LTC series). So flow is derived from the primary
source the way the aggregators derive theirs:

    flow_t = (shares_outstanding_t - shares_outstanding_t-1) * NAV_t

NAV is recomputed as net_assets / shares_outstanding rather than read off the
printed NAV column, which is rounded to 2dp and sometimes to 0dp.

Canary publishes the full daily history for all six of its funds in one
server-rendered HTML table, so this script rebuilds the whole series every run
and is therefore idempotent — a missed day repairs itself on the next run.

Flow is a *gross-of-everything* measure: it excludes price moves (good) but a
zero-flow day genuinely means no creation unit was struck, not that the fund was
idle. Creations move in 10,000-share baskets, so the series is lumpy by
construction.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from funds import FUNDS, LIVE, WATCH_CIKS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ltc_flows.json"

# Canary's WAF serves a 4KB stub to thin user agents. A full browser UA gets the
# real 1.4MB page. Do not remove this header.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

EDGAR_UA = os.environ.get("EDGAR_UA", "Mozilla/5.0")

CANARY_URL = "https://canaryetfs.com/ltcc/"
DAILY_TABLE_ID = "4"      # daily NAV/shares history, all Canary funds
HOLDINGS_TABLE_ID = "45"  # latest-day holdings, all Canary funds


def num(x):
    if x is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(x))
    if s in ("", "-", "."):
        return None
    return float(s)


def fetch_canary_tables() -> dict[str, "list[dict]"]:
    r = requests.get(CANARY_URL, headers=HEADERS, timeout=120)
    r.raise_for_status()
    if len(r.text) < 100_000:
        raise RuntimeError(
            f"canaryetfs.com returned {len(r.text)} bytes — WAF stub, not the data page"
        )
    soup = BeautifulSoup(r.text, "html.parser")
    out = {}
    for tid in (DAILY_TABLE_ID, HOLDINGS_TABLE_ID):
        t = soup.find("table", {"data-wpdatatable_id": tid})
        if t is None:
            raise RuntimeError(f"table data-wpdatatable_id={tid} not found")
        cols = [th.get_text(strip=True) for th in t.find("thead").find_all("th")]
        rows = []
        for tr in t.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells and len(cells) == len(cols):
                rows.append(dict(zip(cols, cells)))
        out[tid] = rows
    return out


def build_series(rows: "list[dict]", ticker: str) -> "list[dict]":
    recs = []
    for r in rows:
        if r.get("Fund Ticker") != ticker:
            continue
        na, so = num(r.get("Net Assets")), num(r.get("Shares Outstanding"))
        if not na or not so:
            continue
        recs.append({
            "date": dt.datetime.strptime(r["Rate Date"], "%m/%d/%Y").date().isoformat(),
            "shares": so,
            "net_assets": round(na, 2),
            "nav": round(na / so, 6),
            "market_price": num(r.get("Market Price")),
            "premium_discount": num(r.get("Premium/Discount")),
            "spread_30d": num(r.get("Median 30 Day Spread Percentage")),
        })
    recs.sort(key=lambda x: x["date"])

    prev = None
    for i, rec in enumerate(recs):
        if i == 0:
            # Seed day: the whole fund arrived, so treat net assets as the flow.
            rec["flow"] = round(rec["net_assets"], 2)
            rec["seed"] = True
        else:
            rec["flow"] = round((rec["shares"] - prev["shares"]) * rec["nav"], 2)
        prev = rec
    return recs


def check_edgar_listings() -> "list[dict]":
    """Watch pending funds for a Form 8-A12B — the filing that precedes listing."""
    hits = []
    for cik, ticker in WATCH_CIKS.items():
        url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
        try:
            # data.sec.gov 403s descriptive bot UAs and accepts browser-like ones.
            # Override with the EDGAR_UA env var if SEC's policy changes.
            j = requests.get(url, headers={"User-Agent": EDGAR_UA}, timeout=60).json()
        except Exception as e:  # never fail the whole run on the watcher
            hits.append({"ticker": ticker, "error": str(e)[:200]})
            continue
        recent = j.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        exch = j.get("exchanges", [])
        listed = any(f in ("8-A12B", "8-A12G") for f in forms)
        hits.append({
            "ticker": ticker,
            "cik": cik,
            "exchanges": exch,
            "has_8a": listed,
            "latest_form": forms[0] if forms else None,
            "latest_form_date": dates[0] if dates else None,
            "action": ("LISTING IMMINENT — add an adapter" if listed else "no 8-A yet"),
        })
    return hits


def main() -> int:
    tables = fetch_canary_tables()
    daily, holdings = tables[DAILY_TABLE_ID], tables[HOLDINGS_TABLE_ID]

    per_fund, dates = {}, set()
    for f in LIVE:
        if f["adapter"] != "canary_table":
            continue
        s = build_series(daily, f["ticker"])
        if not s:
            raise RuntimeError(f"no rows parsed for {f['ticker']}")
        per_fund[f["ticker"]] = s
        dates.update(r["date"] for r in s)

    # Coin count held, for the cross-check panel.
    coins = {}
    for r in holdings:
        t = r.get("Ticker") or r.get("Fund Ticker")
        if t in per_fund or (r.get("Name") or "").upper().startswith("LITECOIN"):
            q = num(r.get("Quantity"))
            if q:
                # Canary prints the holdings date as m/d/Y; normalise to ISO so the
                # page can format it. Note it is the NEXT business day relative to
                # the daily table, so never join the two on date.
                raw = (r.get("Date") or "").strip()
                try:
                    iso = dt.datetime.strptime(raw, "%m/%d/%Y").date().isoformat()
                except ValueError:
                    iso = raw or None
                coins[r.get("Ticker", "LTCC")] = {"ltc": q, "as_of": iso}

    series = []
    for d in sorted(dates):
        row = {"date": d, "by_fund": {}, "flow": 0.0, "net_assets": 0.0}
        for tk, s in per_fund.items():
            m = next((x for x in s if x["date"] == d), None)
            if not m:
                continue
            row["by_fund"][tk] = m
            row["flow"] += m["flow"]
            row["net_assets"] += m["net_assets"]
        row["flow"] = round(row["flow"], 2)
        row["net_assets"] = round(row["net_assets"], 2)
        series.append(row)

    cum = 0.0
    for row in series:
        cum += row["flow"]
        row["cum_flow"] = round(cum, 2)

    payload = {
        "asset": "LTC",
        "asset_name": "Litecoin",
        "updated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "method": ("flow = change in shares outstanding x NAV, per fund, per trading day; "
                   "NAV recomputed as net assets / shares outstanding"),
        "funds": FUNDS,
        "live_tickers": sorted(per_fund),
        "coins_held": coins,
        "coins_total": ({"amount": round(sum(c["ltc"] for c in coins.values()), 4),
                         "unit": "LTC",
                         "as_of": next(iter(coins.values()))["as_of"]} if coins else None),
        "series": series,
        "listing_watch": check_edgar_listings(),
        "caveats": [
            "Flow excludes price movement. Net assets can fall on a zero-flow day.",
            "Creations are struck in 10,000-share baskets, so single-day gaps are "
            "mechanical, not a demand signal.",
            "Seed day is reported as a flow equal to initial net assets.",
            "Source is the issuer's own daily table — the same upstream the "
            "aggregators quote.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1))
    last = series[-1]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(series)} sessions through {last['date']}, "
          f"last flow ${last['flow']:,.0f}, cumulative ${last['cum_flow']:,.0f}")
    for h in payload["listing_watch"]:
        print("  watch:", h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
