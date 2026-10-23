#!/bin/sh
# run.sh — the only commands typed for the v2 site. Usage: ./site/run.sh <command>
#   build        build site/_site from site/ (+ passthrough of docs/)
#   serve        serve site/_site at http://127.0.0.1:8765 (local only)
#   check        build, then every check that exists so far
#   test-engine  engine tests (Python reference + Chromium golden tests)
#   test-worker  the private paid-analysis server's Node tests (../dt-private), if present
#   test-paid-e2e  the paid pages in Chromium against the rehearsal Worker (DT_PRIVATE_REPO, default ../dt-private)
#   site-tests   the three v1 site test files against a local dir (default site/_site; docs = today's pages)
#   bundle       replace docs/ on this branch with the build (step 30 only; asks for DT_BUNDLE=yes)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$HERE")
cd "$REPO"
case "${1:-}" in
  build) python3 site/build.py ;;
  serve) python3 site/build.py && python3 -m http.server 8765 --bind 127.0.0.1 --directory site/_site ;;
  check)
    python3 site/build.py
    python3 checks/contrast.py >/dev/null && echo "contrast: PASS"
    python3 checks/harvest_prices.py docs/pricing/index.html       # the live page (v2 bundle since step 30)
    python3 checks/harvest_prices.py site/_site/pricing/index.html # the page this build would publish
    if [ -f checks/lint.py ]; then python3 checks/lint.py site/_site; fi
    python3 -m pytest -q tests/test_build.py tests/test_design_system.py
    ;;
  test-engine) python3 -m pytest -q tests/test_engine_ref.py tests/test_engine_golden.py tests/test_engine_stats.py tests/test_engine_limits.py tests/test_alias_parity.py tests/test_sniff.py ;;
  test-worker)
    # DT_PUBLIC_REPO: the server's parity tests (ISO list, vendored noise.js) compare with THIS checkout
    if [ -d "$REPO/../dt-private" ]; then (cd "$REPO/../dt-private" && DT_PUBLIC_REPO="$REPO" node --test); else echo "dt-private not present: the paid-analysis server is kept out of this repo"; fi ;;
  test-paid-e2e)
    # delivery plan C-4 Part B: dt-private's deploy bundle on workerd + local D1 + mock Stripe (scripts/rehearse.mjs --serve)
    DT_PRIVATE_REPO="${DT_PRIVATE_REPO:-$REPO/../dt-private}" python3 -m pytest -q tests/test_paid_e2e_rehearsal.py ;;
  site-tests) python3 site/build.py && python3 checks/tests/run_site_tests.py "${2:-site/_site}" ;;
  bundle)
    if [ "${DT_BUNDLE:-}" != "yes" ]; then echo "bundle replaces docs/ — run with DT_BUNDLE=yes (step 30, after the owner's review)"; exit 1; fi
    DT_REQUIRE_LAUNCH_DATE=1 python3 site/build.py   # [legal] launch_date must be set to the push day
    rm -rf docs && cp -R site/_site docs && rm -rf docs/dev && printf 'donttrade.ca\n' > docs/CNAME && touch docs/.nojekyll
    echo "docs/ replaced from site/_site" ;;
  *) sed -n '2,11p' "$0"; exit 1 ;;
esac
