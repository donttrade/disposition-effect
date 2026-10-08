import pandas as pd,numpy as np
d=pd.read_csv("f4/purchases.csv.gz",parse_dates=["fd"])
d=d.drop_duplicates(["tic","fd","RPTOWNERCIK"])
d["wk"]=d.fd.dt.to_period("W")
g=d.groupby(["tic","wk"]).agg(n=("RPTOWNERCIK","nunique"),
                              n_acc=("ACCESSION_NUMBER","nunique"),
                              notional_dup=("notional","sum"),
                              sig=("fd","max")).reset_index()
# REPORTINGOWNER.tsv has one row per owner per filing and build.py attaches the
# FULL filing notional to each, so summing it here counted a joint filing twice.
# The floor is meant to mean $100k of buying, so count each filing once.
# sh_tot is summed over the same distinct accessions, so notional/sh_tot is the
# share-weighted AS-TRADED price of the week's buying (TRANS_PRICEPERSHARE), not
# the retroactively adjusted close that rets.py fetches. Missing or zero share
# total gives NaN, never 0 and never inf.
_ded=(d.drop_duplicates(["tic","wk","ACCESSION_NUMBER"])
        .groupby(["tic","wk"]).agg(notional=("notional","sum"),sh_tot=("sh_tot","sum"))
        .reset_index())
g=g.merge(_ded,on=["tic","wk"],how="left")
g["px_f4"]=np.where(g.sh_tot.fillna(0)>0, g.notional/g.sh_tot.where(g.sh_tot>0), np.nan)
g["yr"]=g.sig.dt.year
print("all weeks with >=1 purchase:",len(g))
for k in (1,2,3,4):
    s=g[g.n>=k]
    print(f"n>={k}: {len(s)} events, {len(s)/((2026.25-2006)*12):.0f}/mo")
c=g[g.n>=2].copy()
print("\nclusters by era:"); print(c.groupby(c.yr<2017).size())
print("\nnotional quantiles (n>=2):"); print(c.notional.quantile([.25,.5,.75,.9]).round(0).to_dict())
print("\ndistinct tickers n>=2:",c.tic.nunique())
c.to_csv("f4/clusters.csv.gz",index=False)
big=c[c.notional>=100000]
print("n>=2 & notional>=$100k:",len(big),"tickers:",big.tic.nunique())
# n_acc is CARRIED, not filtered on, so one price fetch serves both definitions:
# "2+ reporting owners" as published, and "2+ separate filings" as defensible.
solo=int((big.n_acc==1).sum())
print("  of those, all owners on ONE filing: %d (%.1f%%) -- a joint filing, not a cluster"
      % (solo,100.0*solo/max(len(big),1)))
print("  events clearing $100k on the OLD duplicated notional:",int((c.notional_dup>=100000).sum()))
print("  admitted only by the double-count   :",int((c.notional_dup>=100000).sum())-len(big))
