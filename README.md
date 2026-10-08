# ltcetftracker

Daily net creation flows for US-listed **spot Litecoin ETFs**, rebuilt by GitHub
Actions and served as a static page.

Live page: `https://<you>.github.io/ltcetftracker/`

---

## Why this exists

No free aggregator publishes Litecoin ETF flows. Checked 5 Oct 2026:

| Source | LTC flows? |
|---|---|
| Farside Investors | No — covers BTC, ETH, SOL, HYP, ZEC only |
| CoinGlass ETF API | No — BTC, ETH, SOL, XRP, HYPE only |
| SoSoValue | A `us-ltc-spot` page exists but is not readable without a session |
| stockanalysis / Nasdaq / Barchart | Price only, and their AUM figures run stale |
| The Block | Headline AUM and 24h flow, no downloadable series |

So this derives flow the same way the aggregators do, from the issuer's own
daily disclosure:

```
flow_t = (shares_outstanding_t − shares_outstanding_t−1) × NAV_t
NAV_t  = net_assets_t / shares_outstanding_t
```

NAV is recomputed rather than read off the printed NAV column, which is rounded
to two decimals (and occasionally zero).

## The complex, as of 5 Oct 2026

**Trading — one fund.**

| Fund | Ticker | Venue | Listed | Fee | Stakes |
|---|---|---|---|---|---|
| Canary Litecoin ETF | LTCC | Nasdaq | 28 Oct 2025 (seeded 27 Oct) | 0.95% | No — Litecoin is proof-of-work, and the prospectus forbids it |

**Not trading.**

- **Grayscale Litecoin Trust (LTCN)** — still a Reg-D trust quoted on OTCQX.
  NYSE Arca filed the 19b-4 on 24 Jan 2025; the 11 Sep 2026 S-3/A states it is
  still unapproved and that the trust will not seek effectiveness until it is.
  Shares outstanding have been pinned at 24,252,100 since Dec 2025, so its flow
  is structurally zero — there is no creation/redemption programme to measure.
- **CoinShares Litecoin ETF** — withdrawn, Form RW filed 28 Nov 2025.
- **Bitwise, 21Shares, Franklin, WisdomTree, VanEck** — no US spot LTC filing
  exists (EDGAR full-text search, Jun 2024 – Oct 2026).
- **KraneShares KCOI, Grayscale GDLC, Bitwise BITW, Hashdex NCIQ, Franklin EZPZ,
  T. Rowe TKNZ** — baskets that hold LTC as a constituent, not spot LTC funds.
- **Lite Strategy Inc. (LITS)** — an LTC-treasury operating company, not an ETP.

The tracker is built multi-issuer even though one fund trades: `scripts/funds.py`
is the registry, the page renders every fund in it, and every run checks EDGAR
for a Form 8-A12B on the pending ones — the filing that means a listing is days
away.

## Layout

```
index.html                 the dashboard
assets/styles.css          light + dark theme tokens
assets/app.js              renderer: tiles, charts, tables, CSV (no dependencies)
scripts/funds.py           fund registry — add a fund here
scripts/update.py          scraper + flow builder, writes data/ltc_flows.json
data/ltc_flows.json        the series (committed, so the page is static)
.github/workflows/update.yml   twice-daily rebuild + commit
```

## Running it locally

```bash
pip install -r requirements.txt
python scripts/update.py
python -m http.server 8000     # then open http://localhost:8000
```

The script rebuilds the **entire** history on every run, because Canary ships
the full daily table for all six of its funds in one page. That makes it
idempotent — a missed day repairs itself on the next run, and the committed JSON
is always a complete rebuild rather than an accumulation.

## Deploying

1. Create a repo named `ltcetftracker`, push these files to `main`.
2. Settings → Pages → Source: **Deploy from a branch**, branch `main`, folder `/ (root)`.
3. Settings → Actions → General → Workflow permissions: **Read and write**
   (the workflow commits the refreshed data file).
4. Actions → *update flows* → **Run workflow** once to confirm, then it runs on
   schedule: 23:30 UTC Mon–Fri and 11:30 UTC Tue–Sat.

## Gotchas worth knowing before you touch the scraper

- **The user agent is load-bearing.** `canaryetfs.com` serves a 4 KB stub to
  thin user agents and the real 1.4 MB page to a browser-like one. `update.py`
  raises if the response is under 100 KB rather than silently writing nothing.
- **`pandas.read_html` does not work on this page.** The markup is malformed —
  a stray `</div>` closes before the data rows — so lxml drops every row and
  returns only the trailing-returns table. The script walks the DOM with
  BeautifulSoup against `data-wpdatatable_id="4"` instead.
- **There is no JSON or CSV behind the table.** The plugin runs client-side
  (`serverSide: false`), so there is no `admin-ajax` feed to hit. The HTML is
  the endpoint.
- **One page covers six funds.** Table 4 carries LTCC, XRPC, HBR, SOLC, SUIS and
  TRXS. Pointing another tracker at the same URL costs nothing.
- **`data.sec.gov` 403s descriptive bot user agents** and accepts browser-like
  ones. Override with the `EDGAR_UA` env var if that flips.

## Reading the output

- **Flow excludes price.** Cumulative flow sits well above net assets because
  LTC fell and the 0.95% fee accrues daily. That spread is the mark-to-market,
  not a data error.
- **Zero is the normal state.** 34 of 235 sessions have moved the share count.
  Creations are struck in 10,000-share baskets by an authorised participant, so
  a quiet day means no basket cleared, not that demand vanished. Cadence — how
  often the tape prints — carries more signal than any single-day record.
- **One fund is not an asset class.** A thin tape here is one issuer's book.

## Adding a fund when one lists

1. Flip its entry in `scripts/funds.py` to `"status": "live"` and give it an
   `adapter`.
2. If it is another Canary fund, the `canary_table` adapter already works — just
   set the ticker.
3. Otherwise add a fetch function in `update.py` returning the same record shape
   (`date, shares, net_assets, nav, market_price, premium_discount`), and the
   page picks it up: tiles, charts and the per-fund tooltip breakdown are all
   driven off `live_tickers`.

Sources: [Canary LTCC fund data](https://canaryetfs.com/ltcc/) ·
[LTCC prospectus 424B3](https://www.sec.gov/Archives/edgar/data/2039461/000199937125016206/canary-424b3_102725.htm) ·
[Grayscale LTC S-3/A, 11 Sep 2026](https://www.sec.gov/Archives/edgar/data/1732406/000119312526389256/ltc_s-3_amendment_1.htm) ·
[SEC EDGAR submissions API](https://data.sec.gov/submissions/CIK0001732406.json)

Not investment advice. Verify against the issuer before citing.
