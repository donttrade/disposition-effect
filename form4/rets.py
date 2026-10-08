import pandas as pd,numpy as np,yfinance as yf,warnings,os,sys,time
OUTDIR="f4"
COLS=["tic","sig","entry","n","n_acc","notional","px","dvol","r21","r63","m21","m63"]
import re
# Keeps real suffixed symbols (BRK-B, BF.B, and the .OB/.PK over-the-counter tails
# that are common in this sample); rejects quoted and parenthesised junk.
TICK_OK=re.compile(r"^[A-Z][A-Z0-9]{0,6}(?:[.\-][A-Z]{1,2})?$")
warnings.filterwarnings("ignore")
c=pd.read_csv("f4/clusters.csv.gz",parse_dates=["sig"])
c=c[(c.n>=2)&(c.notional>=100000)]
tics=sorted(c.tic.unique())
spy=yf.download("SPY",start="2005-06-01",auto_adjust=True,progress=False)["Close"]
spy=spy.squeeze(); spy.index=pd.to_datetime(spy.index).tz_localize(None)
sidx=spy.index
def fwd(s,i,h):
    try: return s.iloc[i+h]/s.iloc[i]-1
    except Exception: return np.nan
spyr={h:{} for h in (21,63)}
for h in (21,63):
    for i in range(len(sidx)): spyr[h][sidx[i]]=fwd(spy,i,h)
out=[];B=150
# Resumable: each batch is written to its own part file, so a run killed by a
# shell timeout loses only the batch in flight. MAX_BATCHES lets a caller work
# through 55 batches in several invocations. PACE spaces the bulk fetches --
# this is the third rate limit this pipeline has met, after the SEC and Yahoo.
PARTS=os.path.join(OUTDIR,"events_parts"); os.makedirs(PARTS,exist_ok=True)
MAXB=int(os.environ.get("MAX_BATCHES","999")); PACE=float(os.environ.get("PACE","2.0"))
import json as _json
_LEDGER=os.path.join(OUTDIR,"drops.json")
_blank={"batch_fail":0,"malformed_ticker":0,"ticker_absent":0,"no_data_at_all":0,"series_under_300":0,
        "within_21d_of_series_end":0,"events_written":0,"events_considered":0,
        "batches_done":0,"batches_failed":[]}
# Reloaded each invocation: a batch is counted exactly once because a batch with
# a part file on disk is skipped, so chunking the run still totals correctly.
try: drops=_json.load(open(_LEDGER)); [drops.setdefault(k,v) for k,v in _blank.items()]
except Exception: drops=dict(_blank)
_ran=0
CONTROL=os.environ.get("CONTROL_TICKER","MSFT")
def _limited():
    """True when a known-live ticker returns nothing -- i.e. Yahoo is throttling.
    An empty return raises no exception, so without this check a throttled batch
    is indistinguishable from 150 delisted companies and gets cached as done."""
    try:
        d=yf.download(CONTROL,start="2024-01-02",end="2024-02-01",
                      auto_adjust=True,progress=False)
        return len(d)==0
    except Exception:
        return True
for b in range(0,len(tics),B):
    batch=tics[b:b+B]
    part=os.path.join(PARTS,"b%05d.csv.gz"%b)
    # A part counts as done only when its .ok marker exists. File existence alone
    # is not proof of success: a throttled batch writes a header-only file.
    if os.path.exists(part+".ok"): continue
    if _ran>=MAXB: break
    _ran+=1
    _tries=0
    while _limited():
        _tries+=1
        if _tries>3:
            print("RATE LIMITED at batch",b,"-- stopping with nothing written.",flush=True)
            _json.dump(drops,open(_LEDGER,"w"),indent=1)
            raise SystemExit(3)
        print("  throttled, backing off 60s (attempt %d/3)"%_tries,flush=True)
        time.sleep(60)
    try: df=yf.download(batch,start="2005-06-01",auto_adjust=True,progress=False,threads=True)
    except Exception as e:
        print("batchfail",b,type(e).__name__,e,flush=True)
        drops["batch_fail"]+=len(batch); drops["batches_failed"].append(b)
        time.sleep(PACE); continue
    try: cl=df["Close"]; vo=df["Volume"]
    except Exception: continue
    if isinstance(cl,pd.Series): cl=cl.to_frame(batch[0]); vo=vo.to_frame(batch[0])
    cl.index=pd.to_datetime(cl.index).tz_localize(None); vo.index=cl.index
    sub=c[c.tic.isin(batch)]
    rows_this=[]
    for t,grp in sub.groupby("tic"):
        drops["events_considered"]+=len(grp)
        # 141 of 8,239 symbols in this universe are not symbols at all -- they are
        # fragments of the SEC's free-text ticker field, like "( EPG )" or "(NONE)".
        # They can never price and must not be counted as delistings.
        if not TICK_OK.match(t): drops["malformed_ticker"]+=len(grp); continue
        if t not in cl.columns: drops["ticker_absent"]+=len(grp); continue
        s=cl[t].dropna()
        # yfinance returns an all-NaN column for a delisted ticker, so it passes
        # the column check above and only fails here. Those two causes are
        # different stories and must not be pooled.
        if len(s)==0: drops["no_data_at_all"]+=len(grp); continue
        if len(s)<300: drops["series_under_300"]+=len(grp); continue
        v=vo[t].reindex(s.index)
        dv=(s*v).rolling(20).median()
        for _,r in grp.iterrows():
            i=s.index.searchsorted(r.sig,side="right")
            if i>=len(s)-21: drops["within_21d_of_series_end"]+=1; continue
            ed=s.index[i]
            rows_this.append((t,r.sig,ed,r.n,int(r.n_acc),r.notional,float(s.iloc[i]),
                        float(dv.iloc[i]) if not np.isnan(dv.iloc[i]) else np.nan,
                        fwd(s,i,21),fwd(s,i,63),spyr[21].get(ed,np.nan),spyr[63].get(ed,np.nan)))
    # Self-validating throttle test. A single control ticker is not enough: Yahoo
    # throttles unevenly, so MSFT can answer while AAPL is starved. Instead, take
    # the tickers THIS batch reported as empty and re-request a few individually.
    # A ticker that was dead stays empty; one that was throttled now returns data.
    _empty=[t for t in batch if t not in cl.columns or cl[t].dropna().empty]
    _probe=[t for t in _empty if TICK_OK.match(t)][:12]
    _revived=[]
    for _t in _probe:
        try:
            _d=yf.download([_t],start="2024-01-02",end="2024-02-01",
                           auto_adjust=True,progress=False)
            if len(_d)>0: _revived.append(_t)
        except Exception: pass
        time.sleep(0.5)
    _tickers_with_events=sub.tic.nunique()
    if len(rows_this)<=2 and _tickers_with_events>=20:
        print("RATE LIMITED during batch",b,"-- only %d rows from %d event-tickers; "
              "no batch of real companies yields that. Discarding; nothing written."
              %(len(rows_this),_tickers_with_events),flush=True)
        drops["batch_fail"]+=len(batch); drops["batches_failed"].append(b)
        _json.dump(drops,open(_LEDGER,"w"),indent=1)
        raise SystemExit(3)
    if _revived:
        print("RATE LIMITED during batch",b,"-- %d of %d probed 'empty' tickers came back alive (%s). "
              "Discarding the batch; nothing written."%(len(_revived),len(_probe),",".join(_revived)),flush=True)
        drops["batch_fail"]+=len(batch); drops["batches_failed"].append(b)
        _json.dump(drops,open(_LEDGER,"w"),indent=1)
        raise SystemExit(3)
    pd.DataFrame(rows_this,columns=COLS).to_csv(part,index=False)
    open(part+".ok","w").write("verified\n")   # only now is the batch done
    out.extend(rows_this); drops["events_written"]+=len(rows_this); drops["batches_done"]+=1
    _json.dump(drops,open(_LEDGER,"w"),indent=1)
    print(b,"batch rows",len(rows_this),"cumulative",len(out),flush=True)
    time.sleep(PACE)
import glob,json
parts=sorted(glob.glob(os.path.join(PARTS,"b*.csv.gz.ok")))
parts=[x[:-3] for x in parts]
nb=(len(tics)+B-1)//B
print("parts on disk: %d of %d batches"%(len(parts),nb),flush=True)
if len(parts)<nb:
    json.dump(drops,open(os.path.join(OUTDIR,"drops_partial.json"),"w"),indent=1)
    print("INCOMPLETE -- %d batches still to fetch. Re-run to continue; nothing was lost."
          %(nb-len(parts)),flush=True); raise SystemExit(0)
o=pd.concat([pd.read_csv(f) for f in parts],ignore_index=True)
o.to_csv(os.path.join(OUTDIR,"events.csv.gz"),index=False)
json.dump(drops,open(os.path.join(OUTDIR,"drops.json"),"w"),indent=1)
print("DONE",len(o),o.tic.nunique(),flush=True)
print("DROP LEDGER (this run only):",json.dumps(drops),flush=True)
