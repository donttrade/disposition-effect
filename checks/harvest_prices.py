#!/usr/bin/env python3
"""Harvest check: every $ amount on today's live /pricing/ page must come from prices.json.

An amount passes if it is a product's price_usd, or is computed
from a rule in the file (the re-check is percent_of_engagement % of a firm price).
Run against docs/pricing/index.html (the live page) or any built page.

Since step 30 (b613c8b) the live page is the v2 build, so the retired amounts ($49, $99, on the
OLD page only) are no longer accepted: --old accepts them, for a pre-bundle page from git.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def allowed_amounts(prices, include_retired=False):
    """Amounts a page may show. include_retired is for the harvest of today's OLD page only."""
    out = set(prices["retired_amounts"]["amounts"]) if include_retired else set()
    for p in prices["products"]:
        out.add(p["price_usd"])
    pct = prices["rules"]["recheck"]["percent_of_engagement"]
    for p in prices["products"]:
        if p["audience"] == "firm":
            out.add(p["price_usd"] * pct / 100)
    return out


def amounts_in(html):
    text = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html)
    return [float(m.replace(",", "")) for m in re.findall(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)", text)]


def main(path, old=False):
    with open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8") as f:
        ok = allowed_amounts(json.load(f), include_retired=old)
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
    args = [a for a in sys.argv[1:] if a != "--old"]
    sys.exit(main(args[0] if args else os.path.join(REPO, "docs", "pricing", "index.html"), old="--old" in sys.argv[1:]))
