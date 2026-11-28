#!/usr/bin/env bash
# Durable round runner: server from an immutable tree + N journey shards, all nohup'd,
# resumable (p98_pass skips rows already done on the same server sha).
#   scripts/prospect98/run_round.sh ROUND PORT TREE SPLIT [SHARDS] [extra p98_pass args...]
set -uo pipefail
ROUND=$1; PORT=$2; TREE=$3; SPLIT=$4; N=${5:-2}; shift 5 || shift $#
HERE=$(cd "$(dirname "$0")/../.." && pwd)
LOG="$HERE/reports/prospect98/$ROUND"; mkdir -p "$LOG"
PY=$HOME/intent-engine/.venv/bin/python
if ! curl -s -m 3 "http://127.0.0.1:$PORT/version" >/dev/null; then
  nohup "$HERE/scripts/prospect98/serve98.sh" "$ROUND" "$PORT" "$TREE" > "$LOG/server.log" 2>&1 &
  echo $! > "$LOG/server.pid"
  for i in $(seq 1 120); do curl -s -m 3 "http://127.0.0.1:$PORT/version" >/dev/null && break; sleep 1; done
fi
curl -s -m 3 "http://127.0.0.1:$PORT/version" || { echo "server did not start"; tail -20 "$LOG/server.log"; exit 1; }
echo
for s in $(seq 1 "$N"); do
  JOURNEY_BASE="http://127.0.0.1:$PORT" PYTHONPATH="$TREE/src" nohup "$PY" "$HERE/scripts/prospect98/p98_pass.py" \
    --split "$SPLIT" --out "$LOG/s$s" --shard "$s/$N" "$@" > "$LOG/shard$s.log" 2>&1 &
  echo $! > "$LOG/shard$s.pid"
done
echo "round $ROUND: server :$PORT tree $TREE split $SPLIT shards $N"
