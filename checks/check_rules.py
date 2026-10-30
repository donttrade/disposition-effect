#!/usr/bin/env python3
"""check_rules.py — the firm-rules library (site/config/challenge_rules.json), ARCHITECT-CHALLENGE-READINESS §3.

  python3 checks/check_rules.py            # offline: schema, quotes that state each value, dates, links
  python3 checks/check_rules.py --online   # also fetch every source page: each quote under its rules heading

Every rule value is either backed by a quote or is the literal "not stated" (the firm's rules page does
not state it; the page says so and the check uses its default). A quote backs a value only when:
  * it names the section (a heading of the firm's rules page) it sits under, and that heading names a
    rule (RULE_SECTION), so a slogan or a call to action never counts;
  * the value itself, or for a yes/no kind of rule its key term, is inside the quote (support_terms);
  * online: the quote is on the page within SECTION_SPAN characters after that heading.
Presets last checked more than WARN_DAYS ago are warned about; more than HIDE_DAYS ago they are hidden.
A page answering with a bot check or an error is "open by hand", never a pass. Run monthly and before
any content push that names a firm. Firm names are plain-text descriptors; quotes are data, never copy.
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
SECTION_SPAN = 2500
NOT_STATED = "not stated"
RULE_FIELDS = ("target", "target_check", "daily_loss", "max_loss", "drawdown", "trail_stop_at", "consistency",
               "min_days_kind", "min_days", "count_day_if", "profitable_day_min", "time_limit", "day_start")
QUOTED_FIELDS = ("target", "target_check", "daily_loss", "max_loss", "drawdown", "trail_stop_at", "consistency",
                 "min_days", "count_day_if", "time_limit", "day_start")
REQUIRED = ("target", "max_loss")   # a usable preset always states these
STATUSES = ("complete", "partial", "not_quotable")
DRAWDOWNS = ("static", "trailing_eod", "trailing_trade")
TARGET_CHECKS = ("intraday", "end of day")
COUNT_DAY_IF = ("any trade", "non-zero P&L")
RULE_SECTION = re.compile(r"rule|objective|target|goal|loss|drawdown|consisten|parameter|trading day|minimum|limit|"
                          r"evaluation|step|phase|plan|server time|reset|lock|works|calculat|guideline|trigger", re.IGNORECASE)
TRACKING = re.compile(r"[?&#]|ref=|aff|utm_|coupon|promo|via=", re.IGNORECASE)
BOT_CHECK = re.compile(r"just a moment|attention required|cf-chl|captcha|access denied|verify you are human", re.IGNORECASE)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
BLOCK = re.compile(r"(?is)</?(p|div|li|ul|ol|br|tr|td|th|table|thead|tbody|h[1-6]|section|article|header|footer|"
                   r"main|nav|aside|dt|dd|dl|figure|figcaption|blockquote|hr|button|a)\b[^>]*>")
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
ZONE_TERMS = {"Europe/Prague": r"CE\(S\)T|\bCES?T\b", "America/Chicago": r"\bCT\b|Central", "America/New_York": r"\bE[SD]?T\b|Eastern|New York",
              "Etc/GMT-3": r"GMT ?\+ ?3", "Etc/GMT-2": r"GMT ?\+ ?2", "broker": r"server time|GMT ?\+ ?[23]", "UTC": r"\bUTC\b|\bGMT\b"}


def norm(s):
    """Text as compared: entities decoded, bidi isolates and zero-width marks dropped, whitespace collapsed."""
    s = html.unescape(s)
    s = re.sub(r"[⁦-⁩​-‏‪-‮﻿]", "", s)
    s = s.replace(" ", " ").replace("’", "'").replace("–", "-").replace("−", "-")
    return re.sub(r"\s+", " ", s).strip()


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


def quote_in_section(text, section, quote):
    """The quote occurs within SECTION_SPAN characters after an occurrence of its section heading."""
    q, h = norm(quote), norm(section)
    heads = [m.start() for m in re.finditer(re.escape(h), text)]
    for m in re.finditer(re.escape(q), text):
        if any(0 <= m.start() - x <= SECTION_SPAN for x in heads):
            return True
    return False


def _amounts(v):
    return [re.escape(f"${v:,.0f}"), re.escape(f"{v:,.0f}") + r"(?![\d.,])"]


def _pct(v, size):
    return re.escape(f"{v / size * 100:g}%")


def support_terms(field, value, p):
    """Regexes that must EACH match inside at least one quote backing this field (value or key term)."""
    size, pct = p.get("account_size"), p.get("scale") == "percent"
    if field in ("target", "daily_loss", "max_loss"):
        if value is None:
            return [r"\bnone\b|\bno\b|optional"]
        forms = _amounts(value) + ([_pct(value, size)] if pct else [])
        return ["|".join(forms)]
    if field == "target_check":
        return [{"intraday": r"\bonce\b|as soon as|the moment", "end of day": r"end of (the )?(trading )?day"}[value]]
    if field == "drawdown":
        return [{"static": r"static|remains at|unchanged", "trailing_eod": r"end[- ]of[- ]day|\bEOD\b",
                 "trailing_trade": r"closing trade|closed positions|real time|intraday"}[value]]
    if field == "trail_stop_at":
        return [r"highest|never decrease|only increase"] if value is None else [r"lock|no longer rise|stops once"]
    if field == "consistency":
        return [r"\bnone\b|\bno consistency"] if value is None else [re.escape(f"{value * 100:g}%")]
    if field == "min_days":
        if value == 0:
            return [r"no minimum|\bnone\b"]
        out = [rf"\b{value}\b" + (rf"|\b{WORDS[value]}\b" if value in WORDS else "")]
        if p["rules"]["min_days_kind"] == "profitable":
            out.append(_pct(p["rules"]["profitable_day_min"], size) if pct else "|".join(_amounts(p["rules"]["profitable_day_min"])))
        return out
    if field == "count_day_if":
        return [{"any trade": r"at least one (position|trade)", "non-zero P&L": r"non-zero"}[value]]
    if field == "time_limit":
        return [r"unlimited|no time limit|no deadline|no limit"] if value is None else [rf"\b{value}\b"]
    if field == "day_start":
        h = value["hour"]
        h12 = 12 if h % 12 == 0 else h % 12
        hour = r"\b0?0:00\b|midnight" if h == 0 else rf"\b{h}:00\b|\b{h12}(:00)? ?[AaPp]\.? ?[Mm]\b"
        return [hour, ZONE_TERMS.get(value["tz"], re.escape(value["tz"]))]
    raise KeyError(field)


def relevant(field, r):
    """Whether a field changes this preset's result (trail_stop_at under a static floor, how days count
    when there is no day minimum or the minimum counts profitable days, do not)."""
    if field == "trail_stop_at" and r["drawdown"] == "static":
        return False
    if field == "count_day_if" and (r["min_days"] in (0, NOT_STATED) or r["min_days_kind"] == "profitable"):
        return False
    return True


def not_stated(p):
    """The fields of a preset that change its result and that the firm's page does not state."""
    r = p.get("rules") or {}
    return [f for f in QUOTED_FIELDS if r.get(f) == NOT_STATED and relevant(f, r)]


def load(path=LIB):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def age_days(p, today):
    return (today - date.fromisoformat(p["last_checked"])).days


def _value_problems(pid, r):
    out = []
    ns = lambda f: r[f] == NOT_STATED  # noqa: E731
    for f in ("target", "max_loss"):
        if ns(f) or not (isinstance(r[f], (int, float)) and r[f] > 0):
            out.append(f"{pid}: {f} is an amount above zero")
    if not ns("daily_loss") and r["daily_loss"] is not None and not (isinstance(r["daily_loss"], (int, float)) and r["daily_loss"] > 0):
        out.append(f"{pid}: daily_loss")
    if not ns("target_check") and r["target_check"] not in TARGET_CHECKS:
        out.append(f"{pid}: target_check is one of {TARGET_CHECKS} or {NOT_STATED!r}")
    if not ns("drawdown") and r["drawdown"] not in DRAWDOWNS:
        out.append(f"{pid}: drawdown {r['drawdown']}")
    if ns("drawdown") and not ns("trail_stop_at"):
        out.append(f"{pid}: trail_stop_at cannot be stated when the drawdown kind is not")
    if r["drawdown"] == "static" and r["trail_stop_at"] is not None:
        out.append(f"{pid}: a static floor has no trail_stop_at")
    if not ns("trail_stop_at") and r["trail_stop_at"] is not None and not (isinstance(r["trail_stop_at"], (int, float)) and r["trail_stop_at"] >= 0):
        out.append(f"{pid}: trail_stop_at")
    if not ns("consistency") and r["consistency"] is not None and not (0 < r["consistency"] <= 1):
        out.append(f"{pid}: consistency")
    if r["min_days_kind"] not in ("trading", "profitable"):
        out.append(f"{pid}: min_days_kind")
    if not ns("min_days") and not (isinstance(r["min_days"], int) and 0 <= r["min_days"] <= 365):
        out.append(f"{pid}: min_days")
    if not ns("count_day_if") and r["count_day_if"] not in COUNT_DAY_IF:
        out.append(f"{pid}: count_day_if is one of {COUNT_DAY_IF} or {NOT_STATED!r}")
    if not (isinstance(r["profitable_day_min"], (int, float)) and r["profitable_day_min"] >= 0):
        out.append(f"{pid}: profitable_day_min")
    if not ns("time_limit") and r["time_limit"] is not None and not (isinstance(r["time_limit"], int) and 1 <= r["time_limit"] <= 365):
        out.append(f"{pid}: time_limit")
    ds = r["day_start"]
    if not ns("day_start") and not (isinstance(ds, dict) and isinstance(ds.get("hour"), int) and 0 <= ds["hour"] <= 23
                                    and isinstance(ds.get("tz"), str) and ds["tz"] != "file"):
        out.append(f"{pid}: day_start is {{tz, hour}} from the firm's text, or {NOT_STATED!r}")
    return out


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
        for k in ("id", "firm", "program", "status", "sources", "last_checked", "checked_by", "not_modelled"):
            if k not in p:
                out.append(f"{pid}: missing {k}")
        if p.get("status") not in STATUSES:
            out.append(f"{pid}: status {p.get('status')!r}")
            continue
        try:
            if date.fromisoformat(p["last_checked"]) > today:
                out.append(f"{pid}: last_checked {p['last_checked']} is in the future")
        except (KeyError, ValueError):
            out.append(f"{pid}: last_checked is not a date")
        srcs = p.get("sources") or []
        if not srcs:
            out.append(f"{pid}: no source")
        backing = {}
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
                if not q.get("section", "").strip():
                    out.append(f"{pid}: a quote without its section: {q.get('text', '')[:60]}")
                elif p["status"] != "not_quotable" and not RULE_SECTION.search(q["section"]):
                    out.append(f"{pid}: section {q['section']!r} is not a rules section")
                for fld in q.get("fields", []):
                    if fld not in QUOTED_FIELDS:
                        out.append(f"{pid}: quote names an unknown field {fld}")
                    backing.setdefault(fld, []).append(q["text"])
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
        out += _value_problems(pid, r)
        for fld in QUOTED_FIELDS:
            v = r[fld]
            if v == NOT_STATED:
                if fld in backing:
                    out.append(f"{pid}: {fld} is {NOT_STATED!r} but a quote backs it")
                if fld in REQUIRED:
                    out.append(f"{pid}: {fld} is required")
                continue
            if not relevant(fld, r) and fld not in backing:
                continue
            quotes = backing.get(fld, [])
            if not quotes:
                out.append(f"{pid}: {fld} = {v!r} has no quote (set it to {NOT_STATED!r} if the page does not state it)")
                continue
            try:
                terms = support_terms(fld, v, p)
            except (KeyError, TypeError):
                out.append(f"{pid}: {fld} = {v!r} is not a value the checker knows")
                continue
            for t in terms:
                if not any(re.search(t, norm(q), re.IGNORECASE) for q in quotes):
                    out.append(f"{pid}: no quote for {fld} states {v!r} (looked for /{t}/)")
        missing = not_stated(p)
        if (p["status"] == "complete") != (not missing):
            out.append(f"{pid}: status {p['status']} with {sorted(missing)} not stated")
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


def check_source(s, raw, status=200):
    """('ok' | 'quote missing' | 'open by hand', [quotes not found under their section])."""
    text = page_text(raw) if status == 200 else ""
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw or "")
    if status != 200 or BOT_CHECK.search((title.group(1) if title else "") + " " + text[:2000]):
        return "open by hand", []   # a bot check or an error is never a pass
    missing = [q["text"] for q in s["quotes"] if not quote_in_section(text, q["section"], q["text"])]
    return ("ok" if not missing else "quote missing"), missing


def online(lib):
    """[(preset id, url, verdict, missing quotes)]."""
    rows, cache = [], {}
    for p in lib["presets"]:
        for s in p["sources"]:
            if s["url"] not in cache:
                cache[s["url"]] = fetch(s["url"])
            status, raw = cache[s["url"]]
            verdict, missing = check_source(s, raw, status)
            rows.append((p["id"], s["url"], verdict, missing))
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
                print("               not under its section:", m[:120])
            bad = bad or verdict == "quote missing"
    print(f"rules_lib {lib['rules_lib']}: {len(lib['presets'])} entries, {len(shown(lib))} shown, "
          f"{'problems' if bad else 'no problems'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
