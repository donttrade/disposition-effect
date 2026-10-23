"""Delivery plan C-12, now (P-3): /sample-report/ no longer says the buyer's report "would be computed the
same way": it shows a daily-position PGR/PLR with a percentile, and the $39 report has neither. The lead
says what the page is. (C-12 final, after T-1: the page becomes a real R2 report on a fixture.)"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "checks"))
from lint import lint_text, visible_text  # noqa: E402

# R-D1 D-3: the Architect's exact text.
LEAD = ("This is a research figure from public data. It is not the trader report: the report covers five habits in "
        "your own file, tests up to four of them against chance, and shows no percentile.")


def test_sample_report_lead_says_it_is_not_the_trader_report(built_site):
    t = re.sub(r"\s+", " ", visible_text((built_site["out"] / "sample-report" / "index.html").read_text(encoding="utf-8")))
    assert LEAD in t
    assert "computed the same way from your own trade export" not in t
    assert "what the coming trader report looks like" not in t
    assert lint_text(LEAD) == [] and lint_text(LEAD, "p3", paid=True) == []


def test_the_fix_is_recorded_as_a_lift_fix():
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "checks"))
    import lift_pages
    (old, new), = lift_pages.LIFT_FIXES["/sample-report/"]
    assert new == LEAD and "computed the same way" in old
