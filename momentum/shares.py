import pickle,yfinance as yf,warnings,time
warnings.filterwarnings("ignore")
C=pickle.load(open("mom/panel.pkl","rb"))["close"]
out={}
for i,t in enumerate(C.columns):
    try:
        s=yf.Ticker(t).fast_info.get("shares")
        if s and s>0: out[t]=float(s)
    except Exception: pass
    if i%200==0: print(i,len(out),flush=True)
pickle.dump(out,open("mom/shares.pkl","wb"))
print("SHARES",len(out),"of",len(C.columns),flush=True)
