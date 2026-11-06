"""The /tools/ real-data displays (Direction B2, "Instrument panel"): geometry for the templates, made at build time.

site/config/tool_real.json (checks/real_data/make_tool_real.py) holds the figures; this module only turns them into
SVG coordinates, so every drawing on /tools/ and in the tool-page headers is to scale and nothing is typed by hand.
The markup lives in templates/partials/tool_display.html and tool_glyphs.html. Pure functions: no I/O but load().
Ported from the approved mockup's generator (tools-redesign/_tools/mk_b2.py and icons_real.py)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_REAL_JSON = os.path.join(HERE, "config", "tool_real.json")
TOOL_REAL_REPORT_JSON = os.path.join(HERE, "config", "tool_real.report.json")


def load():
    with open(TOOL_REAL_JSON, encoding="utf-8") as f:
        return json.load(f)


def money(v):
    v = round(v, 2)
    return ("−$" if v < 0 else "+$" if v > 0 else "$") + f"{abs(v):,.2f}"


def _f(v, dp=1):
    s = f"{v:.{dp}f}"
    return "0" if s in ("-0", "-0.0") else (s[:-2] if dp == 1 and s.endswith(".0") else s)


def _pts(xy, dp=1):
    return " ".join(f"{_f(x, dp)},{_f(y, dp)}" for x, y in xy)


def curve_geom(vals, x0, x1, y0, y1, pad=0.06, dp=1):
    lo, hi = min(vals + [0]), max(vals + [0])
    sp = hi - lo
    lo, hi = lo - sp * pad, hi + sp * pad
    n = len(vals)
    X = lambda i: x0 + (x1 - x0) * i / (n - 1)
    Y = lambda v: y1 - (v - lo) / (hi - lo) * (y1 - y0)
    peaks, p = [], 0.0
    for v in vals:
        p = max(p, v)
        peaks.append(p)
    eq = [(X(i), Y(v)) for i, v in enumerate(vals)]
    pk = [(X(i), Y(v)) for i, v in enumerate(peaks)]
    return {"eq": _pts(eq, dp), "peak": _pts(pk, dp), "gap": _pts(pk + eq[::-1], dp), "X": X, "Y": Y, "lo": lo, "hi": hi}


def heat_class(level):
    """The tool's own level() (±1…±4, None for an empty cell) as a class."""
    if level is None:
        return "h0"
    return ("hp" if level > 0 else "hn") + str(abs(level))


def _heat_rank(rows):
    cells = [(r, c, l) for r, row in enumerate(rows) for c, l in enumerate(row["levels"]) if l is not None]
    order = sorted(cells, key=lambda x: -abs(x[2]))   # stable: largest first, then reading order
    return {(r, c): i for i, (r, c, _) in enumerate(order)}


# ------------------------------------------------------------------ the one equity curve, drawn once per page
def eq_symbol(D):
    """The closed-trade equity, its running high and the gap between them, once, as an SVG <symbol> in whole units
    (10 a trade across, 0-1000 down, relative steps). The scope, the stats sparkline and the drawdown screen <use> it
    at their own sizes (preserveAspectRatio none, non-scaling strokes), so the page carries the curve once."""
    c = D["curve"]
    lo, hi = min(c + [0]), max(c + [0])
    ys = [round((hi - v) / (hi - lo) * 1000) for v in c]
    peaks, p = [], 0.0
    for v in c:
        p = max(p, v)
        peaks.append(p)
    ps = [round((hi - v) / (hi - lo) * 1000) for v in peaks]
    rel = lambda a: "".join(f"l10 {y - x}" for x, y in zip(a, a[1:]))
    back = "".join(f"l-10 {y - x}" for x, y in zip(ys[::-1], ys[::-1][1:]))
    w = 10 * (len(c) - 1)
    return {"w": w, "eq": f"M0 {ys[0]}" + rel(ys), "peak": f"M0 {ps[0]}" + rel(ps),
            "gap": f"M0 {ps[0]}" + rel(ps) + f"L{w} {ys[-1]}" + back + "Z", "lo": lo, "hi": hi}


def _place(D, Y, x0, x1):
    """Where the symbol sits in a drawing whose value-to-y map is Y: x, y, width, height."""
    lo, hi = min(D["curve"] + [0]), max(D["curve"] + [0])
    return {"x": _f(x0), "y": _f(Y(hi)), "w": _f(x1 - x0), "h": _f(Y(lo) - Y(hi))}


# ------------------------------------------------------------------ the hero scope (the 64 closed trades)
def scope(D):
    c = D["curve"]
    W, H, x0, x1, y0, y1 = 640, 300, 64, 616, 26, 246
    g = curve_geom(c, x0, x1, y0, y1)
    t, pk = D["curve_trough_trade"] - 1, D["curve_peak_trade"] - 1
    tx, ty = g["X"](t), g["Y"](c[t])
    peaks, p = [], 0.0
    for v in c:
        p = max(p, v)
        peaks.append(p)
    ticks = [{"y": _f(g["Y"](v) + 4), "label": "$0" if v == 0 else f"−{abs(v) // 1000:,.0f}k"} for v in (0, -10000, -20000, -30000)]
    return {
        "W": W, "H": H, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "xmid": _f((x0 + x1) / 2), "yax": H - 24,
        "hgrid": [_f(y0 + (y1 - y0) * i / 5) for i in range(6)], "vgrid": [_f(x0 + (x1 - x0) * i / 8) for i in range(9)],
        "ticks": ticks, "zero_y": _f(g["Y"](0)), "use": _place(D, g["Y"], x0, x1),
        "tx": _f(tx), "ty": _f(ty), "fut_w": _f(x1 - tx), "n": len(c),
        "data_curve": ",".join(f"{v:.2f}" for v in c), "data_months": ",".join(D["curve_close_month"]),
        "lo": f"{g['lo']:.2f}", "hi": f"{g['hi']:.2f}",
        "read": {"n": t + 1, "month": D["curve_close_month"][t], "eq": money(c[t]), "dd": money(c[t] - peaks[t])},
        "peak_trade": pk + 1, "trough_trade": t + 1,
        "label": (f"Closed-trade equity of one anonymous investor from a public dataset, {len(c)} trades closed from "
                  f"{D['account']['period']}. It peaks at {money(D['curve_high'])} at trade {pk + 1}, "
                  f"falls to {money(c[t])} at trade {t + 1}, a drawdown of {D['trade_stats']['largest_drawdown']}, and ends "
                  f"at {D['trade_stats']['net']}."),
    }


# ------------------------------------------------------------------ the screens
def spark(D, w=300, h=44):
    g = curve_geom(D["curve"], 2, w - 2, 3, h - 3, pad=0)
    return {"w": w, "h": h, "use": _place(D, g["Y"], 2, w - 2)}


def trade_bars(D):
    c = D["curve"]
    pnl = [c[0]] + [c[i] - c[i - 1] for i in range(1, len(c))]
    top = max(abs(v) for v in pnl)
    w, mid = 10, 26   # one bar per 10 units: viewBox width 10 x trades, stretched (preserveAspectRatio none)
    # one path per colour: each bar is "M x y h8 v h h-8 z"
    d = {"g": [], "l": []}
    for i, v in enumerate(pnl):
        h = max(.8, abs(v) / top * 24)
        d["g" if v > 0 else "l"].append(f"M{i * w + 1} {_f(mid - h if v > 0 else mid)}h{w - 2}v{_f(h)}h-{w - 2}z")
    return {"mid": mid, "gain": "".join(d["g"]), "loss": "".join(d["l"]), "n": len(pnl), "W": w * len(pnl)}


def fan(D):
    F, R = D["fan"], D["readiness"]
    days = len(F["p50"]) - 1
    W, H, x0, x1, y0, y1 = 10 * days, 142, 0, 10 * days, 10, 122   # 10 units a day; the last 20 units hold the day axis
    lo, hi = -R["max_loss"] * 1.25, R["target"] * 1.15
    X = lambda d: x0 + (x1 - x0) * d / days
    Y = lambda v: y1 - (v - lo) / (hi - lo) * (y1 - y0)

    def pl(vals):   # a path in whole units, relative steps (it compresses well); the start is always day 0
        ys = [round(Y(max(v, lo))) for v in vals[:days + 1]]
        return f"M0 {ys[0]}l" + " ".join(f"10 {b - a}" for a, b in zip(ys, ys[1:]))   # implicit lineto
    ro = R["real_order_path"]
    real = _pts([(X(0), Y(0))] + [(X(i + 1), Y(max(v, lo))) for i, v in enumerate(ro)])
    bx, by = X(len(ro)), Y(max(ro[-1], lo))
    return {"W": W, "H": H, "x0": x0, "x1": x1, "ty": _f(Y(R["target"]), 0), "fy": _f(Y(-R["max_loss"]), 0),
            "ty_lab": _f(Y(R["target"]) - 3, 0), "fy_lab": _f(Y(-R["max_loss"]) + 10, 0), "x_lab": x0 + 4,
            # a replay is coloured by its outcome only when it ends inside the window drawn; one still running at
            # the last day drawn (it ended later, up to the 250-day cap) is grey (Tester F5)
            "paths": [{"cls": o if e <= days else "open", "pts": pl(p)} for p, o, e in zip(F["paths"], F["outcomes"], F["end_days"])],
            "ax_y": H - 2,
            "p5": pl(F["p5"]), "p50": pl(F["p50"]), "p95": pl(F["p95"]), "real": real,
            "x": f"M{_f(bx - 3.5)} {_f(by - 3.5)}l7 7M{_f(bx + 3.5)} {_f(by - 3.5)}l-7 7", "days": days,
            "target": f"+${R['target']:,.0f}"}


def heat(D):
    rows = D["heatmap"]["rows"]
    cell, gap, ox, oy = 22, 3, 44, 12
    rank = _heat_rank(rows)
    out = {"w": ox + 5 * cell + 4 * gap, "h": oy + len(rows) * cell + (len(rows) - 1) * gap, "cell": cell,
           "cols": [{"x": _f(ox + c * (cell + gap) + cell / 2), "l": l[0]} for c, l in enumerate(D["heatmap"]["cols"])],
           "rows": [], "cells": []}
    for r, row in enumerate(rows):
        y = oy + r * (cell + gap)
        out["rows"].append({"y": _f(y + cell / 2 + 3), "l": row["hour"][:5]})
        for c, l in enumerate(row["levels"]):
            d = f" hc d{min(7, rank[(r, c)] // 3)}" if (r, c) in rank else ""
            out["cells"].append({"cls": heat_class(l) + d, "x": ox + c * (cell + gap), "y": y})
    return out


def dd(D, w=300, h=84):
    g = curve_geom(D["curve"], 3, w - 3, 6, h - 6, pad=0)
    return {"w": w, "h": h, "use": _place(D, g["Y"], 3, w - 3)}


def lot(D):
    fx = D["eurusd"]
    ser, lo, hi = fx["series"], fx["low"], fx["high"]
    w, h = 240, 46
    X = lambda i: 2 + (w - 4) * i / (len(ser) - 1)
    Y = lambda v: 4 + (hi - v) / (hi - lo) * (h - 8)
    return {"w": w, "h": h, "pts": _pts([(X(i), Y(v)) for i, v in enumerate(ser)]), "ghosts": [i * 36 for i in range(5)],
            "low": f"{lo:.4f}", "high": f"{hi:.4f}"}


def rr():
    """The break-even win rate 1 ÷ (1 + R) for R from 0.5 to 5: a property of the formula, not an example."""
    w, h, x0, x1, y0, y1 = 240, 70, 18, 236, 4, 58
    X = lambda r: x0 + (x1 - x0) * (r - 0.5) / 4.5
    Y = lambda p: y1 - (p - 0.15) / (0.70 - 0.15) * (y1 - y0)
    R = [0.5 + i * 0.05 for i in range(91)]
    ticks = []
    for r in (1, 2, 3, 4, 5):
        ticks.append({"x": _f(X(r)), "cy": _f(Y(1 / (1 + r))), "r": f"{r}R", "ly": _f(Y(1 / (1 + r)) - (13 if r == 4 else 5)),
                      "lx": _f(X(r) + (4 if r == 1 else 0)), "anchor": "end" if r == 5 else "start" if r == 1 else "middle",
                      "pct": f"{100 / (1 + r):.1f}%"})
    return {"w": w, "h": h + 4, "y1": y1, "y1t": y1 + 3, "ty": y1 + 11, "pts": _pts([(X(r), Y(1 / (1 + r))) for r in R]),
            "ticks": ticks}


def disp(D):
    O = D["odean"]
    L = 228 / 0.16
    g, l = O["pgr_f"], O["plr_f"]
    cg, cl = O["ci_pgr"], O["ci_plr"]
    return {"gw": _f(g * L), "lw": _f(l * L), "gbx": _f(cg[0] * L), "gbw": _f(max(1.2, (cg[1] - cg[0]) * L)),
            "lbx": _f(cl[0] * L), "lbw": _f(max(1.2, (cl[1] - cl[0]) * L)),
            "gpct": f"{g * 100:.2f}%", "lpct": f"{l * 100:.2f}%",
            "gband": f"{cg[0] * 100:.2f}–{cg[1] * 100:.2f}%", "lband": f"{cl[0] * 100:.2f}–{cl[1] * 100:.2f}%"}


# ------------------------------------------------------------------ the eight glyphs (48-unit grid)
def glyphs(D):
    s = D["slices"]
    top, base = max(abs(v) for v in s), 18
    stats = []
    for i, v in enumerate(s):
        h = max(1.2, abs(v) / top * 24 if v < 0 else abs(v) / top * 14)
        stats.append({"up": v >= 0, "x": _f(5.5 + i * 4.8), "y": _f(base - h if v >= 0 else base), "h": _f(h), "d": i})
    rows = D["heatmap"]["rows"]
    rank = _heat_rank(rows)
    heat_cells = [{"cls": heat_class(l) + (f" a-fade d{min(8, rank[(r, c)] // 3)}" if (r, c) in rank else ""),
                   "x": _f(8 + c * 6.6), "y": _f(2.5 + r * 6.3)} for r, row in enumerate(rows) for c, l in enumerate(row["levels"])]
    c = D["curve"]
    lo, hi = min(c + [0]), max(c + [0])
    X = lambda i: 4 + 40 * i / (len(c) - 1)
    Y = lambda v: 40 - (v - lo) / (hi - lo) * 32
    peaks, p = [], 0.0
    for v in c:
        p = max(p, v)
        peaks.append(p)
    eq = [(X(i), Y(v)) for i, v in enumerate(c)]
    t = D["curve_trough_trade"] - 1
    dd_ = {"high_y": _f(Y(max(c))), "gap": _pts([(X(i), Y(v)) for i, v in enumerate(peaks)] + eq[::-1]), "eq": _pts(eq),
           "tx": _f(X(t)), "ty": _f(Y(c[t]))}
    R = D["readiness"]
    path = R["real_order_path"]
    n = len(path)
    PX = lambda i: 6 + 38 * (i + 1) / n
    PY = lambda v: 24 - v / R["target"] * 16
    prop = {"ty": _f(PY(R["target"])), "fy": _f(PY(-R["max_loss"])),
            "pts": "6,24 " + _pts([(PX(i), PY(max(v, -R["max_loss"]))) for i, v in enumerate(path)])}
    bx, by = PX(n - 1), PY(-R["max_loss"])
    prop["x"] = f"M{_f(bx - 2.4)} {_f(by - 2.4)}l4.8 4.8M{_f(bx + 2.4)} {_f(by - 2.4)}l-4.8 4.8"
    rr_pts = _pts([(6 + 36 * (r - 0.5) / 4.5, 40 - (1 / (1 + r) - 0.15) / 0.55 * 30) for r in [0.5 + i * 0.25 for i in range(19)]])
    g, l = D["odean"]["pgr_f"], D["odean"]["plr_f"]
    L = 36 / max(g, l)
    return {"stats": {"base": base, "bars": stats}, "heat": heat_cells, "dd": dd_, "prop": prop, "rr": rr_pts,
            "disp": {"g": _f(g * L), "l": _f(l * L)}}


def view(D):
    return {"eq": eq_symbol(D), "scope": scope(D), "spark": spark(D), "bars": trade_bars(D), "fan": fan(D), "heat": heat(D), "dd": dd(D),
            "lot": lot(D), "rr": rr(), "disp": disp(D), "glyph": glyphs(D)}
