from __future__ import annotations
# Join the AS-TRADED price (px_f4, from Form 4 TRANS_PRICEPERSHARE) onto the
# existing events file without refetching anything. events.csv.gz is left
# untouched: it is the provenance of the published figures.
import sys
import numpy as np
import pandas as pd

ev = pd.read_csv("f4/events.csv.gz")
cl = pd.read_csv("f4/clusters.csv.gz")
if "px_f4" not in cl.columns:
    sys.exit("merge_px.py: f4/clusters.csv.gz has no px_f4 column; re-run build.py then clusters.py")
n0 = len(ev)
print("events rows:", n0, " clusters rows:", len(cl))

# Key hygiene: both sides are read as the same string type and stripped.
for fr in (ev, cl):
    fr["tic"] = fr["tic"].astype(str)
    fr["sig"] = pd.to_datetime(fr["sig"]).dt.strftime("%Y-%m-%d")

# ASSERT 1: (tic, sig) unique in clusters, restricted to the keys present in events.
keys = ev[["tic", "sig"]].drop_duplicates()
clr = cl.merge(keys, on=["tic", "sig"], how="inner")
dup = clr.duplicated(["tic", "sig"], keep=False)
if dup.any():
    print(clr[dup].sort_values(["tic", "sig"]).head(20).to_string())
    sys.exit("FATAL: (tic, sig) is NOT unique in clusters for %d rows; merging would fan out events." % int(dup.sum()))
if ev.duplicated(["tic", "sig"]).any():
    sys.exit("FATAL: (tic, sig) is not unique in events.")
print("assert ok: (tic, sig) unique in clusters (restricted to event keys) and in events")

m = ev.merge(cl[["tic", "sig", "px_f4"]].drop_duplicates(["tic", "sig"]), on=["tic", "sig"], how="left", validate="one_to_one")

# ASSERT 2: no row gained or lost.
if len(m) != n0:
    sys.exit("FATAL: row count changed by merge: %d -> %d" % (n0, len(m)))
print("assert ok: row count unchanged (%d)" % n0)

# Diagnostics: print, do not threshold.
matched_key = ev.merge(cl[["tic", "sig"]].assign(_hit=1), on=["tic", "sig"], how="left")["_hit"].notna()
unmatched = int((~matched_key.values).sum())
nopx = int(m.px_f4.isna().sum())
print("\nkey match: %d of %d events (%.2f%%); UNMATCHED keys: %d" % (n0 - unmatched, n0, 100.0 * (n0 - unmatched) / n0, unmatched))
print("px_f4 non-null: %d of %d (%.2f%%); px_f4 NaN: %d (unmatched + matched-with-NaN price)" % (n0 - nopx, n0, 100.0 * (n0 - nopx) / n0, nopx))
if unmatched:
    print("sample of unmatched keys:")
    print(ev.loc[~matched_key.values, ["tic", "sig"]].head(15).to_string(index=False))
if (m.px_f4.dropna() <= 0).any() or np.isinf(m.px_f4.dropna()).any():
    sys.exit("FATAL: px_f4 contains non-positive or inf values")

m.to_csv("f4/events_px.csv.gz", index=False)
print("\nwrote f4/events_px.csv.gz", m.shape)

# Misclassification table: old screen px>=5 (yfinance adjusted close) vs px_f4>=5 (as traded).
yr = pd.to_datetime(m.sig).dt.year
era = np.where(yr <= 2016, "<=2016", ">=2017")
old = (m.px >= 5)
new = (m.px_f4 >= 5)
known = m.px_f4.notna()
print("\n=== screen px>=5 comparison (dollar-volume floor NOT applied here; px screens only) ===")
print("%-10s %8s %10s %10s %12s %12s %10s" % ("era", "events", "old pass", "new pass", "old&~new", "~old&new", "px_f4 NaN"))
for lbl, mask in (("ALL", np.ones(len(m), bool)), ("<=2016", era == "<=2016"), (">=2017", era == ">=2017")):
    mk = np.asarray(mask)
    print("%-10s %8d %10d %10d %12d %12d %10d" % (
        lbl, mk.sum(), int((old & mk).sum()), int((new & mk).sum()),
        int((old & ~new & known & mk).sum()), int((~old & new & mk).sum()), int((~known & mk).sum())))
print("(old&~new = passes old screen, fails as-traded; ~old&new = fails old, passes as-traded. NaN px_f4 rows are in neither column.)")
dv = m.dvol >= 1e6
print("\nWith the $1M dvol floor also applied (the tradable definition used in an.py):")
for lbl, mask in (("ALL", np.ones(len(m), bool)), ("<=2016", era == "<=2016"), (">=2017", era == ">=2017")):
    mk = np.asarray(mask)
    o = old & dv; nw = new & dv
    print("%-10s old tradable %6d  new tradable %6d  lose %5d  gain %5d  px_f4 NaN among old-tradable %d" % (
        lbl, int((o & mk).sum()), int((nw & mk).sum()), int((o & ~nw & known & mk).sum()),
        int((~o & nw & mk).sum()), int((o & ~known & mk).sum())))
print("\nNFLX / TSLA rows (earliest 6 each):")
for t in ("NFLX", "TSLA"):
    s = m[m.tic == t]
    if len(s):
        print(s[["tic", "sig", "n", "notional", "px", "px_f4", "dvol"]].head(6).to_string(index=False))
    else:
        print(t, ": not present in events")
