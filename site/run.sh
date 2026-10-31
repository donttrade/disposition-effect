#!/bin/sh
# run.sh — the only commands typed for the v2 site. Usage: ./site/run.sh <command>
#   build        build site/_site from site/ (+ passthrough of docs/)
#   serve        serve site/_site at http://127.0.0.1:8765 (local only)
#   check        build, then every check that exists so far
#   test-engine  engine tests (Python reference + Chromium golden tests)
#   test-worker  the private paid-analysis server's Node tests (DT_PRIVATE_REPO, default ../dt-private), if present
#   test-paid-e2e  the paid pages in Chromium against the rehearsal Worker (DT_PRIVATE_REPO, default ../dt-private)
#   site-tests   the three v1 site test files against a local dir (default site/_site; docs = today's pages)
#   bundle       replace docs/ on this branch with the build (step 30 only; asks for DT_BUNDLE=yes; DT_PREVIEW: C-17)
#   check-live   --base <origin> [--compare <origin>]: every sitemap URL (+ 404, feed) on a deployed copy (C-15)
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
    # DT_PRIVATE_REPO picks the server checkout (default ../dt-private), as tests/test_paid_flow.py does.
    # DT_PUBLIC_REPO: the server's parity tests (ISO list, vendored noise.js) compare with THIS checkout.
    # R-D1 D-6: the server's report method must be the one this site's wording accepts, or nothing runs.
    PRIV="${DT_PRIVATE_REPO:-$REPO/../dt-private}"
    if [ ! -d "$PRIV" ]; then echo "dt-private not present at $PRIV: the paid-analysis server is kept out of this repo"; exit 0; fi
    SITE_M=$(sed -n "s/^export const METHOD_VERSION = '\(.*\)';\$/\1/p" "$REPO/site/static/js/paid/wording.js")
    # DT-2: the server's line may end in a comment (dt-private E1)
    PRIV_M=$(sed -n "s/^export const METHOD_VERSION = '\([^']*\)';\( *\/\/.*\)\{0,1\}\$/\1/p" "$PRIV/src/core/habits.mjs" 2>/dev/null || true)
    if [ -z "$SITE_M" ] || [ "$SITE_M" != "$PRIV_M" ]; then
      echo "method mismatch: server ${PRIV_M:-(none)} at $PRIV, site ${SITE_M:-(none)}: check out dt-private delivery-39 (R-D1.6)"; exit 1
    fi
    (cd "$PRIV" && DT_PUBLIC_REPO="$REPO" node --test) ;;
  test-paid-e2e)
    # delivery plan C-4 Part B: dt-private's deploy bundle on workerd + local D1 + mock Stripe (scripts/rehearse.mjs --serve)
    DT_PRIVATE_REPO="${DT_PRIVATE_REPO:-$REPO/../dt-private}" python3 -m pytest -q tests/test_paid_e2e_rehearsal.py ;;
  check-live) shift; exec python3 checks/check_live.py "$@" ;;
  site-tests) python3 site/build.py && python3 checks/tests/run_site_tests.py "${2:-site/_site}" ;;
  bundle)
    if [ "${DT_BUNDLE:-}" != "yes" ]; then echo "bundle replaces docs/ — run with DT_BUNDLE=yes (step 30, after the owner's review)"; exit 1; fi
    # C-17: a preview bundle (DT_PREVIEW=<name>: noindex, Disallow-all, preview band) lives only on the branch of
    # that name (paid-preview, live-check), never on main; those two branches take only their own preview bundle.
    BR=$(git symbolic-ref --short -q HEAD || true)
    if [ -n "${DT_PREVIEW:-}" ] && [ "$BR" != "$DT_PREVIEW" ]; then
      echo "DT_PREVIEW=$DT_PREVIEW bundles only on the branch $DT_PREVIEW (this is ${BR:-a detached HEAD})"; exit 1; fi
    case "$BR" in paid-preview|live-check)
      if [ "${DT_PREVIEW:-}" != "$BR" ]; then echo "the branch $BR takes only a preview bundle: DT_PREVIEW=$BR"; exit 1; fi ;;
    esac
    DT_REQUIRE_LAUNCH_DATE=1 python3 site/build.py   # [legal] launch_date and terms_date must be set
    rm -rf docs && cp -R site/_site docs && rm -rf docs/dev && printf 'donttrade.ca\n' > docs/CNAME && touch docs/.nojekyll
    echo "docs/ replaced from site/_site" ;;
  *) sed -n '2,12p' "$0"; exit 1 ;;
esac
