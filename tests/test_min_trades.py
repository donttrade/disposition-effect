"""Release test B3 (TESTER-REPORT-DT2-RELEASE-2026-10-31): the fewest closed trades a report takes.

* One site constant, merge.js MIN_TRADES, equal to the Worker's (dt-private src/core/validate.mjs MIN_ROWS and its
  too_few_rows message); site/build.py reads it for the pages; no template or page script types the number.
* The minimum is stated on /pricing/ (the trader card and Before you pay, which the pay dialog's full details copy),
  /before-you-pay/, /terms/, the FR twins and the report's upload step.
The panel's behaviour (Run off below the minimum) is in tests/test_uploads_merge.py."""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import visible_text  # noqa: E402

PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
MERGE = os.path.join(REPO, "site", "static", "js", "paid", "merge.js")


def site_min():
    m = re.findall(r"^export const MIN_TRADES = ([0-9]+);$", open(MERGE, encoding="utf-8").read(), re.M)
    assert len(m) == 1
    return int(m[0])


@pytest.mark.skipif(not os.path.isfile(os.path.join(PRIVATE, "src", "core", "validate.mjs")), reason="dt-private (server) not present")
def test_the_site_minimum_is_the_workers():
    v = open(os.path.join(PRIVATE, "src", "core", "validate.mjs"), encoding="utf-8").read()
    worker = int(re.search(r"^export const MIN_ROWS = ([0-9]+);", v, re.M).group(1))
    assert site_min() == worker
    app = open(os.path.join(PRIVATE, "src", "core", "app.mjs"), encoding="utf-8").read()
    assert f"at least {worker} different closed trades" in app


def test_the_number_is_typed_once():
    n = str(site_min())
    for root in (os.path.join(REPO, "site", "templates"), os.path.join(REPO, "site", "static", "js", "paid")):
        for dp, _, fns in os.walk(root):
            for fn in fns:
                p = os.path.join(dp, fn)
                s = re.sub(r"(?s)\{#.*?#\}", "", open(p, encoding="utf-8").read())   # TRANSLATOR CHECK notes quote the EN text
                hits = re.findall(rf"at least {n} closed|au moins {n} transactions|MIN_TRADES = {n}\b", s)
                if p == MERGE:
                    assert hits == [f"MIN_TRADES = {n}"], hits
                else:
                    assert hits == [], (p, hits)


def text(out, rel):
    return re.sub(r"\s+", " ", visible_text(open(os.path.join(out, rel), encoding="utf-8").read()))


def test_every_page_states_the_minimum(built_site):
    out, n = built_site["out"], site_min()
    pr = text(out, "pricing/index.html")
    assert f"Needs at least {n} closed trades" in pr                                         # the trader card
    want = f"Needs at least {n} closed trades per report: with fewer, the page does not send the file and no run is used."
    assert want in pr and want in text(out, "before-you-pay/index.html")                     # Before you pay (and the dialog's copy)
    assert f"at least {n} closed trades per report" in text(out, "terms/index.html")
    assert f"Au moins {n} transactions fermées par rapport" in text(out, "fr/avant-de-payer/index.html")
    assert f"au moins {n} transactions fermées par rapport" in text(out, "fr/conditions/index.html")
    assert f"Needs at least {n} closed trades." in text(out, "report/index.html")
