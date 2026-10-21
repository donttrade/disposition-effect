#!/usr/bin/env python3
"""compare.py — plan steps 28–29: old vs new for every lifted page.

    python3 checks/compare.py [site/_site]     # 0 differences, or each one named

For each page in checks/lifted-baseline/ (written by lift_pages.py from the pre-v2 docs/ page,
with the documented LIFT_FIXES applied), the built page's frozen body (between
<!--frozen:start--> and <!--frozen:end-->) must have, exactly:
  * the same visible text: every text node outside <script>/<style>, in order, byte for byte
    (and so the same numbers, footnotes, citations and table cells);
  * the same alt / title / aria-label / placeholder / value texts (chart descriptions);
  * the same ids, in order (every in-page anchor still resolves);
  * the same href / src / action targets, in order (PDF, CSV, chart and study links intact);
  * the same tables, cell by cell;
and the page head the same citation_* meta, in order.
"""
import glob
import html as _h
import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BASE_DIR = os.path.join(HERE, "lifted-baseline")
FROZEN_RE = re.compile(r"(?s)<!--frozen:start-->(.*)<!--frozen:end-->")
READ_ATTRS = ("alt", "title", "aria-label", "placeholder", "value")
LINK_ATTRS = ("href", "src", "action", "data")


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.attrs, self.ids, self.links, self.tables = [], [], [], [], []
        self._skip = None
        self._cell = None
        self._stack = []   # open tables: list of rows

    def handle_starttag(self, tag, attrs):
        a = dict((k.lower(), v or "") for k, v in attrs)
        for k in READ_ATTRS:
            if k in a:
                self.attrs.append(f"{tag}[{k}]={a[k]}")
        if "id" in a:
            self.ids.append(a["id"])
        for k in LINK_ATTRS:
            if k in a:
                self.links.append(f"{tag}[{k}]={a[k]}")
        if tag in ("script", "style"):
            self._skip = tag
        elif tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            self._cell = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self._skip and tag == self._skip:
            self._skip = None
        elif tag in ("td", "th") and self._cell is not None and self._stack:
            if not self._stack[-1]:
                self._stack[-1].append([])
            self._stack[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def facts(fragment, citation=None):
    p = _P()
    p.feed(fragment)
    p.close()
    text = "".join(p.text)
    return {"text": text, "text_collapsed": " ".join(text.split()), "attrs": p.attrs, "ids": p.ids,
            "links": p.links, "tables": p.tables, "citation": citation or []}


def frozen_of(html):
    """The frozen body of a built page, or None. Exactly one region is allowed."""
    if html.count("<!--frozen:start-->") != 1 or html.count("<!--frozen:end-->") != 1:
        return None
    return FROZEN_RE.search(html).group(1)


def citation_of(html):
    head = html[:html.find("</head>")]
    return [[_h.unescape(n), _h.unescape(c)] for n, c in
            re.findall(r'<meta name="(citation_[a-z_]+)" content="([^"]*)"', head)]


def baselines():
    out = {}
    for fp in sorted(glob.glob(os.path.join(BASE_DIR, "*.json"))):
        with open(fp, encoding="utf-8") as f:
            b = json.load(f)
        out[b["path"]] = b
    return out


def _first_diff(a, b):
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return f"at {n}: old …{a[max(0, n - 60):n + 60]!r}… new …{b[max(0, n - 60):n + 60]!r}…"


def diff_page(base, html):
    """[(what, detail)] — empty when the built page matches its baseline."""
    body = frozen_of(html)
    if body is None:
        return [("frozen", "no single <!--frozen:start-->…<!--frozen:end--> region")]
    new = facts(body, citation_of(html))
    out = []
    if new["text"] != base["text"]:
        out.append(("text", _first_diff(base["text"], new["text"])))
    for k in ("attrs", "ids", "links", "tables", "citation"):
        if new[k] != base[k]:
            old_k, new_k = base[k], new[k]
            if isinstance(old_k, list) and isinstance(new_k, list):
                n = next((i for i, (x, y) in enumerate(zip(old_k, new_k)) if x != y), min(len(old_k), len(new_k)))
                out.append((k, f"item {n}: old {old_k[n] if n < len(old_k) else '∅'!r} new {new_k[n] if n < len(new_k) else '∅'!r}"))
            else:
                out.append((k, "differs"))
    return out


def out_file(site, path):
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return os.path.join(site, rel)


def compare_site(site):
    problems = []
    for path, base in baselines().items():
        fp = out_file(site, path)
        if not os.path.exists(fp):
            problems.append((path, "missing", "page not in the build"))
            continue
        with open(fp, encoding="utf-8") as f:
            for what, detail in diff_page(base, f.read()):
                problems.append((path, what, detail))
    return problems


def main(argv):
    site = argv[0] if argv else os.path.join(REPO, "site", "_site")
    problems = compare_site(site)
    for path, what, detail in problems:
        print(f"COMPARE {path} {what}: {detail}")
    n = len(baselines())
    print(f"compare: {n} lifted pages, " + ("0 differences" if not problems else f"{len(problems)} difference(s)"))
    return 1 if problems or not n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
