#!/bin/sh
# Batch-1 citation check (per approval amendment 2): URLs the sandbox could
# NOT verify would be listed here for you to check on the Mac.
#
# STATUS 2026-07-19: all 6 batch-1 citation URLs fetched successfully from
# the sandbox with titles recorded in docs/library_batch1_review_sheet.md.
# NOTHING IS PENDING. The commands below are optional re-verification only.

set -e
for url in \
  "https://www.federalreservehistory.org/essays/panic-of-1907" \
  "https://fraser.stlouisfed.org/files/docs/meltzer/fisdeb33.pdf" \
  "https://www.federalreservehistory.org/essays/banking-panics-1930-31" \
  "https://www.federalreservehistory.org/essays/oil-shock-of-1973-74" \
  "https://www.nber.org/papers/w14563" \
  "https://www.federalreservehistory.org/essays/recession-of-1981-82"
do
  code=$(curl -s -o /dev/null -w "%{http_code}" -L "$url")
  echo "$code  $url"
done
