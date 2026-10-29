#!/usr/bin/env python3
"""check_rules.py — the firm-rules library (site/config/challenge_rules.json), ARCHITECT-CHALLENGE-READINESS §3.

  python3 checks/check_rules.py            # offline: schema, a quote for every value, dates, links
  python3 checks/check_rules.py --online   # also fetch every source page and look for every quote

Offline problems fail (exit 1); presets last checked more than WARN_DAYS ago are warned about, and
more than HIDE_DAYS ago are listed as hidden (the page leaves them out). Online: a page that answers
with a bot check or an error is reported as "open by hand", never as passed. Run it monthly and
before any content push that names a firm.

Firm names are plain-text descriptors only. Quotes are data, never page copy: the page shows the
numbers, the date read and a "rules page" link.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LIB = os.path.join(REPO, "site", "config", "challenge_rules.json")
WARN_DAYS = 30
HIDE_DAYS = 45
RULE_FIELDS = ("target", "daily_loss", "max_loss", "drawdown", "trail_stop_at", "consistency", "min_days_kind",
               "min_days", "profitable_day_min", "time_limit", "day_start")
QUOTED_FIELDS = ("target", "daily_loss", "max_loss", "drawdown", "trail_stop_at", "consistency", "min_days",
                 "time_limit", "day_start")
STATUSES = ("complete", "partial", "not_quotable")
DRAWDOWNS = ("static", "trailing_eod", "trailing_trade")
TRACKING = re.compile(r"[?&#]|ref=|aff|utm_|coupon|promo|via=", re.IGNORECASE)
BOT_CHECK = re.compile(r"just a moment|attention required|cf-chl|captcha|access denied|verify you are human", re.IGNORECASE)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def norm(s):
    """Text as compared: entities decoded, bidi isolates and zero-width marks dropped, whitespace collapsed."""
    s = html.unescape(s)
    s = re.sub(r"[⁦-⁩​-‏‪-‮﻿]", "", s)
    s = s.replace(" ", " ").replace("’", "'").replace("–", "-").replace("−", "-")
    return re.sub(r"\s+", " ", s).strip()


BLOCK = re.compile(r"(?is)</?(p|div|li|ul|ol|br|tr|td|th|table|thead|tbody|h[1-6]|section|article|header|footer|"
                   r"main|nav|aside|dt|dd|dl|figure|figcaption|blockquote|hr|button|a)\b[^>]*>")


def page_text(raw):
    """Visible text of an HTML page, plus the text inside script data (help centres render from JSON)."""
    body = re.sub(r"(?is)<(style|noscript|svg)\b.*?</\1>", " ", raw)
    scripts = " ".join(re.findall(r"(?is)<script\b[^>]*>(.*?)</script>", body))
    body = re.sub(r"(?is)<script\b.*?</script>", " ", body)
    body = re.sub(BLOCK, " ", body)
    body = re.sub(r"(?s)<[^>]+>", "", body)       # inline tags (<b>, <bdi>, <span>) join their text
    for _ in range(2):   # JSON inside JS strings is escaped once or twice
        scripts = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), scripts)
        scripts = re.sub(r"\\+[nrt]", " ", scripts).replace('\\"', '"').replace("\\\\", "\\")
    scripts = re.sub(BLOCK, " ", scripts)
    scripts = re.sub(r"(?s)<[^>]+>", "", scripts)
    return norm(body) + " \n " + norm(scripts)


def quote_found(text, quote):
    return norm(quote) in text


def load(path=LIB):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def age_days(p, today):
    return (today - date.fromisoformat(p["last_checked"])).days


def validate(lib, today=None):
    """Problems (a list of strings) with the library; empty when it is fit to ship."""
    today = today or date.today()
    out = []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.\d+", str(lib.get("rules_lib", ""))):
        out.append("rules_lib is missing or not 'yyyy-mm-dd.n'")
    presets = lib.get("presets", [])
    ids = [p.get("id") for p in presets]
    if len(set(ids)) != len(ids):
        out.append("duplicate preset ids")
    order = [(p.get("firm", "").lower(), p.get("program", "").lower()) for p in presets]
    if order != sorted(order):
        out.append("presets are not in alphabetical order (firm, then program)")
    for p in presets:
        pid = p.get("id", "?")
        for k in ("id", "firm", "program", "status", "sources", "last_checked", "checked_by", "not_modelled", "unconfirmed"):
            if k not in p:
                out.append(f"{pid}: missing {k}")
        if p.get("status") not in STATUSES:
            out.append(f"{pid}: status {p.get('status')!r}")
            continue
        try:
            lc = date.fromisoformat(p["last_checked"])
            if lc > today:
                out.append(f"{pid}: last_checked {lc} is in the future")
        except (KeyError, ValueError):
            out.append(f"{pid}: last_checked is not a date")
        srcs = p.get("sources") or []
        if not srcs:
            out.append(f"{pid}: no source")
        quoted = set()
        for s in srcs:
            for k in ("url", "read_on", "quotes"):
                if k not in s:
                    out.append(f"{pid}: a source lacks {k}")
            url = s.get("url", "")
            if not url.startswith("https://"):
                out.append(f"{pid}: source url is not https: {url}")
            if TRACKING.search(url.split("://", 1)[-1]):
                out.append(f"{pid}: source url carries a query, fragment or tracking part: {url}")
            try:
                if date.fromisoformat(s.get("read_on", "")) > today:
                    out.append(f"{pid}: read_on in the future")
            except ValueError:
                out.append(f"{pid}: read_on is not a date")
            for q in s.get("quotes", []):
                if not q.get("text", "").strip():
                    out.append(f"{pid}: an empty quote")
                for fld in q.get("fields", []):
                    if fld not in QUOTED_FIELDS:
                        out.append(f"{pid}: quote names an unknown field {fld}")
                    quoted.add(fld)
        if p["status"] == "not_quotable":
            if p.get("rules") is not None:
                out.append(f"{pid}: a not_quotable entry carries rules")
            if not p.get("reason"):
                out.append(f"{pid}: a not_quotable entry needs its reason")
            continue
        r = p.get("rules") or {}
        if set(r) != set(RULE_FIELDS):
            out.append(f"{pid}: rules keys {sorted(set(r) ^ set(RULE_FIELDS))} differ from {RULE_FIELDS}")
            continue
        if not (isinstance(p.get("account_size"), (int, float)) and p["account_size"] > 0):
            out.append(f"{pid}: account_size")
        if p.get("scale") not in ("percent", "fixed"):
            out.append(f"{pid}: scale is 'percent' or 'fixed'")
        if not (isinstance(r["target"], (int, float)) and r["target"] > 0 and r["max_loss"] > 0):
            out.append(f"{pid}: target and max_loss are amounts above zero")
        if r["daily_loss"] is not None and not r["daily_loss"] > 0:
            out.append(f"{pid}: daily_loss")
        if r["drawdown"] not in DRAWDOWNS:
            out.append(f"{pid}: drawdown {r['drawdown']}")
        if r["consistency"] is not None and not (0 < r["consistency"] <= 1):
            out.append(f"{pid}: consistency")
        if r["min_days_kind"] not in ("trading", "profitable"):
            out.append(f"{pid}: min_days_kind")
        if r["time_limit"] is not None and not (isinstance(r["time_limit"], int) and 1 <= r["time_limit"] <= 365):
            out.append(f"{pid}: time_limit")
        ds = r["day_start"]
        if ds is not None and not (isinstance(ds, dict) and isinstance(ds.get("hour"), int) and 0 <= ds["hour"] <= 23
                                   and isinstance(ds.get("tz"), str)):
            out.append(f"{pid}: day_start")
        unconf = set(p["unconfirmed"])
        for fld in QUOTED_FIELDS:
            if fld == "trail_stop_at" and r["drawdown"] == "static" and r["trail_stop_at"] is None:
                continue   # no trailing floor, nothing to stop
            if fld not in quoted and fld not in unconf:
                out.append(f"{pid}: {fld} has no quote and is not listed as unconfirmed")
            if fld in quoted and fld in unconf:
                out.append(f"{pid}: {fld} is both quoted and unconfirmed")
        if (p["status"] == "complete") != (not unconf):
            out.append(f"{pid}: status {p['status']} with unconfirmed {sorted(unconf)}")
    return out


def freshness(lib, today=None):
    """(warn, hidden): preset ids last checked more than WARN_DAYS / HIDE_DAYS ago."""
    today = today or date.today()
    warn = [p["id"] for p in lib["presets"] if WARN_DAYS < age_days(p, today) <= HIDE_DAYS]
    hidden = [p["id"] for p in lib["presets"] if age_days(p, today) > HIDE_DAYS]
    return warn, hidden


def shown(lib, today=None):
    """The presets a page may offer: quotable and checked within HIDE_DAYS."""
    today = today or date.today()
    return [p for p in lib["presets"] if p["status"] != "not_quotable" and age_days(p, today) <= HIDE_DAYS]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError) as e:
        return None, str(e)


def online(lib):
    """[(preset id, url, verdict, missing quotes)] where verdict is 'ok', 'quote missing' or 'open by hand'."""
    rows = []
    cache = {}
    for p in lib["presets"]:
        for s in p["sources"]:
            url = s["url"]
            if url not in cache:
                cache[url] = fetch(url)
            status, raw = cache[url]
            text = page_text(raw) if status == 200 else ""
            title = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw or "")
            if status != 200 or BOT_CHECK.search((title.group(1) if title else "") + " " + text[:2000]):
                rows.append((p["id"], url, "open by hand", []))   # a bot check or an error is never a pass
                continue
            missing = [q["text"] for q in s["quotes"] if not quote_found(text, q["text"])]
            rows.append((p["id"], url, "ok" if not missing else "quote missing", missing))
    return rows


def main(argv):
    lib = load()
    probs = validate(lib)
    for x in probs:
        print("FAIL", x)
    warn, hidden = freshness(lib)
    for x in warn:
        print(f"WARN {x}: last checked more than {WARN_DAYS} days ago")
    for x in hidden:
        print(f"HIDDEN {x}: last checked more than {HIDE_DAYS} days ago, left out of the page")
    bad = bool(probs)
    if "--online" in argv:
        for pid, url, verdict, missing in online(lib):
            print(f"{verdict.upper():14} {pid} {url}")
            for m in missing:
                print("               missing:", m[:120])
            bad = bad or verdict == "quote missing"
    print(f"rules_lib {lib['rules_lib']}: {len(lib['presets'])} entries, {len(shown(lib))} shown, "
          f"{'problems' if bad else 'no problems'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
