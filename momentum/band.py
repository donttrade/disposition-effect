import pandas as pd,numpy as np,pickle
from scipy import stats
P=pickle.load(open("mom/panel.pkl","rb"));C=P["close"];D=P["dvol"]
sh=pd.Series(pickle.load(open("mom/shares.pkl","rb"))).reindex(C.columns)
idx=C.index
me=[d for d in pd.Series(idx,index=idx).groupby([idx.year,idx.month]).max().values
    if idx.get_loc(d)>=25 and idx.get_loc(d)+21<len(idx)]
held=set();rows=[]
for d in me:
    i=idx.get_loc(d)
    f=C.iloc[i-3]/C.iloc[i-20]-1; dv=D.iloc[i-20:i-2].median(); px=C.iloc[i]
    e=(px>=5)&(dv>=1e6)&f.notna()&px.notna(); u=e[e].index
    if len(u)<100: continue
    u=dv[u].nlargest(1000).index
    to=(dv[u]/(px[u]*sh[u])).replace([np.inf,-np.inf],np.nan).dropna(); u=to.index
    fw=C.iloc[i+21][u]/C.iloc[i][u]-1; ok=fw.notna(); u=u[ok];fw=fw[u];to=to[u];ff=f[u]
    if len(u)<100: continue
    rq=pd.qcut(ff.rank(method="first"),5,labels=False); tq=pd.qcut(to.rank(method="first"),5,labels=False)
    rt=pd.qcut(ff.rank(method="first"),3,labels=False); tt=pd.qcut(to.rank(method="first"),3,labels=False)
    buy=set(u[(rq==4)&(tq==4)])
    keep=set(u[(rt==2)&(tt==2)])                      # stay while in top tercile of BOTH
    new=(held&keep)|buy
    new={x for x in new if x in set(u)}
    if len(new)<3: held=buy if len(buy)>=3 else held; continue
    sold=len(held-new); bought=len(new-held)
    turn=(sold+bought)/(2*max(len(new),1))
    nm=list(new)
    rows.append((d,fw[nm].mean(),fw.mean(),len(nm),turn))
    held=new
r=pd.DataFrame(rows,columns=["d","port","bench","n","turn"])
r["ex"]=r.port-r.bench
r["net"]=r.ex-r.turn*0.0007
def rep(l,x):
    x=x.dropna();print(f"{l:<28}{len(x):>6}{100*x.mean():>9.3f}{stats.ttest_1samp(x,0).statistic:>8.2f}")
print(f"{'BUY/HOLD BAND':<28}{'N mo':>6}{'mean%':>9}{'t':>8}")
rep("gross excess",r.ex); rep("net @0.07%",r.net)
for e,g in r.groupby(r.d.dt.year<=2016): rep(("2006-2016" if e else "2017-2026")+" net",g.net)
rep("post-2018 net",r[r.d.dt.year>=2019].net)
print(f"mean names {r.n.mean():.0f}   mean monthly turnover {100*r.turn.mean():.0f}%  (vs 79% monthly rebalance)")
