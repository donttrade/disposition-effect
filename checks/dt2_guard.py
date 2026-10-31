"""Release guard for S3 (merged uploads; Tester S3 re-test 1 guard 3, re-test 4): the /report/ page's small-file notice
names the DT-2 result "No sign", which the report renders only once DT-2 (S1) is in: wording.js exports VERDICT_STRINGS
with "No sign". Bundling a site whose built report page says "No sign" while wording.js has no such VERDICT_STRINGS
would put the notice live next to a report that says something else. run.sh bundle runs this before it replaces docs/.

Usage: python3 checks/dt2_guard.py <built site dir> [wording.js]   → exit 0 (fine) or 1 (refused, one line why)."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def problem(site_dir, wording_js=os.path.join(REPO, "site", "static", "js", "paid", "wording.js")):
    page = os.path.join(site_dir, "report", "index.html")
    if not os.path.exists(page):
        return None
    if "No sign" not in open(page, encoding="utf-8").read():
        return None
    src = open(wording_js, encoding="utf-8").read()
    # DT-2's wording.js exports VERDICT_STRINGS and defines the step words (e.g. STEP.none = 'No sign'), which
    # VERDICT_STRINGS spreads in; the stats2f wording has neither.
    has_export = re.search(r"export\s+const\s+VERDICT_STRINGS\s*=", src)
    if not has_export or not re.search(r"['\"]No sign['\"]", src):
        return ("the built /report/ page says \"No sign\" (the S3 small-file notice), but wording.js has no DT-2 "
                "VERDICT_STRINGS with \"No sign\": bundle S3 only with DT-2 (S1)")
    return None


if __name__ == "__main__":
    why = problem(*sys.argv[1:3]) if len(sys.argv) > 1 else "usage: dt2_guard.py <built site dir> [wording.js]"
    if why:
        print("dt2 guard: REFUSED: " + why)
        sys.exit(1)
    print("dt2 guard: PASS")
