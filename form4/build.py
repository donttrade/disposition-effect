import io,os,sys,time,zipfile,urllib.request,urllib.error,pandas as pd,numpy as np

# The SEC refuses automated requests that do not declare a contact it can reach:
# an absent User-Agent is 403, and so is one carrying only a URL. The contact is
# therefore read from the environment and never committed to this repository.
#     export SEC_UA="your-project-name you@example.com"
_ua = os.environ.get("SEC_UA", "").strip()
if not _ua or "@" not in _ua:
    sys.exit("build.py: set SEC_UA first, e.g.\n"
             '  export SEC_UA="my-research me@example.com"\n'
             "The SEC returns 403 for requests without a reachable contact address.")
UA={"User-Agent":_ua}
BASE="https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/"
OUT="f4"   # relative: clusters.py, rets.py and an.py all read f4/ from the repo root
PAUSE=1.0  # seconds between downloads. With none, 81 back-to-back requests earn
           # "Request Rate Threshold Exceeded" and the run dies half-built.
os.makedirs(OUT, exist_ok=True)   # the loop below writes into it and cannot create it
dl_fail=0; parsed=[]; aff_present=[]; aff_dropped=0
qs=[f"{y}q{q}" for y in range(2006,2027) for q in (1,2,3,4)]
qs=qs[:qs.index("2026q2")]
rows=[]
def rd(z,name,cols):
    try: df=pd.read_csv(io.BytesIO(z.read(name)),sep="\t",dtype=str,low_memory=False)
    except KeyError: return None
    df.columns=[c.upper() for c in df.columns]
    keep=[c for c in cols if c in df.columns]
    return df[keep]
for q in qs:
    f=f"{OUT}/{q}.zip"
    if not os.path.exists(f):
        try:
            r=urllib.request.urlopen(urllib.request.Request(BASE+q+"_form345.zip",headers=UA),timeout=120)
            open(f,"wb").write(r.read())
        except urllib.error.HTTPError as e:
            print(q,"DL FAIL http",e.code,e.reason,flush=True)
            dl_fail+=1; time.sleep(PAUSE); continue
        except Exception as e:
            print(q,"DL FAIL",type(e).__name__,e,flush=True)
            dl_fail+=1; time.sleep(PAUSE); continue
        time.sleep(PAUSE)
    try: z=zipfile.ZipFile(f)
    except Exception as e:
        print(q,"ZIP FAIL",e,flush=True); continue
    sub=rd(z,"SUBMISSION.tsv",["ACCESSION_NUMBER","FILING_DATE","ISSUERTRADINGSYMBOL","ISSUERCIK","DOCUMENT_TYPE","AFF10B5ONE"])
    # AFF10B5ONE is NOT a NONDERIV_TRANS column -- it is absent there in all 81
    # quarters, and rd() drops a requested column that does not exist without
    # complaining, which is why the 10b5-1 filter silently never ran.
    nd =rd(z,"NONDERIV_TRANS.tsv",["ACCESSION_NUMBER","TRANS_CODE","TRANS_ACQUIRED_DISP_CD","TRANS_SHARES","TRANS_PRICEPERSHARE","TRANS_DATE"])
    ow =rd(z,"REPORTINGOWNER.tsv",["ACCESSION_NUMBER","RPTOWNERCIK"])
    if sub is None or nd is None or ow is None: print(q,"MISSING TABLE",flush=True); continue
    missing=[c for c in ["TRANS_CODE","TRANS_ACQUIRED_DISP_CD","TRANS_SHARES","TRANS_PRICEPERSHARE"] if c not in nd.columns]
    if missing: print(q,"MISSING COLS",missing,flush=True); continue
    sub=sub[sub.get("DOCUMENT_TYPE","4").astype(str).str.strip()=="4"]
    # 10b5-1 plan filings. The flag is filing-level and the SEC only began
    # publishing it in 2023q1, so this applies to 13 of the 81 quarters and the
    # rest genuinely cannot be filtered. Dropping the accession here removes it
    # from the inner merge below, which is the whole purpose.
    if "AFF10B5ONE" in sub.columns:
        _plan=sub.AFF10B5ONE.astype(str).str.strip().str.lower().isin(["1","true","y","yes"])
        aff_dropped+=int(_plan.sum()); sub=sub[~_plan]; aff_present.append(q)
    nd=nd[(nd.TRANS_CODE.astype(str).str.strip().str.upper()=="P") &
          (nd.TRANS_ACQUIRED_DISP_CD.astype(str).str.strip().str.upper()=="A")]
    nd["sh"]=pd.to_numeric(nd.TRANS_SHARES,errors="coerce")
    nd["px"]=pd.to_numeric(nd.TRANS_PRICEPERSHARE,errors="coerce")
    nd=nd[(nd.sh>0)&(nd.px>0)]
    nd["notional"]=nd.sh*nd.px
    # TRANS_PRICEPERSHARE is the as-traded execution price: what the insider
    # actually paid on the transaction date, with no split or dividend
    # adjustment. The share total is carried (not a price) so that a week-level
    # price is just notional/sh_tot with no weighted-average logic. The tradable
    # screen needs this, NOT the yfinance close in rets.py: that close is
    # retroactively split- and dividend-adjusted, so Netflix's 2006 events sit at
    # $0.29 and fail a $5 screen they cleared by two orders of magnitude in
    # reality (Tesla 2011 is $1.90). The distortion grows with the age of the
    # event, so it is era-asymmetric.
    agg=nd.groupby("ACCESSION_NUMBER",as_index=False).agg(notional=("notional","sum"),
                                                          sh_tot=("sh","sum"))
    m=agg.merge(sub,on="ACCESSION_NUMBER",how="inner").merge(ow,on="ACCESSION_NUMBER",how="inner")
    m["tic"]=m.ISSUERTRADINGSYMBOL.astype(str).str.strip().str.upper()
    m=m[~m.tic.isin(["NONE","NAN",""])]
    m["fd"]=pd.to_datetime(m.FILING_DATE,errors="coerce")
    m=m.dropna(subset=["fd"])
    # ACCESSION_NUMBER is carried through so a cluster can be tested for being
    # a single jointly-filed Form 4 rather than independent decisions.
    rows.append(m[["tic","fd","RPTOWNERCIK","notional","sh_tot","ISSUERCIK","ACCESSION_NUMBER"]])
    parsed.append(q)
    print(q,len(m),flush=True)
if not rows:
    sys.exit("NOTHING BUILT: %d quarters attempted, %d downloads failed.\n"
             "  http 403                        -> SEC_UA is not a reachable contact\n"
             "  Request Rate Threshold Exceeded -> raise PAUSE above 1.0\n"
             "A failed download is not an empty dataset and must not be analysed as one."
             % (len(qs), dl_fail))
all_=pd.concat(rows,ignore_index=True)
all_.to_csv(f"{OUT}/purchases.csv.gz",index=False)
pd.DataFrame({"quarter":parsed,
              "aff10b5one_present":[q in set(aff_present) for q in parsed]}
             ).to_csv(f"{OUT}/coverage.csv",index=False)
print("TOTAL",len(all_),all_.fd.min(),all_.fd.max(),flush=True)
print("QUARTERS parsed %d of %d, download failures %d" % (len(parsed),len(qs),dl_fail),flush=True)
print("AFF10B5ONE present in %d of %d parsed quarters (SEC began publishing it in 2023q1); "
      "%d 10b5-1 plan filings dropped" % (len(aff_present),len(parsed),aff_dropped),flush=True)
