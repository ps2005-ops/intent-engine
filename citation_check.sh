#!/bin/sh
# Batch-1 citation check (per approval amendment 2): URLs the sandbox could
# NOT verify would be listed here for you to check on the Mac.
#
# STATUS 2026-07-19: all 6 batch-1 citation URLs fetched successfully from
# the sandbox with titles recorded in docs/library_batch1_review_sheet.md.
# NOTHING IS PENDING. The commands below are optional re-verification only.

set -e
# Batch 1 (all verified from sandbox 2026-07-19; re-check optional) +
# Batch 2 (episodes 5-8; the last two are PENDING-MAC-VERIFICATION --
# LTCM's Fed speech returned empty from the sandbox, Japan's IMF PDF was
# oversized to display though it returned 200. These two REQUIRE a real
# 200 here before the batch-2 merge; a non-200 means swap the citation).
for url in \
  "https://www.federalreservehistory.org/essays/panic-of-1907" \
  "https://fraser.stlouisfed.org/files/docs/meltzer/fisdeb33.pdf" \
  "https://www.federalreservehistory.org/essays/banking-panics-1930-31" \
  "https://www.federalreservehistory.org/essays/oil-shock-of-1973-74" \
  "https://www.nber.org/papers/w14563" \
  "https://www.federalreservehistory.org/essays/recession-of-1981-82" \
  "https://www.federalreservehistory.org/essays/stock-market-crash-of-1987" \
  "https://www.federalreservehistory.org/essays/asian-financial-crisis" \
  "https://www.imf.org/external/pubs/ft/wp/2009/wp09241.pdf" \
  "https://home.treasury.gov/system/files/236/hedgfund.pdf" \
  "https://www.nber.org/research/business-cycle-dating" \
  "https://www.bls.gov/cpi/" \
  "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"
do
  code=$(curl -s -o /dev/null -w "%{http_code}" -L "$url")
  echo "$code  $url"
done
