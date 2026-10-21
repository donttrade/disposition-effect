"""The column whitelist in detect.js must equal the Python reference's, field for field."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))
import engine_ref as E  # noqa: E402


def js_value(expr):
    code = ("import('./site/static/js/engine/detect.js').then(m => "
            f"process.stdout.write(JSON.stringify({expr})))")
    out = subprocess.run(["node", "--input-type=module", "-e", code], cwd=REPO, capture_output=True, text=True,
                         check=True)
    return json.loads(out.stdout)


def test_signatures_equal():
    assert js_value("m.SIGNATURES") == E.SIGNATURES


def test_orders_and_titles_equal():
    got = js_value("[m.CSV_ORDER, m.HTML_ORDER, m.HEADER_TITLES, m.SECTION_TITLES, m.SEARCH_ROWS]")
    assert got == [E.CSV_ORDER, E.HTML_ORDER, E.HEADER_TITLES, E.SECTION_TITLES, E.SEARCH_ROWS]


def test_no_account_or_name_alias():
    # The whitelist must never contain account, alias, owner or name columns.
    banned = {"account", "accountid", "clientaccountid", "accountalias", "alias", "model", "traderid", "name",
              "owner", "comment", "comments", "balance"}
    for sig in E.SIGNATURES.values():
        for aliases in sig["fields"].values():
            for a in aliases:
                assert a.split("#")[0] not in banned, a
