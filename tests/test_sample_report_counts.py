"""/sample-report/ 2,262 vs 2,264 (checked 21 Oct 2026): not a discrepancy, two labelled groups.

samples/sample_trader_report.py, re-run on the CC0 file (Harvard Dataverse doi:10.7910/DVN/NI6SBJ,
file 4053809; panel cross-check PASS: PGR 0.1925, PLR 0.1200, ratio 1.61 over 4,659 traders) prints:
  traders with >= 30 sell-days                              : 2,264   (n_elig: the selection pool)
  comparison group (>= 30 sell-days, both PGR and PLR defined): 2,262 (n_grp)
The two eligible traders left out (SP1005826, SP1006600) never held a position at a loss, so their
PLR is undefined. The page already words the groups apart (corrections log, 19 Oct 2026, item 3).
This test keeps the page and the script's wording tied to those two groups.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEAD = r"([\d,]+) traders (?:in the same dataset )?with at least 30 sell-days"
BOTH = " and both a PGR and a PLR defined"


def _text(html):
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", html)))


def test_sample_report_names_two_groups_each_with_one_count(built_site):
    t = _text((built_site["out"] / "sample-report" / "index.html").read_text(encoding="utf-8"))
    grp = set(re.findall(LEAD + BOTH, t))
    elig = set(re.findall(LEAD + "(?!" + BOTH + ")", t))
    assert grp == {"2,262"} and elig == {"2,264"}, (grp, elig)


def test_the_script_words_the_groups_the_same_way():
    src = open(os.path.join(REPO, "samples", "sample_trader_report.py"), encoding="utf-8").read()
    assert "among the {v['n_elig']:,} traders with at least {MIN_SELL_DAYS} sell-days, take" in src
    assert "Among the {v['n_grp']:,} traders in the same dataset with at least {MIN_SELL_DAYS} sell-days" + BOTH in src
    assert 'grp = ct.loc[eligible.index].dropna(subset=["pgr", "plr"])' in src   # n_grp ⊆ n_elig
