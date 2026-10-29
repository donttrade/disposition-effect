"""Batch P1: partner/prediction_test.py, the firm-run script.

  * the no-network guarantee (plan section 4.3): the import allowlist (AST walk over the script and its three
    sibling modules), exactly three open() calls at run time, all mode "r", identical output with
    socket.socket replaced by a raising stub, and under `unshare -rn` when the kernel allows it;
  * the AUDIT MAP names the right lines;
  * refusals never echo a cell (canary strings), and the output never contains an identifier or symbol;
  * determinism, and the README's byte-exact expected output on the fixture;
  * the verdict table of section 2.12, top-down;
  * DT-1 parity: the script uses the very dt1_features module the golden file checks."""
import ast
import builtins
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
PARTNER = os.path.join(REPO, "partner")
sys.path.insert(0, PARTNER)
import dt1_features  # noqa: E402
import make_fixture_prediction as G  # noqa: E402
import prediction_test as P  # noqa: E402

SCRIPT = os.path.join(PARTNER, "prediction_test.py")
EXAMPLE = os.path.join(PARTNER, "PREREG-PREDICTION-EXAMPLE.md")
README = os.path.join(PARTNER, "README-PREDICTION.md")
MODULES = ("prediction_test.py", "dt1_features.py", "dt1_outcomes.py", "prediction_metrics.py")
STDLIB_ALLOWED = {"argparse", "csv", "datetime", "decimal", "math", "re", "sys", "unicodedata", "hashlib", "random",
                  "bisect"}
SIBLINGS = {"dt1_features", "dt1_outcomes", "prediction_metrics"}
FORBIDDEN_BUILTINS = {"eval", "exec", "__import__", "compile", "breakpoint", "input", "print", "globals", "vars"}


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("fx"))
    G.write(d, "L", 600, 7)
    return d


def run_cli(args, env_extra=None, prefix=()):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8"}
    r = subprocess.run(list(prefix) + [sys.executable, "-I", SCRIPT] + list(args), capture_output=True, text=True,
                       env=env)
    return r.returncode, r.stdout, r.stderr


def fx_args(d, prereg=EXAMPLE):
    return [os.path.join(d, "trades.csv"), os.path.join(d, "accounts.csv"), prereg]


# ------------------------------------------------------------------ no network

def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    return tree, names


@pytest.mark.parametrize("name", MODULES)
def test_import_allowlist(name):
    tree, names = _imports(os.path.join(PARTNER, name))
    allowed = STDLIB_ALLOWED | (SIBLINGS if name == "prediction_test.py" else set())
    assert names <= allowed, names - allowed
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not (used & FORBIDDEN_BUILTINS), used & FORBIDDEN_BUILTINS


def test_script_imports_exactly_the_audited_list():
    _tree, names = _imports(SCRIPT)
    assert names == {"argparse", "csv", "datetime", "decimal", "hashlib", "math", "random", "re", "sys",
                     "unicodedata"} | SIBLINGS


@pytest.mark.parametrize("name", MODULES)
def test_open_only_in_the_script_and_read_only(name):
    tree, _ = _imports(os.path.join(PARTNER, name))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "open"]
    if name != "prediction_test.py":
        assert calls == []
        return
    assert len(calls) == 2           # one for the pre-registration, one for each CSV (run twice)
    for c in calls:
        assert isinstance(c.args[1], ast.Constant) and c.args[1].value == "r"
    src = open(SCRIPT, encoding="utf-8").read()
    assert ".write(" not in src.replace("sys.stdout.write(", "").replace("sys.stderr.write(", "")


def test_three_opens_at_run_time_all_read_only(fixture_dir, monkeypatch):
    seen = []
    real = builtins.open

    def spy(file, mode="r", *a, **k):
        seen.append((os.path.basename(str(file)), mode))
        return real(file, mode, *a, **k)
    monkeypatch.setattr(builtins, "open", spy)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert P.run(fx_args(fixture_dir)) == 0
    assert seen == [("PREREG-PREDICTION-EXAMPLE.md", "r"), ("accounts.csv", "r"), ("trades.csv", "r")]


def test_identical_output_with_sockets_disabled(fixture_dir):
    code = ("import socket, sys, runpy\n"
            "class Boom(Exception): pass\n"
            "def no(*a, **k): raise Boom('network used')\n"
            "socket.socket = no; socket.create_connection = no; socket.getaddrinfo = no\n"
            "sys.argv = [%r] + %r\n"
            "runpy.run_path(%r, run_name='__main__')\n" % (SCRIPT, fx_args(fixture_dir), SCRIPT))
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    rc, plain, _ = run_cli(fx_args(fixture_dir))
    assert rc == 0 and r.stdout == plain and "network used" not in r.stderr


def _unshare_ok():
    if not shutil.which("unshare"):
        return False
    return subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _unshare_ok(), reason="unshare -rn is not permitted here")
def test_identical_output_with_no_network_namespace(fixture_dir):
    rc1, a, _ = run_cli(fx_args(fixture_dir))
    rc2, b, _ = run_cli(fx_args(fixture_dir), prefix=("unshare", "-rn"))
    assert rc1 == rc2 == 0 and a == b


def test_audit_map_line_numbers():
    lines = open(SCRIPT, encoding="utf-8").read().splitlines()
    head = "\n".join(lines[:60])

    imp = re.search(r"lines (\d+)-(\d+) \(standard library\) and (\d+)-(\d+)", head).groups()
    a, b, c, d = map(int, imp)
    assert all(lines[i - 1].startswith(("import ", "from ")) for i in range(a, b + 1))
    assert all(lines[i - 1].startswith("import ") for i in range(c, d + 1))
    assert "sys.path.insert" in lines[int(re.search(r"search path on line (\d+)", head).group(1)) - 1]
    opens = re.search(r"line (\d+) \(the pre-registration\) and line (\d+)", head).groups()
    assert all("open(" in lines[int(n) - 1] for n in opens)
    so = re.search(r"stdout \.\.\. lines (\d+) and (\d+).*?line (\d+) only", head, re.S).groups()
    assert "sys.stdout.write(" in lines[int(so[0]) - 1] and "sys.stdout.flush()" in lines[int(so[1]) - 1]
    assert "sys.stdout = None" in lines[int(so[2]) - 1]
    se = re.search(r"stderr \.\.\. lines (\d+), (\d+) and (\d+)", head).groups()
    assert all("sys.stderr.write(" in lines[int(n) - 1] for n in se)
    ce = re.search(r"catch-all \.+ line (\d+)", head).group(1)
    assert "except Exception" in lines[int(ce) - 1]
    src = "\n".join(lines)
    assert src.count("sys.stdout.write(") == 1 and src.count("sys.stderr.write(") == 3


# ------------------------------------------------------------------ output content

def test_output_has_no_identifier_or_symbol(fixture_dir):
    rc, out, _ = run_cli(fx_args(fixture_dir))
    assert rc == 0
    with open(os.path.join(fixture_dir, "accounts.csv"), encoding="utf-8") as fh:
        ids = [ln.split(",")[0] for ln in fh.read().splitlines()[1:]]
    for i in ids:
        assert i not in out
    for sym in ("EURUSD", "GBPUSD", "XAUUSD", "NAS100", "US30", "USDJPY"):
        assert sym not in out
    assert not re.search(r"20\d\d-\d\d-\d\dT", out)


def test_deterministic_and_json_twin(fixture_dir):
    _, a, _ = run_cli(fx_args(fixture_dir))
    _, b, _ = run_cli(fx_args(fixture_dir))
    assert a == b
    rc, j, _ = run_cli(["--json"] + fx_args(fixture_dir))
    doc = json.loads(j)
    assert rc == 0 and doc["verdict"] in a and ("%.3f" % doc["h1"]["auc"]) in a
    assert doc["reconciliation"]["read"] == 600


def _readme_block(name):
    text = open(README, encoding="utf-8").read()
    m = re.search(r"<!-- BEGIN %s -->\n```text\n(.*?)```\n<!-- END %s -->" % (name, name), text, re.S)
    return m.group(1)


def test_readme_expected_output_byte_for_byte(fixture_dir):
    _, out, _ = run_cli(fx_args(fixture_dir))
    assert out == _readme_block("EXPECTED OUTPUT")


def test_readme_fixture_hashes(fixture_dir):
    block = _readme_block("FIXTURE SHA-256")
    for name in ("trades.csv", "accounts.csv"):
        h = hashlib.sha256(open(os.path.join(fixture_dir, name), "rb").read()).hexdigest()
        assert "%s  %s" % (h, name) in block


def test_rule_mode_runs(fixture_dir, tmp_path):
    text = open(EXAMPLE, encoding="utf-8").read().replace('outcome_mode = "firm"', 'outcome_mode = "rule"')
    p = tmp_path / "rule.md"
    p.write_text(text, encoding="utf-8")
    rc, out, err = run_cli(fx_args(fixture_dir, str(p)))
    assert rc == 0, err
    assert "Outcome mode: rule" in out and "VERDICT:" in out and "O3 " not in out


# ------------------------------------------------------------------ refusals

CANARY = "CANARYc4f1"


def _variant(fixture_dir, tmp_path, trades_fn=None, accounts_fn=None, prereg_fn=None):
    t = open(os.path.join(fixture_dir, "trades.csv"), encoding="utf-8").read().splitlines()
    a = open(os.path.join(fixture_dir, "accounts.csv"), encoding="utf-8").read().splitlines()
    p = open(EXAMPLE, encoding="utf-8").read()
    if trades_fn:
        t = trades_fn(t)
    if accounts_fn:
        a = accounts_fn(a)
    if prereg_fn:
        p = prereg_fn(p)
    tp, ap, pp = tmp_path / "trades.csv", tmp_path / "accounts.csv", tmp_path / "prereg.md"
    tp.write_bytes(("\n".join(t) + "\n").encode("utf-8", "surrogateescape") if isinstance(t, list) else t)
    ap.write_text("\n".join(a) + "\n", encoding="utf-8")
    pp.write_text(p, encoding="utf-8")
    return [str(tp), str(ap), str(pp)]


def _cell(lines, row, col, value):
    f = lines[row].split(",")
    f[col] = value
    lines[row] = ",".join(f)
    return lines


REFUSALS = {
    "bad direction": dict(trades_fn=lambda t: _cell(t, 5, 4, CANARY)),
    "bad time": dict(trades_fn=lambda t: _cell(t, 6, 1, "2026-13-01T00:00" + CANARY)),
    "bad pnl": dict(trades_fn=lambda t: _cell(t, 7, 6, "1e5" + CANARY)),
    "unknown column": dict(trades_fn=lambda t: [t[0] + "," + CANARY] + [x + ",1" for x in t[1:]]),
    "invisible id": dict(trades_fn=lambda t: _cell(t, 8, 0, CANARY + "​")),
    "unknown account": dict(trades_fn=lambda t: _cell(t, 9, 0, CANARY)),
    "close before open": dict(trades_fn=lambda t: _cell(t, 10, 2, "2026-01-01T00:00:00+02:00")),
    "duplicate trade": dict(trades_fn=lambda t: t + [t[11]]),
    "ragged row": dict(trades_fn=lambda t: t + [CANARY + ",x"]),
    "nul byte": dict(trades_fn=lambda t: t[:3] + [CANARY + "\0"] + t[3:]),
    "bad utf8": dict(trades_fn=lambda t: t[:3] + [CANARY + "\udcff"] + t[3:]),
    "outcome word": dict(accounts_fn=lambda a: _cell(a, 3, 7, CANARY)),
    "period count": dict(prereg_fn=lambda p: p.replace("accounts_in_period = 600", "accounts_in_period = 601")),
    "fill in": dict(prereg_fn=lambda p: p.replace('registration = "EXAMPLE: synthetic fixture, not a registration"',
                                                  'registration = "OSF FILL_IN"')),
    "frozen constant": dict(prereg_fn=lambda p: p.replace("window_trades = 30", "window_trades = 20")),
    "unknown sealed key": dict(prereg_fn=lambda p: p.replace("cv_folds = 10", "cv_folds = 10\n%s = 1" % CANARY)),
    "start outside period": dict(accounts_fn=lambda a: _cell(a, 4, 1, "2025-12-01T00:00:00+02:00")),
}


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_refusal_never_echoes_a_cell(name, fixture_dir, tmp_path):
    args = _variant(fixture_dir, tmp_path, **REFUSALS[name])
    rc, out, err = run_cli(args)
    assert rc == 1, (name, err)
    assert out == ""
    assert err.startswith("ERROR: ") and err.count("\n") == 1
    assert CANARY not in err and "​" not in err
    if name not in ("period count", "fill in", "frozen constant", "unknown sealed key", "unknown column"):
        assert re.search(r"row \d+", err), err


# ------------------------------------------------------------------ verdicts (section 2.12)

PARAMS = {"min_each": "100", "fail_point": "0.55", "fail_upper": "0.60", "pass_lower": "0.55", "target": "0.65"}


def _v(auc, lo, hi, h2=True, n=(200, 200)):
    rec = {"breaches": n[0], "survivors": n[1]}
    res = {"h1": {"auc": auc, "lo": lo, "hi": hi}, "h2": {"passed": h2}}
    return P.verdict(PARAMS, rec, res)


def test_verdict_table_top_down():
    assert _v(0.70, 0.66, 0.74, n=(99, 300)) == "NOT MEASURED"
    assert P.verdict(PARAMS, {"breaches": 300, "survivors": 300}, None) == "NOT MEASURED"
    assert _v(0.54, 0.50, 0.62) == "FAIL: does not predict usefully"
    assert _v(0.57, 0.55, 0.595) == "FAIL: does not predict usefully"     # the useful range is ruled out
    assert _v(0.58, 0.565, 0.595) == "FAIL: does not predict usefully"    # rule 2 wins over rule 3
    assert _v(0.62, 0.57, 0.67, h2=False) == "FAIL: adds nothing"
    assert _v(0.66, 0.61, 0.71) == "PASS: meets target"
    assert _v(0.65, 0.60, 0.70) == "PASS: meets target"
    assert _v(0.61, 0.56, 0.66) == "PASS: below target"
    assert _v(0.58, 0.53, 0.63) == "INCONCLUSIVE"
    assert _v(0.60, 0.55, 0.65) == "INCONCLUSIVE"                         # the lower bound must be ABOVE 0.55


def test_script_uses_the_golden_checked_feature_module():
    assert P.F is dt1_features
