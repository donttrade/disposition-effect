#!/usr/bin/env python3
"""Download the raw public inputs behind the /tools/ previews into checks/real_data/raw/ (gitignored; never committed).

    python3 -I checks/real_data/fetch.py                 # both files; refuses a file whose SHA-256 differs
    python3 -I checks/real_data/fetch.py --accept-new-h10  # the Board's H.10 file changes every week: take today's

Inputs (licences and attribution: DATA_LICENSE.md):
  * Stock Transactions Dataset, Mendeley Data V1, doi:10.17632/k4tnk2nggv.1, CC BY 4.0. The SHA-256 below equals the
    hash Mendeley's public API publishes for the file (public-api/datasets/k4tnk2nggv/files, sha256_hash).
  * Federal Reserve Board, H.10 Foreign Exchange Rates, euro, historical file dat00_eu.htm (public domain; cite the
    Board). Updated weekly, so its hash is kept in checks/real_data/eurusd.json (calc_eurusd.py) and a different file
    is refused unless --accept-new-h10 is given. FRED carries the same series but its terms forbid caching and
    commercial use without consent, so it is not used.
Then it runs make_real_csv.py, which writes raw/real-trades.csv and checks its SHA-256.
Nothing here runs at build time: the site build reads the committed JSON and the coded CSV only.
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
MENDELEY = {
    "file": "mendeley-open-stock-transactions-2020-2024.xlsx",
    "url": "https://data.mendeley.com/public-files/datasets/k4tnk2nggv/files/b37fa5f8-e979-44e8-aaea-baeb143b6e8c/file_downloaded",
    "sha256": "000dbad9f8ed661f7991ad72b3af29f11e9cda2d5a50162f34bf289f78373bcb",
}
H10 = {"file": "h10-hist-dat00_eu.htm", "url": "https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm"}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def h10_kept_sha():
    """The H.10 file the committed eurusd.json was computed from."""
    p = os.path.join(HERE, "eurusd.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("raw_sha256")


def get(spec, want, accept_new=False):
    path = os.path.join(RAW, spec["file"])
    if not os.path.exists(path):
        os.makedirs(RAW, exist_ok=True)
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "donttrade-real-data/1"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    got = sha256(path)
    if want and got != want and not accept_new:
        os.replace(path, path + ".refused")
        sys.exit(f"{spec['file']}: SHA-256 {got} differs from {want}; refused (moved to {path}.refused)")
    print(spec["file"], got)
    return path


def main(argv):
    get(MENDELEY, MENDELEY["sha256"])
    get(H10, h10_kept_sha(), accept_new="--accept-new-h10" in argv)
    # the trade file the scripts read, raw/real-trades.csv (real tickers, so gitignored like the xlsx)
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_real_csv.py")], check=True)


if __name__ == "__main__":
    main(sys.argv[1:])
