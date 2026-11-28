#!/usr/bin/env bash
# Score one round end to end (no analysis, no model calls):
#   scripts/prospect98/score_round.sh ROUND TREE SEARCH_JSON [SPLIT] [UI=1]
# Writes docs/engineering/prospect98/{qualification,report_availability,history_expanded,ui_matrix,strengthened}_ROUND.json
set -uo pipefail
R=$1; TREE=$2; SEARCH=$3; SPLIT=${4:-DEVELOPMENT}; UI=${5:-1}; CAP=${6:-rerender}
HERE=$(cd "$(dirname "$0")/../.." && pwd); cd "$HERE"
D=docs/engineering/prospect98; P=reports/prospect98/$R; PY=$HOME/intent-engine/.venv/bin/python
PYTHONPATH=$TREE/src $PY scripts/prospect98/qualify98.py --pass $P --store reports/prospect98/${R}_store/ci.jsonl --search $SEARCH --split $SPLIT --out $P/qual_noui.json >/dev/null
U=reports/prospect98/ui/ui_matrix_$R.json; mkdir -p reports/prospect98/ui
if [ "$UI" = 1 ] && [ ! -f $U ]; then
  $HOME/job-application-agent/.venv/bin/python scripts/prospect100/ui_matrix.py --captures $P/$CAP --out $U \
    --widths 320,360,375,390,414,430,768,820,1024,1280,1440,1920 --screens $P/screens --workers 4 > $P/ui_matrix.log 2>&1
fi
UIARG=""; [ -f $U ] && UIARG="--ui $U" && python3 -c "import json;d=json.load(open('$U'));json.dump({'summary':d['summary'],'full_results':'$U'},open('$D/ui_matrix_$R.summary.json','w'),indent=1)"
PYTHONPATH=$TREE/src $PY scripts/prospect98/qualify98.py --pass $P --store reports/prospect98/${R}_store/ci.jsonl --search $SEARCH --split $SPLIT --captures $P/$CAP $UIARG --out $D/qualification_$R.json | head -40
ZERO_ANTHROPIC=1 PYTHONPATH=$TREE/src $PY scripts/prospect100/resume/diagnose_reports.py --store reports/prospect98/${R}_store --states "$P/s*/state.json" --out $D/report_availability_$R.json >/dev/null 2>&1 || echo "diagnose_reports failed"
python3 scripts/prospect100/resume/history_expanded.py $P $D/history_expanded_$R.json >/dev/null
python3 scripts/prospect98/strengthened98.py --qual $D/qualification_$R.json --avail $D/report_availability_$R.json \
  --history $D/history_expanded_$R.json --index $P/$CAP/index.json $UIARG --out $D/strengthened_$R.json
