"""Content checks for https://donttrade.ca (read-only; ~1 request/second).

Run:  pytest -q test_site_content.py
Env:  DT_BASE (default https://donttrade.ca), DT_REPO (default donttrade/disposition-effect)

Covers: price consistency, banned words, anonymity leaks (site, feed, repo commits/files),
third-party resources and cookies, self-reported counts, and GitHub links that 404.
It never writes to the site or the repo.
"""
import os
import re
import json
import time
import subprocess
from functools import lru_cache
from urllib.parse import urljoin, urlparse

import pytest
import requests
from bs4 import BeautifulSoup

BASE = os.environ.get("DT_BASE", "https://donttrade.ca").rstrip("/")
REPO = os.environ.get("DT_REPO", "donttrade/disposition-effect")
HOST = urlparse(BASE).netloc
UA = {"User-Agent": "donttrade-content-check/1.0"}
EXTRA_PATHS = ["/thanks/", "/who-pays/", "/404.html"]  # not in sitemap but published

ALLOWED_EMAIL = "donttrade.research@gmail.com"
ALLOWED_EMAILS = {ALLOWED_EMAIL, "you@example.com"}  # placeholder in subscribe inputs
# Anonymity terms (case-insensitive). The list identifies the owner, so it is NOT in
# this tracked file: it lives in checks/tests/anon_terms.txt (gitignored, one term per
# line) or the file named by DT_ANON_TERMS. Without it the anonymity tests SKIP with a
# reason (visible in the pytest summary); they never silently pass.
_ANON_FILE = os.environ.get("DT_ANON_TERMS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "anon_terms.txt")
ANON_TERMS = []
if os.path.exists(_ANON_FILE):
    with open(_ANON_FILE, encoding="utf-8") as _f:
        ANON_TERMS = [t.strip().lower() for t in _f if t.strip() and not t.startswith("#")]


def _need_anon_terms():
    if not ANON_TERMS:
        pytest.skip("anonymity term list missing (checks/tests/anon_terms.txt or DT_ANON_TERMS)")
BANNED = re.compile(r"\b(certif(?:ied|ication|y)|verif(?:ied|ication|y)|audit(?:ed|s)?)\b(?!/)", re.I)  # skip folder names like verify/
NEGATION = re.compile(r"\b(not|never|no one|nothing|don[’']t|no longer|nor|isn[’']t|without|no)\b", re.I)
# Sentences reviewed and accepted by the owner can be listed here (exact text). Empty by default.
BANNED_ACCEPTED = set()

_last = [0.0]


def _get(url, **kw):
    wait = 0.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get(url, headers=UA, timeout=30, **kw); r.encoding = "utf-8"
    _last[0] = time.time()
    return r


@lru_cache(maxsize=None)
def pages():
    sm = _get(BASE + "/sitemap.xml").text
    paths = [urlparse(u).path for u in re.findall(r"<loc>([^<]+)</loc>", sm)]
    paths += [p for p in EXTRA_PATHS if p not in paths]
    out = {}
    for p in paths:
        r = _get(BASE + p)
        out[p] = r
    return out


def text_of(html):
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style"]):
        t.decompose()
    return re.sub(r"\s+", " ", s.get_text(" ")).strip()


def sentences(txt):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", txt) if x.strip()]


# ---------------------------------------------------------------- prices
EXPECTED = {
    "trial": "745", "snapshot": "2,500", "memo": "6,000", "outcomes pack": "12,000",
}
PRICE_NEAR = re.compile(r"\b(Trial|Snapshot|Memo|Outcomes pack)\b[^$]{0,60}?\$\s?([\d,]+)", re.I)


def test_pages_load():
    bad = {p: r.status_code for p, r in pages().items() if r.status_code != 200 and p != "/404.html"}
    assert not bad, bad


def test_engagement_prices_consistent():
    problems = []
    for p, r in pages().items():
        t = text_of(r.text)
        for m in PRICE_NEAR.finditer(t):
            name, amt = m.group(1).lower(), m.group(2)
            span = m.group(0)
            # skip the re-check example "($1,500 for a Memo)" and "full $745 counts toward a Memo"
            if name == "memo" and amt in ("745", "1,500"):
                continue
            between = span[len(m.group(1)):]
            # another product named between the word and the price: the price belongs to it
            if re.search(r"(Trial|Snapshot|Memo|Outcomes pack)", between, re.I):
                continue
            if amt != EXPECTED[name]:
                problems.append((p, span))
    assert not problems, problems


def test_trader_prices_and_conditions():
    problems = []
    for p, r in pages().items():
        t = text_of(r.text)
        for m in re.finditer(r"[Ff]ounding price[^.]{0,120}", t):
            s = m.group(0)
            if "$" in s and ("$39" not in s or "$79" not in s):
                problems.append((p, "founding", s))
        for m in re.finditer(r"[Ss]tandard (?:prices )?after launch:?[^.]{0,80}", t):
            s = m.group(0)
            if not ("$49" in s and "$99" in s):
                problems.append((p, "standard", s))
        for m in re.finditer(r"within (\d+) days of trial delivery", t):
            if m.group(1) != "60":
                problems.append((p, "credit window", m.group(0)))
        for m in re.finditer(r"(\d+) days of (?:buying|purchase|each renewal)", t):
            if m.group(1) != "14":
                problems.append((p, "trader refund window", m.group(0)))
        if re.search(r"\bCAD\s?\$?\d|\$\d[\d,]*\s?CAD\b|C\$\d", t):
            problems.append((p, "CAD price", "CAD amount stated"))
    assert not problems, problems


def test_card_payment_timing_consistent():
    """Terms/for-firms say the Stripe link is sent WITH the scope; pricing says only AFTER acceptance."""
    stmts = {}
    for p, r in pages().items():
        t = text_of(r.text)
        if re.search(r"Stripe link,? sent (?:only )?after you accept", t) or "Once you accept the scope we send a secure Stripe" in t:
            stmts.setdefault("after acceptance", []).append(p)
        if re.search(r"Stripe link sent with (?:the|your) scope", t):
            stmts.setdefault("with scope", []).append(p)
    assert len(stmts) <= 1, stmts


# ---------------------------------------------------------------- owner content rules
def test_banned_words_only_in_negations():
    hits = []
    for p, r in pages().items():
        for s in sentences(text_of(r.text)):
            if BANNED.search(s) and not NEGATION.search(s) and s not in BANNED_ACCEPTED:
                hits.append((p, s[:200]))
    assert not hits, hits


def test_no_firm_called_fraud():
    hits = [(p, m.group(0)) for p, r in pages().items()
            for m in re.finditer(r".{0,60}\b(fraud\w*|scam\w*|ponzi)\b.{0,60}", text_of(r.text), re.I)]
    assert not hits, hits


def test_research_pages_carry_no_offer_prices():
    hits = []
    for p, r in pages().items():
        if p.startswith("/research/") and p != "/research/":
            t = text_of(r.text)
            for amt in ("$745", "$2,500", "$6,000", "$12,000", "$39 ", "$49 ", "$79 ", "$99 "):
                if amt in t:
                    hits.append((p, amt))
    assert not hits, hits


# ---------------------------------------------------------------- anonymity
def _anon_scan(label, blob):
    low = blob.lower()
    found = []
    for term in ANON_TERMS:
        i = low.find(term)
        if i >= 0:
            found.append((label, f"term#{ANON_TERMS.index(term)} at offset {i}"))
    for e in set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob)):
        el = e.lower()
        if (el not in ALLOWED_EMAILS and not el.endswith("@users.noreply.github.com")
                and not el.endswith("@example.com") and el != "noreply@anthropic.com"):
            found.append((label, "unexpected email address"))
    return found


def test_site_anonymity():
    _need_anon_terms()
    found = []
    for p, r in pages().items():
        found += _anon_scan(p, r.text)  # full HTML source incl. meta/comments
    for extra in ("/feed.xml", "/robots.txt", "/sitemap.xml", "/CNAME"):
        found += _anon_scan(extra, _get(BASE + extra).text)
    assert not found, found


def _gh(path):
    out = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip(f"gh api unavailable: {out.stderr[:120]}")
    return out.stdout


def test_repo_commit_identities():
    _need_anon_terms()
    raw = _gh(f"repos/{REPO}/commits?per_page=100")
    commits = []
    for chunk in re.split(r"(?<=\])\s*(?=\[)", raw.strip()):
        commits += json.loads(chunk)
    found = []
    for c in commits:
        for who in ("author", "committer"):
            meta = c["commit"][who]
            if not meta["email"].endswith("@users.noreply.github.com"):
                found.append((c["sha"][:7], who, "non-noreply email"))
            found += _anon_scan(c["sha"][:7] + " " + who, meta["name"] + " " + meta["email"])
        found += _anon_scan(c["sha"][:7] + " message", c["commit"]["message"])
        if "claude.ai/code/session_" in c["commit"]["message"]:
            found.append((c["sha"][:7], "message", "Claude-Session URL in commit message"))
    assert not found, found


def test_repo_text_files():
    _need_anon_terms()
    tree = json.loads(_gh(f"repos/{REPO}/git/trees/HEAD?recursive=1"))
    found = []
    for e in tree["tree"]:
        if e["type"] != "blob" or not re.search(r"\.(md|py|txt|html|xml|json|svg|csv|cfg|toml|yml|yaml)$|LICENSE|NOTICE|CNAME|\.gitignore$", e["path"]):
            continue
        r = _get(f"https://raw.githubusercontent.com/{REPO}/HEAD/{e['path']}")
        if r.ok:
            found += _anon_scan(e["path"], r.text)
            if "127.0.0.1" in r.text or "localhost:" in r.text:
                found.append((e["path"], "localhost URL"))
    assert not found, found


# ---------------------------------------------------------------- third parties / cookies
def test_no_third_party_resources_or_cookies():
    found = []
    for p, r in pages().items():
        if "set-cookie" in {k.lower() for k in r.headers}:
            found.append((p, "Set-Cookie header"))
        s = BeautifulSoup(r.text, "html.parser")
        for tag, attr in (("script", "src"), ("img", "src"), ("iframe", "src"), ("link", "href"),
                          ("source", "src"), ("video", "src"), ("audio", "src"), ("embed", "src"), ("object", "data")):
            for el in s.find_all(tag):
                u = el.get(attr)
                if not u:
                    continue
                if tag == "link" and not set(el.get("rel") or []) & {"stylesheet", "preload", "icon", "apple-touch-icon", "modulepreload", "prefetch", "preconnect", "dns-prefetch"}:
                    continue
                h = urlparse(urljoin(BASE + p, u)).netloc
                if h and h != HOST:
                    found.append((p, tag, h))
        for m in re.finditer(r"(googletagmanager|google-analytics|gtag\(|fbq\(|plausible|umami|matomo|hotjar|clarity\.ms|segment\.com|cloudflareinsights)", r.text, re.I):
            found.append((p, "tracker signature", m.group(1)))
    assert not found, found


# ---------------------------------------------------------------- self-reported counts
def test_self_counts():
    pg = pages()
    research = BeautifulSoup(pg["/research/"].text, "html.parser")
    studies = {urlparse(a["href"]).path for a in research.find_all("a", href=True)
               if re.fullmatch(r"/research/[a-z0-9-]+/", urlparse(a["href"]).path)}
    corr = BeautifulSoup(pg["/corrections/"].text, "html.parser")
    first_table = corr.find("table")
    n_corr = len(first_table.find("tbody").find_all("tr")) if first_table and first_table.find("tbody") else -1
    problems = []
    for p, r in pg.items():
        t = text_of(r.text)
        for m in re.finditer(r"(\d+) published studies", t):
            if int(m.group(1)) != len(studies):
                problems.append((p, m.group(0), f"/research/ lists {len(studies)}"))
        for m in re.finditer(r"(\d+) corrections", t):
            if int(m.group(1)) != n_corr:
                problems.append((p, m.group(0), f"/corrections/ table has {n_corr}"))
        for m in re.finditer(r"scripts public for (\d+), (\d+) to follow", t):
            if int(m.group(1)) + int(m.group(2)) != len(studies):
                problems.append((p, m.group(0), "does not sum to study count"))
    assert not problems, problems


def test_sample_report_trader_count_consistent():
    t = text_of(pages()["/sample-report/"].text)
    counts = set(re.findall(r"([\d,]+) traders (?:in the same dataset )?with at least 30 sell-days", t))
    assert len(counts) <= 1, counts


def test_github_links_resolve():
    links = set()
    for p, r in pages().items():
        links |= {(p, h) for h in re.findall(r'href="(https://github\.com/[^"#]+)"', r.text)}
    broken = []
    seen = {}
    for p, h in sorted(links):
        if h not in seen:
            seen[h] = _get(h).status_code
        if seen[h] in (403, 429):
            continue  # blocked by a proxy or rate limit: not evidence either way
        if seen[h] != 200:
            broken.append((p, h, seen[h]))
    assert not broken, broken
