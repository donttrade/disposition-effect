# Data licence

The code in this repository is MIT (see `LICENSE`).

**The data is not mine and is not covered by that licence.**

`sample1.Rdata` and `sample2.Rdata` are replication files for:

> Xuejun Jin, Rui Li & Yu Zhu (2021). "Could social interaction reduce the
> disposition effect? Evidence from retail investors in a directed social
> trading network." *PLoS ONE* **16**(2): e0246759.
> <https://doi.org/10.1371/journal.pone.0246759>

Deposited at Harvard Dataverse, <https://doi.org/10.7910/DVN/NI6SBJ>, under
**CC0 1.0 Universal** (public domain dedication). Verified via the Dataverse
API: `rightsIdentifier: CC0-1.0`, `restricted: false`, no terms of use, on all
four files in the deposit.

CC0 imposes no attribution requirement. The citation above is given anyway,
because the authors did the hard part.

These two Dataverse files are **not committed to this repository**.
`reproduce.py` downloads them from Dataverse on first run.

## The real public data behind /tools/ (since 6 Nov 2026)

The previews on donttrade.ca/tools/ and in the free tool pages' headers are the
tools run on real public data. The inputs, scripts and hashes are in
`checks/real_data/`; the figures are in `site/config/tool_real.json`.

**The trade-file tools and the test's summary.** The trade file is derived from:

> Laramee, R. (2025). Stock Transactions Dataset. Mendeley Data, V1. doi:10.17632/k4tnk2nggv.1. Licensed CC BY 4.0. Changes: we kept the dataset’s market buys and sells (its combined, split-adjusted sheet) and turned them into a trade file, with ticker names replaced with codes; results are price gains in US dollars before fees, FX and dividends. Selection: the whole dataset, one anonymous investor; not picked by result. The dataset’s authors do not endorse donttrade.

<https://doi.org/10.17632/k4tnk2nggv.1>, licence
<https://creativecommons.org/licenses/by/4.0/>. The derived CSVs keep that
licence. Only one is committed: `checks/real_data/real-trades.coded.csv` (made by
`make_coded_csv.py`), the copy the tools' "Try real public data" button loads, with each ticker
replaced by a neutral code ("Stock 01", "Stock 02", ... in order of first appearance); every other
value is unchanged. Neither the raw xlsx nor the trade file with the real tickers is committed:
`checks/real_data/fetch.py` downloads the xlsx into `checks/real_data/raw/` (gitignored), refuses a
copy whose SHA-256 differs from the one Mendeley publishes, then runs `make_real_csv.py`, which
writes `checks/real_data/raw/real-trades.csv` and refuses it unless its SHA-256 is the one recorded in
`site/config/tool_real.json` (b20de3f2…0ea518).

We use it because it is the only openly licensed, fill-level record of one real account we found.

**Lot size (one past month of the euro, for scale).** Board of Governors of the
Federal Reserve System, H.10 Foreign Exchange Rates, euro, noon buying rates in
New York (public domain), <https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm>. The Board's notice, in full: "Unless otherwise
indicated, information on Board's website is in the public domain and may be
copied and distributed without permission. Please cite to the Board as the
source of the information." FRED carries the same series, but its terms restrict caching and
commercial use, so it is not used.

**Disposition-effect calculator.** Odean, T. (1998). Are investors reluctant to
realize their losses? *Journal of Finance* 53(5), 1775–1798, Table I, entire year:
four published counts, cited as facts, <https://doi.org/10.1111/0022-1082.00072>. The paper is not stored here.
