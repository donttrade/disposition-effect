"""Random IBKR-style histories for the carried-position property tests (Tester F-B1, F-D2).

A history is a list of true fills on a netting account, with O / C / C;O codes, and the
true flat-to-flat trades it makes. An export that starts at `cut` holds only the fills at
or after `cut`, so it can begin in the middle of a position. The engine must never report
a trade that is not one of the true trades that open at or after `cut`.
"""
import random

HDR = ("CurrencyPrimary,AssetClass,Symbol,DateTime,Quantity,TradePrice,Buy/Sell,"
       "Open/CloseIndicator,Notes/Codes,IBCommission,FifoPnlRealized,LevelOfDetail\n")
T0 = 1788256800  # 2026-09-01 10:00:00 as naive UTC seconds


def _ts_text(sec):
    import datetime
    d = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=sec)
    return d.strftime("%Y%m%d;%H%M%S")


def history(seed, n_symbols=2, n_trades=6, ties=False, reversals=False):
    """-> (fills, trades). fills: dicts in true order. trades: (symbol, dir, open_s, close_s, peak).
    Each fill carries `trade`, the index in trades of the trade it opens or adds to or closes."""
    rng = random.Random(seed)
    fills = []
    trades = []
    for si in range(n_symbols):
        sym = "S%d" % si
        t = T0 + rng.randint(0, 600)
        pos = 0
        cur = None  # [dir, open_s, peak]

        def step():
            nonlocal t
            t += 0 if (ties and rng.random() < 0.3) else rng.randint(1, 4000)
            return t

        for _ in range(n_trades):
            if pos == 0:
                d = rng.choice([1, -1])
                q = 10 * rng.randint(1, 5)
                ts = step()
                fills.append(dict(ts=ts, sym=sym, side=d, qty=q, code="O", trade=len(trades)))
                pos = d * q
                cur = ["long" if d > 0 else "short", ts, q]
            # a few adds and partial closes, never crossing zero
            for _ in range(rng.randint(0, 3)):
                d = 1 if pos > 0 else -1
                ts = step()
                if rng.random() < 0.5:
                    q = 10 * rng.randint(1, 3)
                    fills.append(dict(ts=ts, sym=sym, side=d, qty=q, code="O", trade=len(trades)))
                    pos += d * q
                    cur[2] = max(cur[2], abs(pos))
                elif abs(pos) > 10:
                    q = 10 * rng.randint(1, abs(pos) // 10 - 1)
                    fills.append(dict(ts=ts, sym=sym, side=-d, qty=q, code="C", trade=len(trades)))
                    pos -= d * q
            d = 1 if pos > 0 else -1
            ts = step()
            if reversals and rng.random() < 0.4:
                extra = 10 * rng.randint(1, 4)
                fills.append(dict(ts=ts, sym=sym, side=-d, qty=abs(pos) + extra, code="C;O", trade=len(trades)))
                trades.append((sym, cur[0], cur[1], ts, cur[2]))
                pos = -d * extra
                cur = ["long" if -d > 0 else "short", ts, extra]
            else:
                fills.append(dict(ts=ts, sym=sym, side=-d, qty=abs(pos), code="C", trade=len(trades)))
                trades.append((sym, cur[0], cur[1], ts, cur[2]))
                pos = 0
                cur = None
        if pos != 0:  # close the last one so the history ends flat
            d = 1 if pos > 0 else -1
            ts = step()
            fills.append(dict(ts=ts, sym=sym, side=-d, qty=abs(pos), code="C", trade=len(trades)))
            trades.append((sym, cur[0], cur[1], ts, cur[2]))
    order = sorted(range(len(fills)), key=lambda k: (fills[k]["ts"], k))
    return [fills[k] for k in order], trades


def export(fills, cut):
    """The CSV an export starting at `cut` (seconds) would hold."""
    lines = []
    for f in fills:
        if f["ts"] < cut:
            continue
        side = "BUY" if f["side"] > 0 else "SELL"
        qty = f["qty"] if f["side"] > 0 else -f["qty"]
        lines.append("USD,STK,%s,%s,%d,100,%s,%s,%s,-1,,EXECUTION" % (
            f["sym"], _ts_text(f["ts"]), qty, side, f["code"], f["code"]))
    return (HDR + "\n".join(lines) + "\n").encode()


def visible(fills, trades, cut):
    """False when the export starting at `cut` hides a lot of unknown size by the engine's
    stated convention: the position open across `cut` (or one a reversal opened from it,
    whose size the file cannot give either) is added to in the file and then closed by a
    reversal fill (C;O). The file's own counts then never contradict "this was all opened
    in the file", so no reader of the file alone can see the older lot (the report lists
    this limit). Every other cut must give only true trades."""
    for i, (s, d, o, c, q) in enumerate(trades):
        if not (o < cut <= c):
            continue
        j = i
        while True:
            mine = [f for f in fills if f.get("trade") == j and f["ts"] >= cut]
            closer = [f for f in mine if f["ts"] == trades[j][3] and f["code"] == "C;O"]
            if not closer:
                break  # closed by a plain C: the file shows the unknown lot's end
            if any(f["code"] == "O" for f in mine):
                return False
            j += 1  # the reversal opened trade j + 1, of unknown size too
            if j >= len(trades) or trades[j][0] != s:
                break
    return True


def window_truth(trades, cut):
    """The true trades an export starting at `cut` may report (they open inside it)."""
    return {(s, d, o * 1000, c * 1000, float(q)) for s, d, o, c, q in trades if o >= cut}


def engine_keys(result):
    return {(t["symbol"], t["dir"], t["open_ts"], t["close_ts"], float(t["qty"])) for t in result["trades"]}
