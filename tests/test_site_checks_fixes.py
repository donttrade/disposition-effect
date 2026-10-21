"""Offline tests for two fixes to the live-site checks in checks/tests/ (21 Oct 2026, after launch).

1. test_site_security.py::test_repo_history_has_no_secrets_or_stray_emails crashed with a
   UnicodeDecodeError on a binary blob in history. It now reads blobs as bytes, skips binary
   ones (a NUL byte) and decodes text with errors='replace'. It must still FAIL on a real secret
   or stray email: the fakes below are assembled at run time, so no literal ever sits in the repo.
2. test_site_functional.py::test_external_links_not_404 checked <form action> URLs
   (https://api.web3forms.com/submit is POST-only and answers 403 to GET). It now checks only
   <a href> targets, and still fails on a real 404.
"""
import os
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks", "tests"))
import test_site_functional as F  # noqa: E402
import test_site_security as S  # noqa: E402

FAKE_SECRET = "sk_" + "live_" + "Zq9" * 8                    # built here, never stored whole
FAKE_EMAIL = "stray.person" + "@" + "elsewhere-mail" + ".test"
BINARY = b"RIFF\x00\x00\x00\x00WEBPVP8 \xff\xfe\x00\x9c" + bytes(range(256)) * 4


def test_blob_findings_skips_binary_and_survives_bad_bytes():
    assert S.blob_findings("img/x.webp", "a" * 40, BINARY) == []
    # invalid UTF-8 in a text blob no longer crashes, and the finding after it is still reported
    data = b"caf\xe9 \xff key = " + FAKE_SECRET.encode() + b"\nmail " + FAKE_EMAIL.encode()
    bad = S.blob_findings("notes.txt", "b" * 40, data)
    assert ("notes.txt", "bbbbbbb", "sk_l…") in bad
    assert any(x[2].startswith("email:stra…@") for x in bad), bad
    assert all(FAKE_SECRET not in str(x) for x in bad), "the full secret is never printed"
    assert S.blob_findings("ok.md", "c" * 40, b"write to donttrade.research@gmail.com") == []


def _fake_github(monkeypatch, blobs):
    """gh api, offline: one commit whose tree holds `blobs` {path: bytes}."""
    shas = {f"{i:040x}": (p, d) for i, (p, d) in enumerate(blobs.items(), 1)}

    def gh(path, raw=False):
        if "/commits?" in path:
            return '[{"sha": "c0ffee"}]'
        if "/git/trees/" in path:
            import json
            return json.dumps({"tree": [{"type": "blob", "path": p, "sha": s} for s, (p, _) in shas.items()]})
        raise AssertionError(path)

    monkeypatch.setattr(S, "_gh", gh)
    monkeypatch.setattr(S, "_gh_bytes", lambda path: shas[path.rsplit("/", 1)[1]][1])


def test_history_scan_reads_binary_blobs_and_passes_when_clean(monkeypatch):
    _fake_github(monkeypatch, {"static/img/hero.webp": BINARY, "README.md": b"donttrade.research@gmail.com\n"})
    S.test_repo_history_has_no_secrets_or_stray_emails()


@pytest.mark.parametrize("planted", ["secret", "email"])
def test_history_scan_still_fails_on_a_planted_secret_or_email(monkeypatch, planted):
    text = ("token = " + FAKE_SECRET) if planted == "secret" else ("contact " + FAKE_EMAIL)
    _fake_github(monkeypatch, {"static/img/hero.webp": BINARY, "site/x.py": text.encode() + b" \xff\n"})
    with pytest.raises(AssertionError) as e:
        S.test_repo_history_has_no_secrets_or_stray_emails()
    assert "site/x.py" in str(e.value)


def test_external_link_check_reads_anchors_only_and_still_fails_on_a_404(monkeypatch):
    form = "https://api.web3forms.com/submit"
    dead = "https://example.org/gone"
    live = "https://example.org/fine"
    links = [("https://donttrade.ca/start/", form, form), ("https://donttrade.ca/", dead, dead),
             ("https://donttrade.ca/", live, live), ("https://donttrade.ca/", "/pricing/", "https://donttrade.ca/pricing/")]
    anchors = {dead, live, "https://donttrade.ca/pricing/"}
    assert F.external_link_targets(links, anchors) == sorted([dead, live])
    # the whole test, offline: the crawl yields the links above; the form action would answer 403
    monkeypatch.setattr(F, "crawl", lambda: ({}, links, {}))
    monkeypatch.setattr(F, "_ANCHOR_URLS", anchors)
    codes = {form: 403, dead: 404, live: 200}
    monkeypatch.setattr(F, "_get", lambda url, method="GET", allow_redirects=False:
                        SimpleNamespace(status_code=codes[url], url=url))
    with pytest.raises(AssertionError) as e:
        F.test_external_links_not_404()
    assert dead in str(e.value) and form not in str(e.value)
    codes[dead] = 200
    F.test_external_links_not_404()
