import pandas as pd,numpy as np,yfinance as yf,warnings,os,pickle
warnings.filterwarnings("ignore")
tics=open("mom/tickers.txt").read().split()
B=200; CL=[]; DV=[]
for b in range(0,len(tics),B):
    batch=tics[b:b+B]
    try: df=yf.download(batch,start="2005-06-01",auto_adjust=True,progress=False,threads=True)
    except Exception as e: print("fail",b,e,flush=True); continue
    try: cl=df["Close"]; vo=df["Volume"]
    except Exception: continue
    if isinstance(cl,pd.Series): cl=cl.to_frame(batch[0]); vo=vo.to_frame(batch[0])
    cl.index=pd.to_datetime(cl.index).tz_localize(None); vo.index=cl.index
    dv=cl*vo
    ok=[c for c in cl.columns if cl[c].notna().sum()>=500 and (dv[c].median() if dv[c].notna().any() else 0)>=3e6]
    if ok: CL.append(cl[ok].astype("float32")); DV.append(dv[ok].astype("float32"))
    print(b,len(ok),sum(x.shape[1] for x in CL),flush=True)
C=pd.concat(CL,axis=1).sort_index(); D=pd.concat(DV,axis=1).sort_index()
C=C.loc[:,~C.columns.duplicated()]; D=D.loc[:,~D.columns.duplicated()]
pickle.dump({"close":C,"dvol":D},open("mom/panel.pkl","wb"))
print("PANEL",C.shape,C.index.min(),C.index.max(),flush=True)
