#!/bin/zsh
# The zero-Anthropic daily learning cycle. Run by com.intentengine.learning.daily
# at 19:15 America/Toronto, after the close and before the market night cycle.
#
#   1. paper daily     resolve every forward forecast whose exit session has
#                      passed (catches up after sleep), alert on overdue/missed
#   2. paper learn     shadow learning on resolved records: attribution,
#                      calibration drift, belief update, candidate proposals
#                      (promotion is human-only)
#   3. paper register --if-due
#                      register the next cohort on the preregistered 21-session
#                      cadence -- the replacement for the retired July generator
#   4. econ resolve    the econ forward ledger (first due 2026-12-25)
#
# Code and data are apart: CODE is a detached worktree pinned by SHA; each
# step runs in the ONE directory that owns its ledger (single writer).
# No step reads ANTHROPIC_API_KEY; it is unset so that a regression to an LLM
# path fails loudly instead of spending.
set -u
CODE=${LEARNING_CODE:?pinned code worktree}
PY=/Users/prathamsharma/intent-engine/.venv/bin/python
PAPER=/Users/prathamsharma/ie-paper-validation
ECON=/Users/prathamsharma/intent-engine-econ
STATUS=$PAPER/reports/paper_validation/learning_daily_status.jsonl
LOCK=/Users/prathamsharma/Library/Logs/intent-engine/learning_daily.lock

unset ANTHROPIC_API_KEY CLAUDE_API_KEY
export PYTHONPATH=$CODE/src TZ=America/Toronto TRADING_MODE=PAPER
# The FRED key stays in its one file; it is read into this process only.
export FRED_API_KEY=$(grep '^FRED_API_KEY=' /Users/prathamsharma/intent-engine/.env | cut -d= -f2- | tr -d "\"'")

mkdir -p ${LOCK:h}
if ! mkdir $LOCK 2>/dev/null; then
  echo "another learning_daily run holds $LOCK; exiting"; exit 0
fi
trap 'rmdir $LOCK' EXIT

typeset -A RC
step() { local name=$1 dir=$2; shift 2
  echo "### $name $(date -u +%FT%TZ)"
  (cd $dir && "$@"); RC[$name]=$?
  echo "### $name rc=${RC[$name]}"
}
step paper_daily    $PAPER $PY -m intent_engine.paper_validation daily
step paper_learn    $PAPER $PY -m intent_engine.paper_validation learn
step paper_register $PAPER $PY -m intent_engine.paper_validation register --if-due
step econ_resolve   $ECON  $PY -m intent_engine.econ.resolve_job \
     --ledger reports/real_forward_expectations.jsonl \
     --log reports/econ_resolution_runs.jsonl

FAILED=()
for k v in ${(kv)RC}; do [[ $v != 0 ]] && FAILED+=$k; done
SHA=$(git -C $CODE rev-parse --short HEAD)
print -r -- "{\"ran_at\": \"$(date -u +%FT%TZ)\", \"code\": \"$SHA\", \"failed\": \"${FAILED[*]}\", \"paper_daily\": ${RC[paper_daily]}, \"paper_learn\": ${RC[paper_learn]}, \"paper_register\": ${RC[paper_register]}, \"econ_resolve\": ${RC[econ_resolve]}}" >> $STATUS
ALERTS=()
tail -1 $PAPER/reports/paper_validation/daily_runs.jsonl 2>/dev/null | grep -q '"status": "ALERT"' && ALERTS+=paper_daily
tail -1 $ECON/reports/econ_resolution_runs.jsonl 2>/dev/null | grep -q '"status": "ALERT"' && ALERTS+=econ_resolve
if (( ${#ALERTS} )); then
  osascript -e "display notification \"alert: ${ALERTS[*]} (see run logs)\" with title \"Intent Engine learning cycle\"" 2>/dev/null
fi
if (( ${#FAILED} )); then
  osascript -e "display notification \"failed: ${FAILED[*]}\" with title \"Intent Engine learning cycle\"" 2>/dev/null
  exit 1
fi
exit 0
