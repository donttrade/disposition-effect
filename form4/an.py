import pandas as pd,numpy as np
from scipy import stats
import os
_src="f4/events_px.csv.gz" if os.path.exists("f4/events_px.csv.gz") else "f4/events.csv.gz"
if _src.endswith("events.csv.gz"):
    print("WARNING: f4/events_px.csv.gz not found; falling back to f4/events.csv.gz. "
          "The as-traded screen (px_f4) is NOT MEASURED in this run; run form4/merge_px.py.")
d=pd.read_csv(_src,parse_dates=["sig","entry"]).dropna(subset=["r21","m21"])
HAS_F4="px_f4" in d.columns
d["ab21"]=d.r21-d.m21; d["ab63"]=d.r63-d.m63
d["era"]=np.where(d.sig.dt.year<=2016,"2006-2016","2017-2026")
def t(x):
    x=x.dropna()
    return len(x),100*x.mean(),100*x.median(),stats.ttest_1samp(x,0).statistic if len(x)>2 else np.nan
print("=== 21-day market-adjusted BHAR, n>=2 insiders, notional>=$100k ===")
print(f"{'cut':<34}{'N':>7}{'mean%':>9}{'med%':>8}{'t':>8}")
def row(lbl,x): 
    N,m,md,tt=t(x); print(f"{lbl:<34}{N:>7}{m:>9.2f}{md:>8.2f}{tt:>8.2f}")
row("ALL",d.ab21)
for e,g in d.groupby("era"): row("  "+e,g.ab21)
print()
for k in (2,3,4,5):
    s=d[d.n>=k]
    row(f"n>={k} ALL",s.ab21)
    for e,g in s.groupby("era"): row(f"   {k}+ {e}",g.ab21)
# Two tradable specifications are reported side by side, dollar-volume floor identical:
#   PUBLISHED : px    >= $5  -- px is the yfinance split/dividend-ADJUSTED close (rets.py);
#               retroactively deflated for old events (NFLX 2006 = $0.29), so era-asymmetric.
#   AS-TRADED : px_f4 >= $5  -- Form 4 TRANS_PRICEPERSHARE, the price the insider reported paying.
SPECS=[("PUBLISHED px>=5 (adjusted close)","px")]
if HAS_F4: SPECS.append(("AS-TRADED px_f4>=5 (Form 4 price)","px_f4"))
def tradable(fr,col): return fr[(fr[col]>=5)&(fr.dvol>=1e6)]
def erarows(lbl,fr,col="ab21"):
    for e in ("2006-2016","2017-2026"): row("%s %s"%(lbl,e),fr[fr.era==e][col])
if not HAS_F4:
    print("\n*** AS-TRADED specification: NOT MEASURED (no px_f4 column in %s) ***"%_src)
for SN,col in SPECS:
    tr=tradable(d,col)
    print("\n"+"#"*78+"\n### SPEC: %s, 20d median $vol>=$1M\n"%SN+"#"*78)
    print("\n=== TRADABLE SUBSET [%s] ==="%SN)
    row("tradable ALL",tr.ab21)
    erarows("  ",tr)
    for k in (3,4):
        s=tr[tr.n>=k]
        row(" n>=%d"%k,s.ab21)
        erarows("   %d+"%k,s)
    print("\n=== THE SAME CUTS, but a cluster must be 2+ SEPARATE FILINGS (n_acc>=2) [%s] ==="%SN)
    print("    a jointly-filed Form 4 is one decision, not several")
    j=d[d.n_acc>=2]
    row("n_acc>=2 ALL",j.ab21)
    for e,g in j.groupby("era"): row("  "+e,g.ab21)
    jt=tradable(j,col)
    row("tradable n_acc>=2",jt.ab21)
    erarows("  ",jt)
    for k in (3,4):
        sk=jt[jt.n_acc>=k]
        row(" tradable n_acc>=%d"%k,sk.ab21)
        erarows("   %d+"%k,sk)
    print("\n=== hold item 6: does the early era lean on the crash? [%s] ==="%SN)
    e1=d[d.sig.dt.year<=2016]; e1t=tradable(e1,col)
    for lbl,fr in (("2006-2016 all",e1),("2006-2016 tradable",e1t)):
        row(lbl,fr.ab21)
        row("  ex 2008-09",fr[~fr.sig.dt.year.isin([2008,2009])].ab21)
    print("\n=== tradable + n>=3, by year [%s] ==="%SN)
    t3=tr[tr.n>=3]
    y=t3.groupby(t3.sig.dt.year).ab21.agg(["count","mean"])
    y["t"]=[stats.ttest_1samp(t3[t3.sig.dt.year==yy].ab21,0).statistic if c>2 else np.nan for yy,c in zip(y.index,y["count"])]
    y["mean"]*=100; print(y.round(2).to_string())
    print("\n=== 63-day, tradable n>=3 [%s] ==="%SN)
    row("63d all",t3.ab63)
    erarows("  ",t3,"ab63")
    print("\n=== WIN RATE, 21d, tradable n>=3 -- BY ERA [%s] ==="%SN)
    for e in ("2006-2016","2017-2026"):
        g=t3[t3.era==e]
        print("  %-10s %.1f%%  (N=%d)" % (e,100*(g.ab21>0).mean() if len(g) else float("nan"),len(g)))
    print("  %-10s %.1f%%  (N=%d)" % ("all eras",100*(t3.ab21>0).mean(),len(t3)))
    print("dvol quartiles tradable:",tr.dvol.quantile([.25,.5,.75]).round(0).to_dict())

if HAS_F4:
    print("\n"+"#"*78+"\n### MEMBERSHIP CHANGE between the two specifications (dvol>=1M in both)\n"+"#"*78)
    o=(d.px>=5)&(d.dvol>=1e6); n_=(d.px_f4>=5)&(d.dvol>=1e6)
    for lbl,mk in (("ALL",d.sig.notna()),("2006-2016",d.era=="2006-2016"),("2017-2026",d.era=="2017-2026")):
        print("  %-10s published-only %5d   as-traded-only %5d   both %5d   (events with r21/m21 only)"%(lbl,int((o&~n_&mk).sum()),int((~o&n_&mk).sum()),int((o&n_&mk).sum())))
    print("  n>=3 headline cell: ")
    for lbl,mk in (("2006-2016",d.era=="2006-2016"),("2017-2026",d.era=="2017-2026")):
        k=mk&(d.n>=3)
        print("  %-10s published-only %5d   as-traded-only %5d   both %5d"%(lbl,int((o&~n_&k).sum()),int((~o&n_&k).sum()),int((o&n_&k).sum())))
