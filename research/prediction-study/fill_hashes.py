#!/usr/bin/env python3
"""Writes ONE block of SHA-256 fingerprints into the three places that must agree (plan section 4.4):
partner/PREREG-PREDICTION.md (section 4.3), partner/LICENSING.md and research/prediction-study/RELEASE-NOTES-prediction-v1.md,
plus site/config/prediction_study.json "sha256". The fixture output is regenerated, not trusted.

Usage (Claude Code, repo root): python3 -B research/prediction-study/fill_hashes.py [--check]
--check exits 1 if any of the four places differs from what this would write.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CODE = ["partner/prediction_test.py", "partner/dt1_features.py", "partner/dt1_outcomes.py",
        "partner/prediction_metrics.py"]
SUPPORT = ["partner/make_fixture_prediction.py", "partner/parity/dt1_golden.json", "partner/parity/rules_golden.json",
           "partner/PREREG-PREDICTION-EXAMPLE.md"]
TARGETS = ["partner/PREREG-PREDICTION.md", "partner/LICENSING.md",
           "research/prediction-study/RELEASE-NOTES-prediction-v1.md"]
MARK = re.compile(r"<!-- BEGIN PREDICTION SHA-256 -->\n.*?<!-- END PREDICTION SHA-256 -->", re.S)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture_hashes():
    with tempfile.TemporaryDirectory() as td:
        subprocess.run([sys.executable, "-I", os.path.join(REPO, "partner", "make_fixture_prediction.py"), "--out", td],
                       check=True)
        out = subprocess.run([sys.executable, "-I", os.path.join(REPO, "partner", "prediction_test.py"),
                              os.path.join(td, "trades.csv"), os.path.join(td, "accounts.csv"),
                              os.path.join(REPO, "partner", "PREREG-PREDICTION-EXAMPLE.md")],
                             capture_output=True, check=True).stdout
        return {"fixture trades.csv": sha(open(os.path.join(td, "trades.csv"), "rb").read()),
                "fixture accounts.csv": sha(open(os.path.join(td, "accounts.csv"), "rb").read()),
                "fixture expected output": sha(out)}


def block():
    code = {p: sha(open(os.path.join(REPO, p), "rb").read()) for p in CODE}
    sup = {p: sha(open(os.path.join(REPO, p), "rb").read()) for p in SUPPORT}
    fx = fixture_hashes()
    lines = ["<!-- BEGIN PREDICTION SHA-256 -->", "", "The analysis code (`sha256sum` prints the same):", "", "```"]
    lines += ["%s  %s" % (h, p) for p, h in code.items()]
    lines += ["```", "", "The supporting files and the fixture run:", "", "```"]
    lines += ["%s  %s" % (h, p) for p, h in sup.items()]
    lines += ["%s  %s" % (h, p) for p, h in fx.items()]
    lines += ["```", "", "<!-- END PREDICTION SHA-256 -->"]
    return "\n".join(lines), dict(code, **sup, **fx)


def main():
    text, hashes = block()
    stale = []
    for t in TARGETS:
        path = os.path.join(REPO, t)
        old = open(path, encoding="utf-8").read()
        if not MARK.search(old):
            raise SystemExit("no hash markers in " + t)
        new = MARK.sub(lambda m: text, old)
        if new != old:
            stale.append(t)
            if "--check" not in sys.argv:
                open(path, "w", encoding="utf-8").write(new)
    sp = os.path.join(REPO, "site", "config", "prediction_study.json")
    st = json.load(open(sp, encoding="utf-8"))
    want = {p: hashes[p] for p in CODE}
    if st.get("sha256") != want:
        stale.append("site/config/prediction_study.json")
        if "--check" not in sys.argv:
            st["sha256"] = want
            open(sp, "w", encoding="utf-8").write(json.dumps(st, indent=2) + "\n")
    sys.stdout.write(("stale: %s\n" % ", ".join(stale)) if stale else "all four places agree\n")
    return 1 if (stale and "--check" in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(main())
