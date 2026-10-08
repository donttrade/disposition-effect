import pandas as pd,numpy as np,pickle,sys
from scipy import stats
P=pickle.load(open("mom/panel.pkl","rb")); C=P["close"]; D=P["dvol"]
SH=pickle.load(open("mom/shares.pkl","rb"))      # {ticker: shares_outstanding}
sh=pd.Series(SH).reindex(C.columns)
idx=C.index
# month-end trading days
me=pd.Series(idx,index=idx).groupby([idx.year,idx.month]).max().values
me=[d for d in me if idx.get_loc(d)>=25 and idx.get_loc(d)+21<len(idx)]
rows=[];grid=[]
for d in me:
    i=idx.get_loc(d)
    c=C.iloc[i-25:i+1]
    # formation: close[i-20] -> close[i-3]   (3-day skip)
    f=C.iloc[i-3]/C.iloc[i-20]-1
    dv=D.iloc[i-20:i-2].median()
    px=C.iloc[i]
    elig=(px>=5)&(dv>=1e6)&f.notna()&px.notna()
    u=elig[elig].index
    if len(u)<100: continue
    u=dv[u].nlargest(1000).index                    # liquidity-screened investable universe
    to=(dv[u]/(px[u]*sh[u])).replace([np.inf,-np.inf],np.nan).dropna()
    u=to.index
    fw=C.iloc[i+21][u]/C.iloc[i][u]-1               # 21-day forward, entry at close of d
    ok=fw.notna(); u=u[ok]; fw=fw[u]; to=to[u]; ff=f[u]
    if len(u)<100: continue
    bench=fw.mean()
    rq=pd.qcut(ff.rank(method="first"),5,labels=False)
    tq=pd.qcut(to.rank(method="first"),5,labels=False)
    for a in range(5):
        for b in range(5):
            m=(rq==a)&(tq==b)
            if m.sum()>=3: grid.append((d,a,b,fw[m].mean()-bench,m.sum()))
    sel=(rq==4)&(tq==4)
    if sel.sum()<3: continue
    rows.append((d,fw[sel].mean(),bench,sel.sum(),len(u),list(fw[sel].index)))
r=pd.DataFrame(rows,columns=["d","port","bench","n","univ","names"])
r["ex"]=r.port-r.bench
# turnover cost: fraction of book replaced each month * round-trip spread
prev=set();turn=[]
for nm in r.names:
    s=set(nm); turn.append(1.0 if not prev else 1-len(s&prev)/len(s)); prev=s
r["turn"]=turn
for cost in (0.0007,0.0014):
    r[f"ex_net_{int(cost*1e4)}"]=r.ex-r.turn*cost
g=pd.DataFrame(grid,columns=["d","rq","tq","ex","n"])
def rep(lbl,x):
    x=x.dropna(); print(f"{lbl:<30}{len(x):>6}{100*x.mean():>9.3f}{stats.ttest_1samp(x,0).statistic:>8.2f}")
print(f"{'':<30}{'N mo':>6}{'mean%':>9}{'t':>8}")
print("--- long-only STMOM vs equal-weight same universe, 21d hold ---")
rep("gross excess",r.ex); rep("net @0.07% RT",r.ex_net_7); rep("net @0.14% RT",r.ex_net_14)
for e,gg in r.groupby(r.d.dt.year<=2016):
    rep(("2006-2016 " if e else "2017-2026 ")+"net@7",gg.ex_net_7)
rep("post-2018 net@7",r[r.d.dt.year>=2019].ex_net_7)
print(f"\nmean names {r.n.mean():.1f}  mean universe {r.univ.mean():.0f}  mean turnover {100*r.turn.mean():.0f}%")
print("\n--- M&S grid: excess vs universe, by past-return quintile (rows) x turnover quintile (cols) ---")
pv=g.groupby(["rq","tq"]).ex.mean().unstack()*100
print(pv.round(2).to_string())
print("\nhigh-ret row (rq=4) by turnover quintile, t-stats:")
for b in range(5):
    x=g[(g.rq==4)&(g.tq==b)].groupby("d").ex.mean()
    print(f"  tq={b}: {100*x.mean():+.3f}%  t={stats.ttest_1samp(x.dropna(),0).statistic:+.2f}  N={len(x)}")
r.drop(columns=["names"]).to_csv("mom/bt_months.csv",index=False)
