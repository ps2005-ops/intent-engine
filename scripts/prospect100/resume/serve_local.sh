#!/usr/bin/env bash
# Prospect-100 resume: a LOCAL founder server for one qualification round.
#
#   scripts/prospect100/resume/serve_local.sh ROUND PORT
#
# Fresh store per round under reports/prospect100_resume/<ROUND>_store, so a
# round is one candidate commit and nothing is mixed across rounds. Reuses
# only the Nov 9 SEC filing cache (filings are immutable by accession number);
# acquisition memory is NOT reused, because its recorded 404s and refusals
# would silently suppress re-fetching sources that may now exist.
#
# ZERO_ANTHROPIC=1: the qualification grades the deterministic core, and a
# stray .env must never turn a round into paid model calls.
# Quotas are raised on THIS local process only; the preview is untouched.
set -euo pipefail
ROUND=${1:?round name}; PORT=${2:?port}
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
ST="$ROOT/reports/prospect100_resume/${ROUND}_store"
mkdir -p "$ST/runtime" "$ST/acq" "$ST/sec"
SEC_SEED="$HOME/ie-prospect100/reports/prospect100_pass3/captures_final_store/sec"
[ -d "$SEC_SEED" ] && [ -z "$(ls -A "$ST/sec")" ] && cp -R "$SEC_SEED/." "$ST/sec/"
# A read-only COPY of what the live market engine has published; the bridge
# reads <root>/reports/market/demo_snapshots, and the live root is never opened.
SNAP="$ST/market_snapshots"
mkdir -p "$SNAP/reports/market/demo_snapshots"
cp -n "$HOME/intent-engine-market/reports/market/demo_snapshots/"*.json \
  "$SNAP/reports/market/demo_snapshots/" 2>/dev/null || true
cd "$ROOT"
export PYTHONPATH="$ROOT/src" ZERO_ANTHROPIC=1 WEBAPP_ENV=development \
  WEBAPP_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))') \
  DEMO_MODE=1 DEMO_MAX_ANALYSES_PER_HOUR=1000 DEMO_MAX_ANALYSES_PER_DAY=1000 \
  DEMO_MAX_ANALYSES_PER_HOUR_PER_VISITOR=1000 \
  WEBAPP_COMMIT=$(git -C "$ROOT" rev-parse HEAD) \
  WEBAPP_STORE="$ST/w.jsonl" WEBAPP_FI_STORE="$ST/fi.jsonl" WEBAPP_CI_STORE="$ST/ci.jsonl" \
  RUNTIME_ROOT="$ST/runtime" ACQUISITION_MEMORY_DIR="$ST/acq" SEC_FILING_CACHE_DIR="$ST/sec" \
  MARKET_SNAPSHOT_ROOT="$SNAP"
exec "${PY:-$HOME/intent-engine/.venv/bin/python}" -m intent_engine.webapp runserver --port "$PORT"
