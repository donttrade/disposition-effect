# prediction-v1: the DT-1 prediction study script, version 1.0

The script for the pre-registered prediction study: do habits in an account's first 30 trades rank the accounts that break a daily-loss or max-loss rule in the next 30 days? A firm runs it on its own past records, on its own machine. It has no network access, writes no file, and prints only group totals in which every cell holds at least 5 accounts.

- How to run it and check it: `partner/README-PREDICTION.md`
- What to export: `partner/EXPORT-GUIDE-PREDICTION.md`
- The registration text: `partner/PREREG-PREDICTION.md`
- The OSF registration: (added when posted)
- Licence: PolyForm Noncommercial 1.0.0, with a free permission to run this version on a firm's real records for this study only (`partner/LICENSING.md`)

## SHA-256 fingerprints (these must match `LICENSING.md` and the OSF registration)

<!-- BEGIN PREDICTION SHA-256 -->

The analysis code (`sha256sum` prints the same):

```
7bc070e8e9496afe730ccffb9900449034edbc8faec124f6f7fbd03d79a8b8a4  partner/prediction_test.py
db81646693dc6888d2361cb49a0031dda659e05c73d23593c5886461882c59c1  partner/dt1_features.py
07f9da966b4734e4d94d86a6f126df6bd24b8ace49709855a7b6fc6e58f6c152  partner/dt1_outcomes.py
2d810ad6222ea724bd649185deac67a25a06de259eee63f508921041a12798ff  partner/prediction_metrics.py
```

The supporting files and the fixture run:

```
daaaecc53c0a96be065b120c43466797670d2116eb45e2afd4c3232ccdbd0da2  partner/make_fixture_prediction.py
4fc66a69b42175789b686833be558e52b20d909705aa5d434282f0f613d12e1a  partner/parity/dt1_golden.json
07fcf9ec005837be4410f213b856a1a4e3e96462ab38b001c92598070eaedfa8  partner/parity/rules_golden.json
abf723c530f13bae94b5612c0ea52a6a26c2cd919176f34cdd4689cc7b519e1f  partner/PREREG-PREDICTION-EXAMPLE.md
d213660000e8c0a7bdc547cb62f25fc1eea6e0c66a5b2bb65b413a38f8286474  fixture trades.csv
1cdfd73bcb7d20ffd947d442339433c61c4a812aaf79e6b899ccfbb2a10cc22b  fixture accounts.csv
c4503575f2538e3f0fd90f4fb12bea5df9a010d485a7d8bbba5ff4c0da124ed1  fixture expected output
```

<!-- END PREDICTION SHA-256 -->
