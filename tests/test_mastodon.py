"""2 Nov (owner): Mastodon profile verification. Every template page's <head> carries
<link rel="me" href="https://mastodon.social/@donttradestudy">, from [site] mastodon_url in site.toml."""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
sys.path.insert(0, SITE)
import build as B  # noqa: E402

URL = "https://mastodon.social/@donttradestudy"
LINK = f'<link rel="me" href="{URL}">'


def test_setting_in_site_toml():
    cfg = B.read_toml(os.path.join(SITE, "config", "site.toml"), "site.toml")
    assert cfg["site"]["mastodon_url"] == URL
    base = open(os.path.join(SITE, "templates", "base.html"), encoding="utf-8").read()
    assert URL not in base   # not hard-coded
    assert "site.mastodon_url" in base


def test_home_page_head_has_rel_me(built_site):
    html = open(B.out_file(str(built_site["out"]), "/"), encoding="utf-8").read()
    head = re.search(r"(?s)<head>.*?</head>", html).group(0)
    assert head.count(LINK) == 1


def test_every_template_page_has_rel_me(built_site):
    out = str(built_site["out"])
    for path in ("/pricing/", "/privacy/", "/fr/confidentialite/", "/tools/", "/before-you-pay/"):
        html = open(B.out_file(out, path), encoding="utf-8").read()
        assert LINK in re.search(r"(?s)<head>.*?</head>", html).group(0), path
