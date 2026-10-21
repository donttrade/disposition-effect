"""Quote-mark mutations of small valid CSV files (Tester F-B2): shared by the Python fuzz
test and the browser parity check."""
import random

HEAD = ["Date", "Time", "Symbol", "Side", "Quantity", "Price", "Notes"]


def _rows():
    out = []
    for i in range(40):
        d = "2026-01-%02d" % (5 + i // 20)
        m = (i % 20) * 2
        sym = "AAA" if i % 2 else "BBB"
        out.append([d, "10:%02d:00" % m, sym, "Buy", "1", "100", "note %d, ok" % i])
        out.append([d, "10:%02d:00" % (m + 1), sym, "Sell", "1", "101", ""])
    return out


def bases():
    """name -> text: every field quoted (comma and ';'), and quoted notes only."""
    q = lambda cells, sep=",": sep.join('"%s"' % c for c in cells)  # noqa: E731
    rows = _rows()
    return {
        "allquoted": q(HEAD) + "\n" + "\n".join(q(r) for r in rows) + "\n",
        "allquoted_semicolon": q(HEAD, ";") + "\n" + "\n".join(q([c.replace(",", "") for c in r], ";") for r in rows) + "\n",
        "notes_quoted": ",".join(HEAD) + "\n" + "\n".join(",".join(r[:6]) + ',"' + r[6] + '"' for r in rows) + "\n",
    }


def mutations(text, seed, n_random=400):
    """One quote inserted at every position, each quote deleted, and n_random pairs inserted."""
    for pos in range(len(text) + 1):
        yield "ins%d" % pos, text[:pos] + '"' + text[pos:]
    for pos, ch in enumerate(text):
        if ch == '"':
            yield "del%d" % pos, text[:pos] + text[pos + 1:]
    rng = random.Random(seed)
    for _ in range(n_random):
        a, b = sorted(rng.sample(range(len(text)), 2))
        yield "pair%d_%d" % (a, b), text[:a] + '"' + text[a:b] + '"' + text[b:]
