#!/usr/bin/env bash
# Everything after the batch-2 deploy, unattended through quota windows.
#
#   1. the batch-2 INVALIDATION SET, computed in
#      reports/next40_invalidation_v2.json: Rubrik and Commvault, whose
#      winning decision rested on filing boilerplate or an alphabetical tie;
#      HYCU and SnapLogic, whose captures still carry a dict repr because
#      they were measured before the batch-1 renderer repair.
#   2. cohort B, the generalization cohort (15-27)
#   3. cohort C, the confirmation cohort (28-40)
#
# The runner claims reports/next40_owner.json and refuses if another live
# session holds it, so a second writer cannot start a cohort behind this one.
set -u
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
LOG="${1:-/tmp/next40_drive2.log}"
export NEXT40_SESSION="${NEXT40_SESSION:-3ef2b24e-d40c-4d5d-a19e-26a85736a3c7}"

say() { echo "=== $(date '+%H:%M:%S') $*" | tee -a "$LOG"; }

say "STEP 1  batch-2 invalidation (Rubrik, Commvault, HYCU, SnapLogic)"
$PY scripts/next40_qualification.py --cohort A --wait-quota \
    --only 1 --only 9 --only 12 --only 14 2>&1 | tee -a "$LOG"

say "STEP 2  cohort B (15-27)"
$PY scripts/next40_qualification.py --cohort B --wait-quota 2>&1 | tee -a "$LOG"

say "STEP 3  cohort C (28-40)"
$PY scripts/next40_qualification.py --cohort C --wait-quota 2>&1 | tee -a "$LOG"

say "DRIVE COMPLETE — all 40 attempted"
