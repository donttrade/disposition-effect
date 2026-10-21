#!/usr/bin/env python3
"""Accessibility harness: axe-core (vendored, pinned 4.10.2, MPL-2.0) run in Chromium.

Why vendored axe: it is the only automated WCAG checker that runs offline.
Dev-only: checks/vendor/axe.min.js is never copied into the site.

    python3 checks/a11y.py URL [URL ...]     # both themes, prints serious/critical issues

Library use: from a11y import axe_violations, horizontal_overflow
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AXE = os.path.join(HERE, "vendor", "axe.min.js")


def axe_violations(page, impacts=("serious", "critical")):
    """Inject axe into the page (bypassing the page CSP via add_script_tag content) and run it."""
    with open(AXE, encoding="utf-8") as f:
        src = f.read()
    page.add_script_tag(content=src)
    res = page.evaluate("async () => (await axe.run(document, {resultTypes: ['violations']})).violations"
                        ".map(v => ({id: v.id, impact: v.impact, help: v.help,"
                        " nodes: v.nodes.map(n => n.target.join(' ')).slice(0, 5)}))")
    return [v for v in res if v["impact"] in impacts]


def horizontal_overflow(page):
    """Elements wider than the viewport (the page itself scrolling sideways)."""
    return page.evaluate("""() => {
        const w = document.documentElement.clientWidth;
        if (document.documentElement.scrollWidth <= w) return [];
        return [...document.querySelectorAll('body *')].filter(e => {
            const r = e.getBoundingClientRect(); return r.right > w + 1 && getComputedStyle(e).position !== 'fixed';
        }).slice(0, 10).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className ? '.' + String(e.className).split(' ')[0] : ''));
    }""")


def main(urls):
    from playwright.sync_api import sync_playwright
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = b.new_context(color_scheme=scheme, bypass_csp=True)
            page = ctx.new_page()
            for u in urls:
                page.goto(u)
                v = axe_violations(page)
                bad += len(v)
                print(f"{scheme:5} {u}: {len(v)} serious/critical")
                for x in v:
                    print("   ", json.dumps(x))
            ctx.close()
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
