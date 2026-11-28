#!/usr/bin/env bash
# Re-render a round's stored runs (slides included) on an IMMUTABLE tree. No analysis,
# no fetch, no model call. Writes a NEW capture set; never overwrites or deletes one.
#   scripts/prospect98/rerender98.sh ROUND TREE [OUT_NAME=rerender]
# Runs FROM the tree with its own src (memory: pristine-comparison-runs-from-the-export).
set -euo pipefail
R=$1; TREE=$2; NAME=${3:-rerender}
HERE=$(cd "$(dirname "$0")/../.." && pwd)
P=$HERE/reports/prospect98/$R; ST=$HERE/reports/prospect98/${R}_store
if [ -e "$P/$NAME" ] || [ -e "$P/${NAME}_store" ]; then
  echo "refusing: $P/$NAME already exists (a capture set is never overwritten)"; exit 1
fi
cd "$TREE"
ZERO_ANTHROPIC=1 MARKET_SNAPSHOT_ROOT="$ST/market_snapshots" PYTHONPATH="$TREE/src" \
  "$HOME/intent-engine/.venv/bin/python" "$TREE/scripts/prospect100/resume/rerender_current.py" \
  --store "$ST" --states "$P/s*/state.json" --out "$P/$NAME"
