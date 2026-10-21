#!/usr/bin/env python3
"""Harvest check: every $ amount on today's live /pricing/ page must come from prices.json.

An amount passes if it is a product's price_usd or standard_price_usd, or is computed
from a rule in the file (the re-check is percent_of_engagement % of a firm price).
Run against docs/pricing/index.html (the live page) or any built page.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def allowed_amounts(prices):
    out = set()
    for p in prices["products"]:
        out.add(p["price_usd"])
        if p["standard_price_usd"] is not None:
            out.add(p["standard_price_usd"])
    pct = prices["rules"]["recheck"]["percent_of_engagement"]
    for p in prices["products"]:
        if p["audience"] == "firm":
            out.add(p["price_usd"] * pct / 100)
    return out


def amounts_in(html):
    text = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html)
    return [float(m.replace(",", "")) for m in re.findall(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)", text)]


def main(path):
    with open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8") as f:
        ok = allowed_amounts(json.load(f))
    with open(path, encoding="utf-8") as f:
        found = amounts_in(f.read())
    missing = sorted({a for a in found if a not in ok})
    print(f"harvest: {len(found)} amounts on {os.path.relpath(path, REPO)}, distinct {sorted(set(found))}")
    if missing:
        print("FAIL: not in prices.json and not computed from it:", missing)
        return 1
    print("harvest: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "docs", "pricing", "index.html")))
