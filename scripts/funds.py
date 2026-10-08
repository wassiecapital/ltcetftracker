"""Fund registry for the US spot Litecoin ETF complex.

Multi-issuer by design. Today exactly one fund trades (Canary LTCC); the rest are
registered here with status != "live" so the dashboard shows the pipeline, and so
that adding a fund on its listing day is a one-line change plus an adapter.

Verified 5 Oct 2026 — see README for sources.
"""

FUNDS = [
    {
        "ticker": "LTCC",
        "issuer": "Canary Capital",
        "name": "Canary Litecoin ETF",
        "exchange": "Nasdaq",
        "status": "live",
        "adapter": "canary_table",
        "fee": 0.0095,          # unified sponsor fee, no waiver disclosed
        "stakes": False,        # Litecoin is proof-of-work; prospectus forbids staking
        "seed_date": "2025-10-27",
        "first_trade": "2025-10-28",
        "cik": "2039461",
        "cusip": "137221107",
        "basket_shares": 10000,
        "source": "https://canaryetfs.com/ltcc/",
    },
    {
        "ticker": "LTCN",
        "issuer": "Grayscale",
        "name": "Grayscale Litecoin Trust (ETF conversion pending)",
        "exchange": "NYSE Arca (proposed)",
        "status": "pending_19b4",
        "adapter": None,
        "fee": 0.025,          # current trust fee; post-conversion fee left blank in S-3/A
        "stakes": False,
        "seed_date": None,
        "first_trade": None,
        "cik": "1732406",
        "note": (
            "Still a Reg-D trust quoted on OTCQX. NYSE Arca filed the 19b-4 on "
            "24 Jan 2025; as of the 11 Sep 2026 S-3/A it was not approved and the "
            "trust will not seek effectiveness until it is. Shares outstanding have "
            "been pinned at 24,252,100 since Dec 2025, so flow is structurally zero "
            "until a creation/redemption programme exists."
        ),
    },
    {
        "ticker": "KCOI",
        "issuer": "KraneShares",
        "name": "KraneShares Crypto Trust (basket, LTC is a constituent)",
        "exchange": "n/a",
        "status": "not_single_asset",
        "adapter": None,
        "fee": 0.0068,
        "stakes": False,
        "note": "Multi-asset basket. Tracked here only so it is not miscounted as a spot LTC fund.",
    },
]

# Withdrawn / dead, kept for the record so nobody re-adds them:
#   CoinShares Litecoin ETF — Form RW filed 28 Nov 2025 (CIK 2048623).
#   No US spot LTC filing exists from Bitwise, 21Shares, Franklin, WisdomTree or VanEck.

LIVE = [f for f in FUNDS if f["status"] == "live"]

# EDGAR CIKs to watch for an 8-A12B (the filing that means "about to list").
WATCH_CIKS = {f["cik"]: f["ticker"] for f in FUNDS if f.get("cik") and f["status"] != "live"}
