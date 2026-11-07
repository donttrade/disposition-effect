#!/usr/bin/env python3
"""markets_verified.py: what each large builder-listed market tracks, from the builder's OWN public documentation, cross-checked
against Hyperliquid's public metadata. Writes checks/selloff/zenodo/MARKETS-VERIFIED.csv.

Which markets: every builder-listed (HIP-3) market with at least 1% of the value force-closed on builder-listed markets on
5 Nov 2026 (read from 5-november-2026-per-market.csv), plus any market the study page names (SOXL, MU, SP500, XYZ100, AMD are
already in that set).

Status (the same words the study page shows):
  builders_docs     the builder's own documentation names the underlying (the security or index) and how the price is taken,
                    and its contract details (maximum leverage, margin mode) agree with Hyperliquid's public metadata;
  partly_sourced    the builder's documentation names the issuer or underlying but leaves something open (said in notes);
  no_source_found   no primary source found. The page then keeps the name "as listed".
A ticker name alone is never taken as evidence: e.g. the builder's PURRDAT market references Nasdaq: PURR.

The documents describe each market as of the check date (7 Nov 2026, UTC), not as of 5 Nov. The builder changelog
(https://docs.trade.xyz, "Changelog") lists no change to these markets' underlying between 6 Oct and 7 Nov 2026.
Hyperliquid metadata: POST https://api.hyperliquid.xyz/info {"type":"perpDexs"} and {"type":"meta","dex":"<dex>"}, read 2026-11-07.
No address of any kind is written (the builders' deployer addresses were compared, not copied).
Usage: python3 checks/selloff/markets_verified.py
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = HERE if os.path.exists(os.path.join(HERE, "5-november-2026-per-market.csv")) else os.path.join(HERE, "zenodo")  # the pack copy, or the repo
PER_MARKET = os.path.join(PACK, "5-november-2026-per-market.csv")
OUT = os.path.join(PACK, "MARKETS-VERIFIED.csv")
CHECKED = "2026-11-07"
NAMED_ON_PAGE = ("xyz:SOXL-PERP", "xyz:MU-PERP", "xyz:SP500-PERP", "xyz:XYZ100-PERP", "xyz:AMD-PERP")
MIN_SHARE = 0.01

XYZ_SPEC = "https://docs.trade.xyz/perpetuals/specifications-and-schedules/specification-index"
XYZ_US = "https://docs.trade.xyz/perpetuals/markets/stocks/us"
XYZ_KR = "https://docs.trade.xyz/perpetuals/markets/stocks/korea"
XYZ_IDX = "https://docs.trade.xyz/perpetuals/markets/equity-indices"
XYZ_ARCH = "trade[XYZ] docs, Relationship to Hyperliquid and Perpetuals Architecture: perpetuals are deployed under the xyz HIP-3 deployment; the deployer address they state equals Hyperliquid's perpDexs entry for xyz"
ENT_EQ = "https://docs.entropy.io/asset-directory/equity-assets"
HL = "Hyperliquid info API (perpDexs; meta for the dex)"
US_PRICE = ("Builder's relayer takes the stock's own price 24/5 (pre-market, regular, post-market, and overnight via Blue Ocean ATS); "
            "outside those hours an internal price from the market's own order book")
KR_PRICE = ("Korea Exchange price in won divided by the USD/KRW rate during Korean sessions; an internal price from the market's own "
            "order book outside them")
IDX_PRICE = ("Spot index value in the US cash session; outside it, the dated index futures price discounted to spot; an internal "
             "price when neither is available")


def stock(market, what, spec_quote, lev, margin, src=XYZ_SPEC, price=US_PRICE, notes=""):
    return {"market": market, "what": what, "quote": spec_quote, "lev": lev, "margin": margin, "src": src, "price": price,
            "status": "builders_docs", "notes": notes}


# Evidence, market by market. "quote" is the builder's own words (shortened with "..." only).
EVIDENCE = [
    stock("xyz:SOXL-PERP", "1 share of the Direxion Daily Semiconductor Bull 3X Shares ETF (NYSE Arca: SOXL)",
          "SOXL references 1 share of the Direxion Daily Semiconductor Bull 3X Shares (NYSE Arca: SOXL), quoted in USD. The fund seeks "
          "daily investment results of 300% of the daily performance of the ICE Semiconductor Index ...; leverage resets daily.",
          "10x", "isolated only",
          notes="The underlying is itself a leveraged fund (3 times a chip-stock index, reset daily)."),
    stock("xyz:MU-PERP", "1 share of Micron Technology (Nasdaq: MU)",
          "MU references 1 share of Micron Technology, Inc. common stock (Nasdaq: MU), quoted in USD.", "10x", "cross"),
    {"market": "xyz:SP500-PERP", "what": "the S&P 500 index",
     "quote": "S&P500 references the S&P 500 Index ... The S&P 500 Index is a product of S&P Dow Jones Indices LLC and has been "
              "licensed for use by trade[XYZ].", "lev": "50x", "margin": "cross", "src": XYZ_IDX, "price": IDX_PRICE,
     "status": "builders_docs", "notes": "Also in the Specification Index (" + XYZ_SPEC + ")."},
    {"market": "xyz:XYZ100-PERP", "what": "the builder's own XYZ U.S. 100 index (100 large US-listed non-financial companies)",
     "quote": "XYZ100 tracks a modified market-capitalization-weighted index of 100 of the largest, most actively-traded, "
              "non-financial companies that are listed on a U.S. stock exchange.", "lev": "30x", "margin": "cross", "src": XYZ_IDX,
     "price": IDX_PRICE, "status": "builders_docs",
     "notes": "The index is the builder's own (XYZ U.S. 100 Index). The builder does not call it the Nasdaq-100, so we do not either."},
    stock("xyz:AMD-PERP", "1 share of Advanced Micro Devices (Nasdaq: AMD)",
          "AMD references 1 share of Advanced Micro Devices, Inc. common stock (Nasdaq: AMD), quoted in USD.", "10x", "isolated only"),
    stock("xyz:SNDK-PERP", "1 share of Sandisk (Nasdaq: SNDK)",
          "SNDK references 1 share of Sandisk Corporation common stock (Nasdaq: SNDK), quoted in USD.", "10x", "cross"),
    stock("xyz:NBIS-PERP", "1 share of Nebius Group (Nasdaq: NBIS)",
          "NBIS references 1 Nebius Group N.V. Class A ordinary share (Nasdaq: NBIS), quoted in USD.", "10x", "isolated only"),
    stock("xyz:DRAM-PERP", "1 share of the Roundhill Memory ETF (Cboe BZX: DRAM)",
          "DRAM references 1 share of the Roundhill Memory ETF (Cboe BZX: DRAM), quoted in USD.", "20x", "cross",
          notes="The underlying is a fund of memory-chip companies, not the memory chips themselves."),
    stock("xyz:KORU-PERP", "1 share of the Direxion Daily MSCI South Korea Bull 3X ETF (NYSE Arca: KORU)",
          "KORU references 1 share of the Direxion Daily MSCI South Korea Bull 3X ETF (NYSE Arca: KORU), quoted in USD. The fund seeks "
          "daily investment results ... of 300% of the performance of the MSCI Korea 25/50 Index.", "10x", "isolated only",
          notes="The underlying is itself a leveraged fund (3 times a Korean stock index, daily)."),
    stock("xyz:SPCX-PERP", "1 share of Space Exploration Technologies, SpaceX (Nasdaq: SPCX)",
          "SPCX references 1 share of Space Exploration Technologies Corp. Class A common stock (Nasdaq: SPCX), quoted in USD.",
          "20x", "cross", notes="Listed first as a pre-IPO market; the builder's Pre-IPO Specification Index marks it as converted."),
    stock("xyz:SKHX-PERP", "1 share of SK hynix (Korea Exchange: 000660), in US dollars",
          "The SKHX oracle price tracks the USD value of 1 common share of SK Hynix Inc. The oracle price can be replicated by dividing "
          "the KRW price of 000660 KS Equity by the USD/KRW exchange rate.", "10x", "cross", src=XYZ_KR, price=KR_PRICE,
          notes="The Specification Index lists this market as SKHYNIX; the builder's pre-IPO page says xyz:SKHX is that market."),
    stock("xyz:NVDA-PERP", "1 share of NVIDIA (Nasdaq: NVDA)",
          "NVDA references 1 share of NVIDIA Corporation common stock (Nasdaq: NVDA), quoted in USD.", "20x", "cross"),
    stock("xyz:SMSN-PERP", "1 share of Samsung Electronics (Korea Exchange: 005930), in US dollars",
          "The SMSN oracle price tracks the USD value of 1 common share of Samsung Electronics Co., Ltd. The oracle price can be "
          "replicated by dividing the KRW price of 005930 KS Equity ... by the USD/KRW exchange rate.", "10x", "isolated only",
          src=XYZ_KR, price=KR_PRICE, notes="The Specification Index lists this market as SAMSUNG."),
    {"market": "io:NBIS-PERP", "what": "",
     "quote": "NBIS (Nebius Group NV): Symbol NBIS; Reference issuer Nebius Group NV; Quote asset USDC; Maximum leverage 15x; "
              "Margin mode Isolated; Market Type US Equity.", "lev": "15x", "margin": "isolated only", "src": ENT_EQ,
     "price": "The price on the underlying's primary public listing venue in its regular session; outside it, an internal price "
              "anchored to the last public price (an approved after-hours venue if there is one)",
     "status": "partly_sourced",
     "notes": "The builder (Entropy, 'ticker: io') names the issuer but not the exact share or exchange, and the deployer address in "
              "its docs differs from Hyperliquid's perpDexs entry for io (the oracle updater address matches). Leverage and margin "
              "mode agree with Hyperliquid's metadata. The page keeps this market's name as listed."},
    stock("xyz:CRCL-PERP", "1 share of Circle Internet Group (NYSE: CRCL)",
          "CRCL references 1 share of Circle Internet Group, Inc. Class A common stock (NYSE: CRCL), quoted in USD.", "10x", "cross"),
    stock("xyz:PURRDAT-PERP", "1 share of Hyperliquid Strategies (Nasdaq: PURR)",
          "PURRDAT references 1 share of Hyperliquid Strategies Inc. common stock (Nasdaq: PURR), quoted in USD.", "10x",
          "isolated only", notes="The market's name (PURRDAT) is not the stock's ticker (PURR)."),
    stock("xyz:INTC-PERP", "1 share of Intel (Nasdaq: INTC)",
          "INTC references 1 share of Intel Corporation common stock (Nasdaq: INTC), quoted in USD.", "10x", "cross"),
    stock("xyz:TSLA-PERP", "1 share of Tesla (Nasdaq: TSLA)",
          "TSLA references 1 share of Tesla, Inc. common stock (Nasdaq: TSLA), quoted in USD.", "20x", "cross"),
    stock("xyz:MRNA-PERP", "1 share of Moderna (Nasdaq: MRNA)",
          "MRNA references 1 share of Moderna, Inc. common stock (Nasdaq: MRNA), quoted in USD.", "10x", "isolated only"),
    stock("xyz:AVGO-PERP", "1 share of Broadcom (Nasdaq: AVGO)",
          "AVGO references 1 share of Broadcom Inc. common stock (Nasdaq: AVGO), quoted in USD.", "10x", "isolated only"),
]
BUILDERS = {"xyz": ("trade[XYZ]", "XYZ", XYZ_ARCH), "io": ("Entropy", "EntropyIO", "Entropy docs, Entropy Architecture: 'Entropy (ticker: io)'")}
COLUMNS = ["dex", "builder", "hyperliquid_dex_full_name", "market_as_listed", "share_of_builder_listed_value_5nov", "status",
           "what_it_tracks", "price_source", "max_leverage_and_margin", "builder_words", "source_url", "dex_link_source",
           "cross_check", "checked_utc_date", "notes"]


def event_shares():
    rows = [r for r in csv.DictReader(open(PER_MARKET, encoding="utf-8")) if r["date_utc"] == "2026-11-05" and r["scope"] == "builder_listed"]
    total = float(next(r for r in rows if r["row_type"] == "scope_total_unique_wallets")["value_force_closed_usd"])
    return {r["market"]: float(r["value_force_closed_usd"]) / total for r in rows if r["row_type"] == "market"}


def main():
    share = event_shares()
    want = {m for m, s in share.items() if s >= MIN_SHARE} | set(NAMED_ON_PAGE)
    ev = {e["market"]: e for e in EVIDENCE}
    missing = want - set(ev)
    if missing:
        raise SystemExit(f"no evidence row for {sorted(missing)}")
    out = []
    for m in sorted(want, key=lambda k: -share[k]):
        e = ev[m]
        dex = m.split(":")[0]
        b, full, link = BUILDERS[dex]
        if e["status"] == "builders_docs" and not (e["what"] and e["src"].startswith("https://")):
            raise SystemExit(f"{m}: a verified row needs what it tracks and a source URL")
        out.append([dex, b, full, m, f"{share[m]:.4f}", e["status"], e["what"], e["price"], f"{e['lev']}, {e['margin']}", e["quote"],
                    e["src"], link, f"{HL}: max leverage {e['lev']} and margin mode agree", CHECKED, e["notes"]])
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(out)
    print(f"{OUT}: {len(out)} markets; " + ", ".join(f"{s}: {sum(1 for r in out if r[5] == s)}" for s in ("builders_docs", "partly_sourced", "no_source_found")))


if __name__ == "__main__":
    main()
