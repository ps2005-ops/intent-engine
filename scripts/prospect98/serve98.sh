#!/usr/bin/env bash
# Prospect-98: a LOCAL founder server for one round, from an IMMUTABLE tree.
#   scripts/prospect98/serve98.sh ROUND PORT TREE
# TREE is a git-archive export (e.g. ~/ie-p98-trees/base-84b0ccbb) so the round's
# code cannot move while it runs (memory: live-cycle-needs-a-frozen-tree).
# Same isolation as prospect100 serve_local.sh: fresh store, ZERO_ANTHROPIC=1,
# read-only COPIES of market snapshots and econ state; production never opened.
set -euo pipefail
ROUND=${1:?round}; PORT=${2:?port}; TREE=${3:?tree}
HERE=$(cd "$(dirname "$0")/../.." && pwd)
ST="$HERE/reports/prospect98/${ROUND}_store"
mkdir -p "$ST/runtime" "$ST/acq" "$ST/sec" "$ST/research_memory"
SEC_SEED="$HOME/ie-prospect100/reports/prospect100_pass3/captures_final_store/sec"
[ -d "$SEC_SEED" ] && [ -z "$(ls -A "$ST/sec")" ] && cp -R "$SEC_SEED/." "$ST/sec/"
SNAP="$ST/market_snapshots"; mkdir -p "$SNAP/reports/market/demo_snapshots"
cp -n "$HOME/intent-engine-market/reports/market/demo_snapshots/"*.json "$SNAP/reports/market/demo_snapshots/" 2>/dev/null || true
ECON_SRC="$HOME/intent-engine-market/econ"; mkdir -p "$ST/runtime/econ"
for k in state_snapshot expectation expectation_resolution node; do
  [ -f "$ECON_SRC/$k.jsonl" ] && [ ! -f "$ST/runtime/econ/$k.jsonl" ] && cp "$ECON_SRC/$k.jsonl" "$ST/runtime/econ/$k.jsonl"
done
shasum -a 256 "$ST/runtime/econ/"*.jsonl "$SNAP/reports/market/demo_snapshots/"*.json > "$ST/inputs.sha256"
cd "$TREE"
export PYTHONPATH="$TREE/src" ZERO_ANTHROPIC=1 WEBAPP_ENV=development \
  WEBAPP_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))') \
  DEMO_MODE=1 DEMO_MAX_ANALYSES_PER_HOUR=1000 DEMO_MAX_ANALYSES_PER_DAY=1000 \
  DEMO_MAX_ANALYSES_PER_HOUR_PER_VISITOR=1000 \
  WEBAPP_COMMIT=$(basename "$TREE") \
  WEBAPP_STORE="$ST/w.jsonl" WEBAPP_FI_STORE="$ST/fi.jsonl" WEBAPP_CI_STORE="$ST/ci.jsonl" \
  RUNTIME_ROOT="$ST/runtime" ACQUISITION_MEMORY_DIR="$ST/acq" SEC_FILING_CACHE_DIR="$ST/sec" \
  MARKET_SNAPSHOT_ROOT="$SNAP" INDEPENDENT_MEMORY_DIR="${P98_MEMORY:-$ST/research_memory}"
exec "${PY:-$HOME/intent-engine/.venv/bin/python}" -m intent_engine.webapp runserver --port "$PORT"
