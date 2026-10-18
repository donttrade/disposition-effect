"""Download and cache the three Kenneth French data files this study needs.

Idempotent: a file already present in data/ with a non-trivial size is left
alone, so re-running this costs nothing and the study never re-fetches on
every run. Delete data/ to force a clean download.

    python3 fetch.py

The French library ships each series as a zip containing one CSV. We keep the
zip exactly as served and also write the extracted CSV next to it, so that a
reader can open the raw text and check the parsing in volmom.py against it.
"""
from __future__ import annotations

import io
import os
import ssl
import sys
import urllib.request
import zipfile

FRENCH_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"

# name -> (zip filename on the French server, extracted csv we write)
DATASETS = {
    "momentum_monthly": "F-F_Momentum_Factor_CSV.zip",
    "momentum_daily": "F-F_Momentum_Factor_daily_CSV.zip",
    "research_factors_monthly": "F-F_Research_Data_Factors_CSV.zip",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# A truncated download can still produce a file, so "already cached" means
# "present AND larger than this", not merely "present".
MIN_PLAUSIBLE_BYTES = 1024

# Some servers (Harvard Dataverse among them) answer HTTP 403 to Python's
# default "Python-urllib/3.x" User-Agent, so every request names itself.
USER_AGENT = "donttrade-reproduce/1.0 (+https://github.com/donttrade/disposition-effect)"


def _ssl_context() -> ssl.SSLContext | None:
    """Honour an outbound proxy's CA bundle if the environment names one.

    Never disables verification -- if no bundle is configured we fall back to
    urllib's default context, which is already verifying.
    """
    bundle = (
        os.environ.get("REQUESTS_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("CURL_CA_BUNDLE")
    )
    if bundle and os.path.exists(bundle):
        return ssl.create_default_context(cafile=bundle)
    return None


def csv_path_for(dataset_name: str) -> str:
    """Where volmom.py expects to find the extracted CSV for a dataset."""
    return os.path.join(DATA_DIR, dataset_name + ".csv")


def download_dataset(dataset_name: str, zip_filename: str) -> str:
    """Fetch one French zip, extract its single CSV, return the CSV's path."""
    zip_path = os.path.join(DATA_DIR, zip_filename)
    csv_path = csv_path_for(dataset_name)

    if (
        os.path.exists(csv_path)
        and os.path.getsize(csv_path) > MIN_PLAUSIBLE_BYTES
    ):
        print(
            "cached   %-26s %9d bytes  %s"
            % (dataset_name, os.path.getsize(csv_path), csv_path)
        )
        return csv_path

    url = FRENCH_BASE + "/" + zip_filename
    context = _ssl_context()
    request_kwargs = {"timeout": 120}
    if context is not None:
        request_kwargs["context"] = context

    print("fetching %-26s %s" % (dataset_name, url))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, **request_kwargs) as response:
        payload = response.read()

    with open(zip_path, "wb") as handle:
        handle.write(payload)

    archive = zipfile.ZipFile(io.BytesIO(payload))
    members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
    if len(members) != 1:
        raise SystemExit(
            "expected exactly one CSV inside %s, found %r"
            % (zip_filename, archive.namelist())
        )

    # French's files are not UTF-8 -- they carry Latin-1 punctuation in the
    # preamble (e.g. the copyright line), so decoding as UTF-8 raises.
    text = archive.read(members[0]).decode("latin-1")
    with open(csv_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    print(
        "wrote    %-26s %9d bytes  %s"
        % (dataset_name, os.path.getsize(csv_path), csv_path)
    )
    return csv_path


def main() -> int:
    os.makedirs(DATA_DIR, exist_ok=True)
    for dataset_name, zip_filename in DATASETS.items():
        download_dataset(dataset_name, zip_filename)
    print("\nall three French datasets are in %s" % DATA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
