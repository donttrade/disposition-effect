#!/usr/bin/env python3
"""donttrade v2 site build: site.toml + prices.json + Jinja2 templates → site/_site/.

Rules (V2-BUILD-PLAN, STRUCTURE and step 3):
  * Every page of today's docs/ that no template owns yet is copied through
    unchanged, so the output always holds every baseline URL.
  * The build FAILS LOUDLY (exit 1, with the reason) on:
      - a path in checks/urls-baseline.txt missing from the output,
      - an externally linked id (path#id in the baseline) missing from its page,
      - trader_first_home != paid_report, or analytics on without a beacon token,
      - a paid-only page or paid-flagged markup in the output while paid_report is off,
      - a placeholder left in private.toml when paid_report is on
        (unless DT_ALLOW_PLACEHOLDERS=1, for local test builds only).
  * Output is deterministic: sorted walks, no timestamps, so two builds are byte-identical.

Environment:
  DT_DEV=1                 also build site/dev/ (styleguide, sniffer) into _site/dev/
  DT_SITE_TOML=path        use another site.toml (test builds with flags on)
  DT_OUT=path              write somewhere other than site/_site
  DT_ALLOW_PLACEHOLDERS=1  allow private.toml placeholders (local test mode only)
  DT_BASELINE=path         use another URL baseline (tests plant a missing URL this way)
  DT_PRIVATE_TOML=path     read private.toml from elsewhere (flag-on test builds)
"""

import json
import os
import re
import shutil
import sys
import tomllib

from jinja2 import Environment, FileSystemLoader, StrictUndefined

SITE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SITE)
DOCS = os.path.join(REPO, "docs")
BASELINE = os.environ.get("DT_BASELINE") or os.path.join(REPO, "checks", "urls-baseline.txt")

PAID_FLAG_MARKER = 'data-requires-flag="paid_report"'
PLACEHOLDER_RE = re.compile(r"\[[A-Z ]+ — [^\]]+\]")

# Pages owned by templates. path → template, metadata, and the flag that must be on.
PAGES = [
    {"template": "pages/home.html", "path": "/", "requires_flag": None,
     "title": "donttrade — behavioural measurement for trading firms",
     "description": "We measure the plan gap: how traders plan to act versus how they act. Fixed price, "
                    "public script, run on your own systems."},
]

# Free tools (steps 10-12). connect-src stays 'none' (the csp_for default): these pages
# cannot send anything, which is what makes "your file is not uploaded" true.
PAGES += [
    {"template": "pages/tool-trade-stats.html", "path": "/tools/trade-stats/", "requires_flag": None,
     "modules": ["/static/js/tools/trade-stats.js"], "sample": True,
     "title": "Free MT5 Report Analyzer: Trade Stats From Your File",
     "description": "Drop your MT5, MT4, IBKR or Tradovate file and get profit factor, expectancy, drawdown and "
                    "streaks, with a real-or-noise check. Runs in your browser."},
    {"template": "pages/tool-prop-sim.html", "path": "/tools/prop-challenge-simulator/", "requires_flag": None,
     "modules": ["/static/js/tools/prop-sim.js"], "sample": True,
     "title": "Prop Firm Challenge Simulator on Your Own Trades",
     "description": "Replay 10,000 challenges built from your own past trading days under the rules you enter. "
                    "Pass, bust and time-out shares, fully explained. Free."},
]

SAMPLE_CSV = os.path.join(SITE, "static", "samples", "demo-trades.csv")


def sample_csv():
    """The synthetic demo file, inlined into the page inside <script type="text/csv">.

    Inlined rather than fetched because the page's CSP is connect-src 'none'. The build
    refuses anything that could end the script element early."""
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        text = f.read()
    if "<" in text or "&" in text:
        die("demo-trades.csv contains '<' or '&'; it cannot be inlined safely")
    return text


PAID_PAGES = [
    {"template": "pages/welcome.html", "path": "/welcome/", "requires_flag": "paid_report", "connect_worker": True,
     "modules": ["/static/js/paid/welcome.js"], "title": "Thank you — donttrade",
     "description": "Your donttrade habit report is ready."},
    {"template": "pages/restore.html", "path": "/restore/", "requires_flag": "paid_report", "connect_worker": True,
     "modules": ["/static/js/paid/restore.js"], "title": "Restore access — donttrade",
     "description": "Reopen your donttrade habit report on this browser."},
    {"template": "pages/report.html", "path": "/report/", "requires_flag": "paid_report", "connect_worker": True,
     "modules": ["/static/js/paid/report.js"], "title": "Your habit report — donttrade",
     "description": "Your donttrade habit report, built from your own trade file."},
]
PAGES += PAID_PAGES
# Flag-on /pricing/: Traders | Firms tabs. Its firm and shared sections are lifted
# word for word from today's live page (see lift_sections), so with the flag off the
# old page passes through untouched.
PAGES.append({"template": "pages/pricing_paid.html", "path": "/pricing/", "requires_flag": "paid_report",
              "scripts": ["/static/js/tabs.js", "/static/js/print.js"], "title": "Pricing — donttrade",
              "description": "Published prices in USD. Every price on this site comes from one list."})

# Paths that may exist only when paid_report = true.
PAID_ONLY_PATHS = ["/welcome/", "/restore/", "/report/"]


class BuildError(Exception):
    pass


def die(msg):
    raise BuildError(msg)


def load_config():
    toml_path = os.environ.get("DT_SITE_TOML") or os.path.join(SITE, "config", "site.toml")
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    with open(os.path.join(SITE, "config", "prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    flags = cfg["flags"]
    if flags["trader_first_home"] != flags["paid_report"]:
        die(f"flag mismatch: trader_first_home={flags['trader_first_home']} must equal "
            f"paid_report={flags['paid_report']} ({toml_path})")
    if flags["analytics"] and not cfg["analytics"]["cf_beacon_token"]:
        die("analytics = true but [analytics] cf_beacon_token is empty")
    private = {}
    if flags["paid_report"]:
        p = os.environ.get("DT_PRIVATE_TOML") or os.path.join(SITE, "config", "private.toml")
        if not os.path.exists(p):
            die("paid_report = true needs site/config/private.toml (copy private.example.toml)")
        with open(p, "rb") as f:
            private = tomllib.load(f)
        for k in ("seller_legal_name", "premises_address", "phone"):
            if k not in private:
                die(f"private.toml is missing {k}")
            if PLACEHOLDER_RE.search(private[k]) and os.environ.get("DT_ALLOW_PLACEHOLDERS") != "1":
                die(f"private.toml {k} still holds a placeholder; fill it in "
                    "(or set DT_ALLOW_PLACEHOLDERS=1 for a local test build only)")
    if flags["paid_report"]:
        mode = cfg["stripe"]["mode"]
        if mode not in ("test", "live"):
            die(f"[stripe] mode must be test or live, not {mode!r}")
        for p in prices["products"]:
            if p["requires_flag"] == "paid_report" and p["id"] == "report39":
                if not p["stripe_link_" + mode] and os.environ.get("DT_ALLOW_PLACEHOLDERS") != "1":
                    die(f"paid_report = true but prices.json has no stripe_link_{mode} for report39")
    return cfg, prices, private


def lift_sections(rel_path):
    """{id: html} for each <h2 id=...> section of an old docs/ page's <main>, verbatim.

    A section runs from its <h2 id> to the next <h2 id> (or the end of <main>). Key
    "_intro" holds what comes before the first one."""
    with open(os.path.join(DOCS, rel_path), encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"(?s)<main[^>]*>(.*)</main>", html)
    if not m:
        die(f"lift: no <main> in docs/{rel_path}")
    main = m.group(1)
    cuts = [(mm.start(), mm.group(1)) for mm in re.finditer(r'<h2[^>]*\sid="([^"]+)"', main)]
    out = {"_intro": main[: cuts[0][0]] if cuts else main}
    for k, (start, sid) in enumerate(cuts):
        end = cuts[k + 1][0] if k + 1 < len(cuts) else len(main)
        out[sid] = main[start:end]
    return out


def usd(n):
    """$745, $2,500 — prices are whole dollars on this site."""
    if n != int(n):
        die(f"price {n} is not a whole number of dollars")
    return "${:,}".format(int(n))


def csp_for(page, cfg):
    connect = page.get("connect_src", "'none'")
    if page.get("connect_worker"):
        connect = "'self' " + cfg["worker"]["api_base"]
    if cfg["flags"]["analytics"]:
        connect += " https://cloudflareinsights.com"
    script = "'self'" + (" https://static.cloudflareinsights.com" if cfg["flags"]["analytics"] else "")
    return ("default-src 'self'; script-src " + script + "; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; connect-src " + connect + "; worker-src 'self'; "
            "form-action 'self' https://api.web3forms.com; base-uri 'none'; object-src 'none'")


def out_file(out, path):
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return os.path.join(out, rel)


def copy_tree_sorted(src, dst, skip=None):
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for name in sorted(files):
            s = os.path.join(root, name)
            rel = os.path.relpath(s, src)
            if skip and skip(rel):
                continue
            d = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d)  # content only: no timestamps carried over


def read_baseline():
    paths, ids = [], []
    with open(BASELINE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "#" in line:
                ids.append(tuple(line.split("#", 1)))
            else:
                paths.append(line)
    return paths, ids


def verify(out, flags):
    paths, ids = read_baseline()
    for p in paths:
        if not os.path.exists(out_file(out, p) if p.endswith("/") else os.path.join(out, p.lstrip("/"))):
            die(f"baseline URL missing from the build: {p}")
    for p, i in ids:
        with open(out_file(out, p), encoding="utf-8") as f:
            html = f.read()
        if not re.search(r'\sid="' + re.escape(i) + '"', html):
            die(f"externally linked id missing: {p}#{i}")
    if not flags["paid_report"]:
        for p in PAID_ONLY_PATHS:
            if os.path.exists(out_file(out, p)):
                die(f"paid-only page {p} is in the build while paid_report = false")
        for root, _, files in os.walk(out):
            for name in files:
                if name.endswith(".html"):
                    fp = os.path.join(root, name)
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        if PAID_FLAG_MARKER in f.read():
                            die(f"paid-flagged markup in {os.path.relpath(fp, out)} while paid_report = false")


def build():
    cfg, prices, private = load_config()
    flags = cfg["flags"]
    out = os.environ.get("DT_OUT") or os.path.join(SITE, "_site")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)

    owned = {}
    for page in PAGES:
        if page["requires_flag"] and not flags[page["requires_flag"]]:
            continue
        owned[os.path.relpath(out_file(out, page["path"]), out)] = page

    # 1. passthrough of every docs/ file a template does not own yet
    copy_tree_sorted(DOCS, out, skip=lambda rel: rel in owned)
    # 2. static assets of the new design
    copy_tree_sorted(os.path.join(SITE, "static"), os.path.join(out, "static"),
                     skip=(None if flags["paid_report"] else (lambda rel: rel.startswith("js" + os.sep + "paid"))))
    # 3. dev pages, only on request; never bundled
    if os.environ.get("DT_DEV") == "1":
        copy_tree_sorted(os.path.join(SITE, "dev"), os.path.join(out, "dev"))

    env = Environment(loader=FileSystemLoader(os.path.join(SITE, "templates")), undefined=StrictUndefined,
                      autoescape=True, keep_trailing_newline=True)
    env.filters["usd"] = usd
    products = {p["id"]: p for p in prices["products"]}
    base_ctx = {"site": cfg["site"], "flags": flags, "nav": cfg["nav"], "footer": cfg["footer"],
                "legal": cfg["legal"], "forms": cfg["forms"], "analytics": cfg["analytics"],
                "worker": cfg["worker"], "prices": prices, "products": products, "private": private,
                "stripe_mode": cfg["stripe"]["mode"], "lift": lift_sections}
    for rel, page in sorted(owned.items()):
        page = {"scripts": [], "modules": [], "og_image": "/assets/og/default.png", **page}
        extra = {"sample_csv": sample_csv()} if page.get("sample") else {}
        html = env.get_template(page["template"]).render(page=page, csp=csp_for(page, cfg), **base_ctx, **extra)
        fp = os.path.join(out, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)

    verify(out, flags)
    return out


def main():
    try:
        out = build()
    except BuildError as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        return 1
    print(f"built {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
