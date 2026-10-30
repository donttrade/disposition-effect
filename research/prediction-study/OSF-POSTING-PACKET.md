# Prediction study: posting packet (prepared, nothing posted or sent)

Batch P2 of `ARCHITECT-PREDICTION-STUDY-2026-10-30.md`.

Everything outward-facing is listed here as steps for the owner. **Nothing has been posted to OSF, nothing has been emailed, no tag or branch has been pushed, and no Hyperliquid data has been fetched.**

The owner's answers (29 Oct) are built in:
- **Q1:** the result is published whatever it shows.
- **Q2:** the study licence is free for firms and academic partners, for this study only; the firm plan stays paid for real use.
- **Q3:** the opt-in study save is built, but stays off until this registration is posted (see "U1" below).

## 1. What goes on OSF

**Template:** OSF Preregistration. Its headings were checked against a copy of the OSF Prereg form v1 published in the `preregr` R package, not against the live osf.io page.

| OSF item | Paste from `partner/PREREG-PREDICTION.md` |
|---|---|
| Title; Authors; Description | §1.1. The description is the first paragraph of `README-PREDICTION.md`. |
| Hypotheses | §1.2 |
| Study type; Blinding; Study design; Randomization | §3.1 "Existing data" paragraph (observational, no blinding), §2.1 |
| Existing data; Explanation of existing data | "Registration prior to analysis of the data", plus the §3.1 paragraph |
| Data collection procedures | §3.1, plus `EXPORT-GUIDE-PREDICTION.md` (attach it) |
| Sample size; Sample size rationale; Stopping rule | §3.2 and §3.3 |
| Measured variables; Indices | §2.2 (outcomes), §2.3 (features and DT-1), §2.4 (B0) |
| Statistical models; Inference criteria | §4.2, §4.4, §4.5 |
| Data exclusion; Missing data | §4.1 (E1–E7); undefined features (§2.3) |
| Exploratory analysis | H3–H5, §4.6 |
| Other | §4.3 (code and hashes), §5.1–§5.5, and the parameter block |

**Attach:**
- `PREREG-PREDICTION.md` (the whole text, parameter block included);
- `EXPORT-GUIDE-PREDICTION.md`;
- `research/prediction-study/S2-LAYER1-REPORT.md` and `S3-LAYER2-REPORT.md`.

## 2. The outward steps, in order

| # | Step | Where it runs |
|---|---|---|
| 1 | Review the branch `prediction-study` (Tester, then Manager), then merge it to `main` | Claude Code |
| 2 | Tag the release: `git tag -a prediction-v1 -m "Prediction study v1.0" <merged commit>`, then `git push origin main prediction-v1` | plain Terminal |
| 3 | Create the GitHub release `prediction-v1` with the text of `RELEASE-NOTES-prediction-v1.md` (hashes included) | browser (github.com) |
| 4 | Check that the three hash lists agree: `sha256sum partner/prediction_test.py partner/dt1_features.py partner/dt1_outcomes.py partner/prediction_metrics.py` against `LICENSING.md`, `PREREG-PREDICTION.md` §4.3 and the release notes | plain Terminal |
| 5 | Create the OSF registration from §1 above, attach the files, and submit. **Irreversible:** the timestamp and the publication pledge become public. | browser (osf.io) |
| 6 | Record the registration: put the OSF URL and date in `site/config/prediction_study.json` (`osf_url`, `registered_on`, plus `sha256` from step 4), and put the OSF identifier in place of `registration = "OSF FILL_IN"` in the copy of the block sent to firms | Claude Code |
| 7 | Turn the results page on: set `prediction_results = true` in `site/config/site.toml`, then build, check and bundle the usual way. It shows "Registered: results pending". | Claude Code |
| 8 | Firm outreach (draft in §4). Offer: "a free, pre-registered study of your own past accounts that you run and check yourself". | the owner's email client or LinkedIn |
| 9 | Academic reviewers (drafts in §5) | the owner's email client, from donttrade.research@gmail.com |
| 10 | When a firm agrees, it completes the block's firm fields and sends them in. donttrade posts the block as a dated OSF amendment **before** the firm runs. | browser (osf.io) |
| 11 | The firm runs `python3 -I partner/prediction_test.py trades.csv accounts.csv PREREG-PREDICTION.md` and sends the text. It also runs it with `--json` for the page. | plain Terminal (the firm's machine) |
| 12 | Publish: save the `--json` output as `site/config/prediction_result.json` wrapped as `{"verdict": ..., "runs": [...], "pooled": null}`, then build and bundle | Claude Code |

**Optional before step 5:** the internal Hyperliquid method check (H0, then H1). It is prepared in `/home/claude/research-private/hl-dryrun/`, outside every repo. The commands are in that folder's README:
- H0: `python3 -I hl_dryrun.py probe` (plain Terminal);
- H1: `python3 -I hl_dryrun.py fetch --out ~/research-private/hl-dryrun/run1` (plain Terminal, 4–10 hours).

If H1 runs before posting, replace the last two sentences of §5.1 with: "An internal run on public on-chain perpetual-futures fills checked that the code runs on real-shaped data; it changed nothing in DT-1. No firm data and no user data had been analysed."

## 3. Differences from the Architect's draft (all in the registration text)

1. **Fixed UTC offset.** The day boundary is `day_start` plus a fixed `day_utc_offset`, not a time-zone name. The script is standard library only and opens exactly three files, so it cannot read the time-zone database. The limitation is stated in §5.3.
2. **Three new parameter keys:** `outcome_mode` (firm or rule), `pnl_basis` and `day_utc_offset`. Every study constant accepts only its registered value.
3. **Four files are fingerprinted, not two.** `prediction_test.py` imports `dt1_features.py`, `dt1_outcomes.py` and `prediction_metrics.py` from its own folder. `bisect` was added to the import allowlist, because the verbatim engine copies use it.
4. **The fingerprint** is the SHA-256 of the block's lines, from the BEGIN line to the END line, joined by newlines.
5. **Rules that were left open:**
   - a logistic fit that separates counts as H2 not passed;
   - a standard deviation of 0 for B2 is floored at 10⁻⁹;
   - in rule mode, A is `start_balance`.
6. **E6** uses a `bot_flag` column.
7. **The CFD/futures and per-firm robustness checks** are made across runs.
8. **The exploratory P&L effects, overtrading and size creep** are not in version 1.0. The registration says so.
9. **§3.2 uses the measured power** (94.8% at AUC 0.65, 200/200) in place of the Hanley–McNeil figure (95.6%), plus the measured H2 rates from S3.

## 4. Firm outreach draft (NOT SENT)

> Subject: A free, pre-registered study of your past challenge accounts
>
> We are testing, in public, whether habits in a trader's first 30 trades rank the accounts that break a daily or max-loss rule in the next 30 days. The plan is registered on OSF [link] before any data is seen, and the result is published whatever it shows.
>
> You would run an open-source, standard-library Python script on your own historical records, on your own machine. It has no network access, writes no file and prints only group totals, with every cell holding at least 5 accounts. You read the output before you send it. The script's fingerprints are in the registration, so you can check that you ran exactly the registered code.
>
> Running it for this study is free under the study licence. You choose whether you are named or anonymised. About a day to export two files and an hour to run.
>
> donttrade.research@gmail.com

## 5. Academic reviewer drafts (NOT SENT)

The plan (§6.3) names two people. Neither affiliation was re-checked when this packet was written.

> **To Luke Clark (Centre for Gambling Research, UBC).** Subject: Review request: a pre-registered behaviour-based breach-prediction study.
>
> Your group's work on behaviour-based prediction (Finkenwirth et al. 2021) is the closest precedent to a study we are about to register. Would you review the attached draft registration before it is posted? We would credit you as a reviewer. The code is public and the result will be published whatever it shows. Co-authorship is open if the study interests you.

> **To Tiejun Ma (University of Edinburgh).** Subject: A sister registration on retail spread-betting data?
>
> We are registering a study of whether early trading habits rank later rule breaches in prop-firm accounts. The analysis is an open-source script that runs where the data lives. Would you consider running it on the STX dataset under a sister registration, as an independent replication on data we never see, with co-authorship?

## 6. U1 (the opt-in study save): built later, off until posting

The owner's answer: build it, and keep it off until this registration is posted. Nothing in this worktree can host it yet:
- the Challenge Readiness page and its engine are on the `readiness` branch, not on `main`;
- the save Worker (`donttrade-profiles`, behind `readiness_save`) from `ARCHITECT-CHALLENGE-READINESS-2026-10-29` §2.6 has not been built anywhere.

U1 therefore waits until both exist. It will then add F, B and O to the browser through the public JS, plus Worker schema v2 and consent v1. The golden file `partner/parity/dt1_golden.json` is the target that the browser output has to match.
