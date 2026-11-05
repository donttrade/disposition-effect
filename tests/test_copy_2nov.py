"""2 Nov owner-approved copy fixes: /independence/ no longer says "Readers pay nothing" (the donttrade test is on
sale); /about/ lists Bluesky, Threads and Mastodon among the official channels, Mastodon as rel="me"."""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402


def _read(built_site, path):
    return open(B.out_file(str(built_site["out"]), path), encoding="utf-8").read()


def test_independence_names_the_one_paid_product(built_site):
    html = _read(built_site, "/independence/")
    assert "Readers pay nothing" not in html and "the one paid product" not in html
    assert ('<p>Two sources. Firms and brokers pay for fixed-scope measurements of their own data. The research, the '
            'newsletter and the free tools cost readers nothing; for traders, the only paid product is '
            '<a href="/pricing/#traders">the donttrade test</a>. No affiliate links, no sponsorships, no referral fees '
            'from any firm, broker or platform.</p>') in html
    assert 'id="traders"' in _read(built_site, "/pricing/")   # the link lands


def test_about_lists_the_three_new_channels(built_site):
    about = _read(built_site, "/about/").split("<!--frozen:end-->")[1]
    where = re.search(r"(?s)<h2>Where to find this</h2>\s*<p>(.*?)</p>", about).group(1)
    for url, text in [("https://x.com/donttradestudy", "x.com/donttradestudy"),
                      ("https://donttrade.substack.com", "donttrade.substack.com"),
                      ("https://www.tiktok.com/@donttradestudy", "tiktok.com/@donttradestudy"),
                      ("https://www.instagram.com/donttradestudy/", "instagram.com/donttradestudy"),
                      ("https://www.youtube.com/@donttradestudy", "youtube.com/@donttradestudy"),
                      ("https://bsky.app/profile/donttradestudy.bsky.social", "bsky.app/profile/donttradestudy.bsky.social"),
                      ("https://www.threads.com/@donttradestudy", "threads.com/@donttradestudy"),
                      ("https://mastodon.social/@donttradestudy", "mastodon.social/@donttradestudy")]:
        assert f'<a href="{url}" rel="me noopener">{text}</a>' in where, url


def test_about_names_the_one_paid_product(built_site):
    html = _read(built_site, "/about/")
    assert "Readers pay nothing" not in html and "readers pay nothing" not in html
    assert "the one paid product" not in html   # 3 Nov: untrue for firms, who pay for measurements
    assert "Firms pay for measurements. The research and free tools cost readers nothing." in html
    assert ("Firms pay for fixed-scope measurements of their own data; the research and free tools cost readers nothing, "
            'and for traders the only paid product is <a href="/pricing/#traders">the donttrade test</a>; no firm can change a '
            "number.") in html
