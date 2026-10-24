#!/usr/bin/env python3
"""WCAG 2.1 contrast check for every token pair the design system uses, both themes.

Reads the tokens straight from site/static/css/site.css:
  light = the first `:root {` block; dark = `:root[data-theme="dark"]`, which must
  equal the prefers-color-scheme block. Text pairs need >= 4.5:1, UI pairs >= 3:1.
Also fails if the light rust #9A3B1C appears in a dark token block or in any --band-* token.
The dark hero band's tokens (--band-*, all three blocks) are measured as BAND_PAIRS.
Exit code 0 = pass. Prints one line per pair.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "..", "site", "static", "css", "site.css")

# (foreground, background, minimum, why)
PAIRS = [
    ("text", "bg", 4.5, "body text"), ("text", "surface", 4.5, "text on panels"),
    ("muted", "bg", 4.5, "muted text"), ("muted", "surface", 4.5, "muted on panels / footer"),
    ("rust", "bg", 4.5, "links"), ("rust", "surface", 4.5, "links on panels"),
    ("rust-hover", "bg", 4.5, "hovered links"),
    ("on-rust", "rust", 4.5, "primary button text"), ("on-rust", "rust-hover", 4.5, "hovered button"),
    ("rust-hover", "surface", 4.5, "secondary button hover"),
    ("gain", "bg", 4.5, "gain numbers"), ("gain", "surface", 4.5, "gain on panels"),
    ("loss", "bg", 4.5, "loss numbers / errors"), ("loss", "surface", 4.5, "loss on panels"),
    ("caution", "bg", 4.5, "caution badge"), ("caution", "surface", 4.5, "caution on panels"),
    ("plan", "bg", 4.5, "plan line labels"), ("plan", "surface", 4.5, "plan on panels"),
    ("field-border", "bg", 3.0, "form control borders"), ("field-border", "surface", 3.0, "controls on panels"),
    ("rust", "bg", 3.0, "focus ring"), ("rust", "surface", 3.0, "focus ring on panels"),
]

# The dark hero band (ARCHITECT-BRAND-AND-WRAPPED §2.2). The band re-scopes --bg, --text, --rust, ...
# to these, so every component inside it is measured here: every foreground on both band
# backgrounds (the band itself and the cards inside it), in both themes.
BAND_BGS = ("band-bg", "band-surface")
BAND_TEXT = (("band-text", "band text"), ("band-muted", "muted text in the band"),
             ("band-rust", "links, focus ring, key numbers in the band"), ("band-rust-hover", "hovered links in the band"),
             ("band-gain", "gains in the band"), ("band-loss", "losses in the band"), ("band-plan", "plan lines in the band"),
             ("band-caution", "sample-data marker in the band"))
BAND_PAIRS = ([(fg, bg, 4.5, why) for fg, why in BAND_TEXT for bg in BAND_BGS]
              + [("band-field-border", bg, 3.0, "drop box and input borders in the band") for bg in BAND_BGS]
              + [("band-on-rust", "band-rust", 4.5, "button text in the band"),
                 ("band-on-rust", "band-rust-hover", 4.5, "hovered button in the band")])
BAND_TOKENS = sorted({t for p in BAND_PAIRS for t in p[:2]} | {"band-border"})


def blocks(css):
    light = re.search(r"(?s):root\s*\{(.*?)\}", css).group(1)
    media = re.search(r'(?s)@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{(.*?)\}',
                      css).group(1)
    dark = re.search(r'(?s):root\[data-theme="dark"\]\s*\{(.*?)\}', css).group(1)
    return light, media, dark


def tokens(block):
    return {k: v.upper() for k, v in re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", block)}


def lum(hexv):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def main():
    css = open(CSS, encoding="utf-8").read()
    light, media, dark = blocks(css)
    themes = {"light": tokens(light), "dark": {**tokens(light), **tokens(dark)}}
    failures = []
    if tokens(media) != tokens(dark):
        failures.append("the prefers-color-scheme dark block differs from :root[data-theme=dark]")
    if "#9A3B1C" in tokens(dark).values() or "#9A3B1C" in tokens(media).values():
        failures.append("#9A3B1C (light rust) used in a dark theme block")
    for name, block in (("light", light), ("dark (media)", media), ("dark (toggle)", dark)):
        t = tokens(block)
        missing = [k for k in BAND_TOKENS if k not in t]
        if missing:
            failures.append(f"{name} block lacks band token(s): {', '.join(missing)}")
        if any(v == "#9A3B1C" for k, v in t.items() if k.startswith("band-")):
            failures.append(f"#9A3B1C (light rust) used in a --band-* token ({name} block): 2.55:1 on charcoal")
    for theme, t in themes.items():
        for fg, bg, need, why in PAIRS + BAND_PAIRS:
            r = ratio(t[fg], t[bg])
            ok = r >= need
            print(f"{'PASS' if ok else 'FAIL'}  {theme:5}  {fg:13} on {bg:10} {r:5.2f}:1 (need {need}) {why}")
            if not ok:
                failures.append(f"{theme} {fg} on {bg} = {r:.2f}:1 < {need}")
    for f in failures:
        print("FAIL ", f)
    print("contrast.py:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
