# Licensing for `partner/`

## Which licence applies

| Version | Licence |
|---|---|
| `partner-v1` (commit `2ff165c`, 13 October 2026) and earlier | MIT, as the repository root `LICENSE`. That grant stands and is not withdrawn. |
| Every later version | [PolyForm Noncommercial 1.0.0](LICENSE.md), with the notice in [`NOTICE`](NOTICE) |

## In plain words

**Free:** traders running it on their own records; students, researchers, schools, charities, journalists and government bodies; anyone reading or auditing the code.

**Needs a commercial licence:** a business using it for its business — for example, a prop firm or broker running it on its own client records, or publishing, quoting or marketing any figure it produced. A commercial licence comes with the donttrade firm plan and the Pilot. Contact: donttrade.research@gmail.com.

## Additional permission: evaluation

On top of the PolyForm terms, any organisation may run any version of this software **on synthetic or test data** (for example the file `make_fixture.py` writes) for up to 32 days, to decide whether to commission an engagement. This permission does not cover real client records, and it does not cover publishing or quoting anything the software prints.

## Additional permission: prediction study

On top of the PolyForm terms, and on top of the evaluation permission above, any organisation may run the registered version of the prediction study script (release `prediction-v1`, with the SHA-256 fingerprints in the table below) **on its own real client records, free of charge, for the donttrade prediction study only**. The organisations covered are, for example, a prop firm, a broker, or a university research group working with donttrade on the study.

This permission covers three things:
- running that version on the organisation's own records, on its own machines;
- sending the aggregate text the script prints to donttrade;
- donttrade publishing that text as part of the study, under the organisation's name or anonymised, as the organisation chooses.

It does not cover anything else, including:
- ongoing scoring or monitoring of accounts;
- running any other version;
- publishing, quoting or marketing any figure from the run by the organisation itself, except to repeat what donttrade has published;
- any other commercial use.

Using DT-1 or any donttrade measurement in a firm's own operations stays a paid engagement.

## The files in this folder

| File | Licence |
|---|---|
| `partner_disposition.py` (v2, 17 October 2026, per-bound intervals, SHA-256 `c096e375e4e67c9f9c0164f4863b292eea567da3f71132ebba44caf7237388dc`) | PolyForm Noncommercial 1.0.0, as above |
| `make_fixture.py` (the synthetic test-file generator) | PolyForm Noncommercial 1.0.0, as above |
| `prediction_test.py`, `dt1_features.py`, `dt1_outcomes.py`, `prediction_metrics.py` (prediction study v1.0; SHA-256 in the table below) | PolyForm Noncommercial 1.0.0, plus the prediction-study permission above |
| `make_fixture_prediction.py`, `parity/dt1_golden.json`, `parity/rules_golden.json` | PolyForm Noncommercial 1.0.0, as above |
| `README.md`, `EXPORT-GUIDE.md`, `README-PREDICTION.md`, `EXPORT-GUIDE-PREDICTION.md`, `PREREG-PREDICTION.md`, `PREREG-PREDICTION-EXAMPLE.md`, this file | PolyForm Noncommercial 1.0.0, as above |
| `LICENSE.md` | the PolyForm Noncommercial 1.0.0 terms, unchanged |
| `NOTICE` | the required notice |

### Prediction study v1.0: SHA-256 fingerprints

These must match the OSF registration and the release notes of `prediction-v1` (check with `sha256sum`, plain Terminal):

<!-- BEGIN PREDICTION SHA-256 -->

The analysis code (`sha256sum` prints the same):

```
7e670cbe08b905acdd91ff6edaeffb0f7c784a920b20a45f54423c1acd8b14f5  partner/prediction_test.py
e782800ca5948648f80b5554e5942147946b3eb52edf497acd9eac3618b05c9a  partner/dt1_features.py
07f9da966b4734e4d94d86a6f126df6bd24b8ace49709855a7b6fc6e58f6c152  partner/dt1_outcomes.py
2d810ad6222ea724bd649185deac67a25a06de259eee63f508921041a12798ff  partner/prediction_metrics.py
```

The supporting files and the fixture run:

```
daaaecc53c0a96be065b120c43466797670d2116eb45e2afd4c3232ccdbd0da2  partner/make_fixture_prediction.py
cf921b4b9a0c979fdcdb9ee2f0c8aac4c79d9aebba604ef3137e8ecd451159f7  partner/parity/dt1_golden.json
07fcf9ec005837be4410f213b856a1a4e3e96462ab38b001c92598070eaedfa8  partner/parity/rules_golden.json
abf723c530f13bae94b5612c0ea52a6a26c2cd919176f34cdd4689cc7b519e1f  partner/PREREG-PREDICTION-EXAMPLE.md
d213660000e8c0a7bdc547cb62f25fc1eea6e0c66a5b2bb65b413a38f8286474  fixture trades.csv
1cdfd73bcb7d20ffd947d442339433c61c4a812aaf79e6b899ccfbb2a10cc22b  fixture accounts.csv
cf85df0d44342018cc7353ba7466d6f7b91f60bd4a7cc16247fd50b086495093  fixture expected output
```

<!-- END PREDICTION SHA-256 -->

A file that is unchanged since `partner-v1` is also available under MIT from that commit; the MIT grant is not
withdrawn.

## The Open Behavioural Measurement Spec (OBMS) is licensed separately

The OBMS draft, which defines what this script measures and the suite that checks it, is a separate folder with
its own licence file (`LICENSE` in the spec folder):
- **Specification text** (`SPEC.md`, `README.md`, `CHANGELOG.md` there): Creative Commons Attribution 4.0
  International (CC BY 4.0).
- **Conformance suite** (everything under `test-suite/` there, including the oracle): MIT.

This script is one implementation of that spec. It is not part of the spec, and the spec's licences do not
cover it. The spec's licences do not change this folder's licence, and this folder's licence does not restrict
the spec: anyone may implement the spec, commercially or not, without using this script.

## Name

No one may describe a figure as measured, verified, certified, audited or produced by donttrade, or imply that donttrade endorses a firm, except under a signed firm plan or Pilot agreement and in the wording that agreement allows.

## Text, charts and numbers

Study write-ups and charts on the website are licensed CC BY-NC 4.0. The numbers in them are facts: quote them freely, with a link. A figure about one public panel says nothing about any firm's traders.
