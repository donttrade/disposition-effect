import pandas as pd,numpy as np,pickle
from scipy import stats
P=pickle.load(open("mom/panel.pkl","rb"));C=P["close"];D=P["dvol"]
sh=pd.Series(pickle.load(open("mom/shares.pkl","rb"))).reindex(C.columns)
idx=C.index
me=pd.Series(idx,index=idx).groupby([idx.year,idx.month]).max().values
me=[d for d in me if idx.get_loc(d)>=25 and idx.get_loc(d)+21<len(idx)]
sel_rets={}   # month -> array of selected-name 21d returns
bench={}
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
    s=(rq==4)&(tq==4)
    if s.sum()<5: continue
    sel_rets[d]=fw[s].values; bench[d]=fw.mean()
ms=sorted(sel_rets)
rng=np.random.default_rng(0)
print(f"months={len(ms)}  mean candidates/mo={np.mean([len(sel_rets[m]) for m in ms]):.0f}")
for N in (5,8,20,50):
    paths=[]
    for _ in range(4000):
        ex=[np.mean(rng.choice(sel_rets[m],size=min(N,len(sel_rets[m])),replace=False))-bench[m] for m in ms]
        ex=np.array(ex)-0.0007   # charge full round trip every month
        paths.append((ex.mean(),stats.ttest_1samp(ex,0).statistic,(1+ex).prod()**(12/len(ex))-1))
    p=np.array(paths)
    print(f"N={N:>3}  net mean/mo {100*p[:,0].mean():+.3f}%   t: 5th {np.percentile(p[:,1],5):+.2f} med {np.median(p[:,1]):+.2f} 95th {np.percentile(p[:,1],95):+.2f}   P(t>2)={100*(p[:,1]>2).mean():.0f}%   P(beat bench)={100*(p[:,0]>0).mean():.0f}%")
