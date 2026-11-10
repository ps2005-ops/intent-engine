#!/usr/bin/env bash
# The rest of the qualification, unattended through quota windows.
#
#   1. the INVALIDATION SET only -- eight of cohort A's fourteen, computed in
#      reports/next40_invalidation.json: four whose decision the repair can
#      change, three controls that must not change, and Adastra, whose only
#      failed gate was a cold-start latency gate.
#   2. cohort B, the generalization cohort (15-27)
#   3. cohort C, the confirmation cohort (28-40)
#
# --wait-quota reads the retry window off the refusal page and resumes, so a
# filled window costs a wait rather than a pass.
set -u
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
LOG="${1:-/tmp/next40_drive.log}"
# ONE WRITER. The runner claims reports/next40_owner.json on startup and
# refuses if another live session holds it, so a second session cannot start
# a cohort behind this one's back and reconcile by timestamp afterwards.
export NEXT40_SESSION="${NEXT40_SESSION:-3ef2b24e-d40c-4d5d-a19e-26a85736a3c7}"

say() { echo "=== $(date '+%H:%M:%S') $*" | tee -a "$LOG"; }

say "STEP 1  invalidation set (8 of cohort A)"
$PY scripts/next40_qualification.py --cohort A --wait-quota \
    --only 1 --only 3 --only 4 --only 7 --only 8 --only 10 --only 12 \
    --only 13 2>&1 | tee -a "$LOG"

say "STEP 2  cohort B (15-27)"
$PY scripts/next40_qualification.py --cohort B --wait-quota 2>&1 | tee -a "$LOG"

say "STEP 3  cohort C (28-40)"
$PY scripts/next40_qualification.py --cohort C --wait-quota 2>&1 | tee -a "$LOG"

say "DRIVE COMPLETE"
