"""Tool-card previews (25 Oct sweep, owner: "show it rather than say it").

The previews draw the free tools' own results on the synthetic sample file (site/config/tool_previews.json,
written by checks/make_tool_previews.py). They must match the sample file, show on the cards, stay one link
per card with the picture hidden from screen readers, and the lint exemption for their dollar figures must
stay strict: a figure that is not the tools' own sample output is still a price problem.
"""
import hashlib
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
import lint as L  # noqa: E402

TP = json.load(open(os.path.join(REPO, "site", "config", "tool_previews.json"), encoding="utf-8"))


def test_previews_were_captured_from_the_committed_sample_file():
    with open(os.path.join(REPO, "site", "static", "samples", "demo-trades.csv"), "rb") as f:
        assert TP["sample_sha256"] == hashlib.sha256(f.read()).hexdigest(), "rerun checks/make_tool_previews.py"


def test_home_cards_show_the_previews_as_one_link_each(built_site):
    h = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    cards = re.findall(r'(?s)<li class="tool-card">(.*?)</li>', h)
    assert len(cards) == 3
    for c in cards:
        assert c.count("<a ") == 1 and 'class="tool-card-link"' in c
        assert re.search(r'class="tp [^"]*" aria-hidden="true"', c)
    assert TP["trade_stats"]["net"] in h and TP["trade_stats"]["win_rate"] in h


def test_lint_exempts_only_the_sample_figures():
    ok = f'<p>x</p><!--sample-out--><b>{TP["trade_stats"]["net"]}</b><!--/sample-out-->'
    assert "$" not in L.without_tool_previews(ok).replace("<p>x</p>", "")
    bad = '<!--sample-out--><b>+$12.34</b><!--/sample-out-->'
    assert L.without_tool_previews(bad) == bad
