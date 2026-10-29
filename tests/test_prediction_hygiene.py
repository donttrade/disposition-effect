"""Prediction study: nothing from the internal Hyperliquid dry run is in this repo (plan section 5.2), and no
address-shaped string is in any study file."""
import os
import re
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
STUDY = ["partner/prediction_test.py", "partner/dt1_features.py", "partner/dt1_outcomes.py",
         "partner/prediction_metrics.py", "partner/make_fixture_prediction.py", "partner/README-PREDICTION.md",
         "partner/EXPORT-GUIDE-PREDICTION.md", "partner/PREREG-PREDICTION-EXAMPLE.md"]


def tracked():
    return subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True, check=True).stdout.split()


def test_no_dry_run_file_is_tracked():
    bad = [p for p in tracked() if re.search(r"(^|/)(hl-dryrun/|derived[^/]*\.csv$|prereg-internal\.md$|"
                                             r"INTERNAL-RESULT\.txt$)", p)]
    assert bad == []


def test_gitignore_guards_the_dry_run():
    text = open(os.path.join(REPO, ".gitignore"), encoding="utf-8").read()
    for pat in ("hl-dryrun/", "derived*.csv", "prereg-internal.md", "INTERNAL-RESULT.txt"):
        assert pat in text.splitlines()


def test_no_address_shaped_string_in_study_files():
    files = STUDY + [p for p in tracked() if p.startswith(("research/prediction-study/", "partner/parity/"))]
    for p in files:
        path = os.path.join(REPO, p)
        if os.path.exists(path):
            assert not ADDR.search(open(path, encoding="utf-8", errors="replace").read()), p
