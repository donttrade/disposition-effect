#!/usr/bin/env python3
"""docs/ is never dated in the future (6 Nov 2026, fix round 1; a build before the push day had been bundled with
DT_TODAY and would have shown "Version 2026-11-06" and a sitemap <lastmod> of tomorrow if shipped early).

Fails (exit 1, one clear message) when docs/ states a date later than the machine's REAL date (DT_TODAY is ignored here):
the terms and privacy versions ("Version 2026-11-06", "Version du …") and every sitemap <lastmod>. Run by
./site/run.sh check. Usage: python3 checks/docs_date.py [docs-dir]"""
import datetime
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_PAGES = ("terms", "privacy", "fr/conditions", "fr/confidentialite")


def future_dates(docs, today):
    iso = today.isoformat()
    found = []
    for rel in VERSION_PAGES:
        p = os.path.join(docs, rel, "index.html")
        if os.path.exists(p):
            for d in re.findall(r"[Vv]ersion(?: du)? (\d{4}-\d{2}-\d{2})", open(p, encoding="utf-8").read()):
                if d > iso:
                    found.append((f"/{rel}/ version", d))
    sm = os.path.join(docs, "sitemap.xml")
    if os.path.exists(sm):
        for loc, d in re.findall(r"<loc>([^<]+)</loc><lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", open(sm, encoding="utf-8").read()):
            if d > iso:
                found.append((f"sitemap lastmod {loc}", d))
    return found


def main(argv):
    docs = argv[0] if argv else os.path.join(REPO, "docs")
    today = datetime.date.today()
    found = future_dates(docs, today)
    if found:
        print(f"docs_date: FAIL: {os.path.relpath(docs, REPO)} is dated after today ({today.isoformat()}): "
              + "; ".join(f"{w} {d}" for w, d in found[:5]) + (" …" if len(found) > 5 else "")
              + ". Rebuild it on or after that day with ./site/run.sh bundle (no DT_TODAY); never commit or deploy it earlier.")
        return 1
    print("docs_date: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
