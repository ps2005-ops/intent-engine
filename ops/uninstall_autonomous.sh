#!/usr/bin/env bash
# Remove the market engine's unattended launchd agents.
#
#   ops/uninstall_autonomous.sh --dry-run   # show what would be removed
#   ops/uninstall_autonomous.sh             # unload and delete the plists
#
# IDEMPOTENT: running it twice, or on a machine where nothing is installed,
# succeeds and reports that there was nothing to do.
#
# WHAT IT DOES NOT TOUCH: run records, reports, the funnel history, the asset
# ledger, or the logs. Uninstalling the SCHEDULE must never delete RESEARCH --
# those are the only measurements this project has, and "I turned off the timer"
# is not consent to erase sixteen days of operating history. Remove the runtime
# root by hand if that is genuinely what you want.
set -uo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

AGENTS="$HOME/Library/LaunchAgents"
LABELS=(com.intentengine.market.day
        com.intentengine.market.night
        com.intentengine.market.health)
uid="$(id -u)"
found=0

for label in "${LABELS[@]}"; do
  plist="$AGENTS/$label.plist"
  loaded=""
  launchctl list 2>/dev/null | grep -q "$label" && loaded=" (loaded)"
  if [[ -f "$plist" || -n "$loaded" ]]; then
    found=1
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "would remove  $label$loaded"
      continue
    fi
    launchctl bootout "gui/$uid/$label" >/dev/null 2>&1 || true
    rm -f "$plist"
    echo "removed       $label"
  else
    echo "not installed $label"
  fi
done

if [[ $found -eq 0 ]]; then
  echo
  echo "nothing was installed; nothing to do."
elif [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "DRY RUN — nothing removed."
else
  echo
  echo "autonomous operation is OFF. Reports, run records and research history"
  echo "are untouched. Cycles can still be run by hand:"
  echo "  python -m intent_engine.market night --root <root>"
fi
