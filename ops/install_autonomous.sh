#!/usr/bin/env bash
# Install the market engine's unattended launchd agents.
#
#   ops/install_autonomous.sh --dry-run    # render + validate, install nothing
#   ops/install_autonomous.sh              # install and load
#
# IDEMPOTENT. Re-running unloads any existing agent before reloading it, so a
# second run leaves exactly one scheduled job per cycle -- never two. That is
# the specific failure this script exists to prevent: a duplicated launchd job
# runs the cycle twice, and while the run identity would catch it, a system
# that relies on its last line of defence for a routine mistake is one bug away
# from double-counting.
#
# PATHS ARE RESOLVED, NEVER HARD-CODED. The repository root comes from this
# script's own location, so the rendered plists point at wherever the repo
# actually lives -- not at whatever path happened to be current when the
# template was written.
#
# NO SECRETS. The rendered plists contain a path, a schedule and
# TRADING_MODE=PAPER. The script refuses to install if a rendered file contains
# anything that looks like a credential (checked, not assumed).
set -uo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
AGENTS="$HOME/Library/LaunchAgents"
LOGDIR="$HOME/Library/Logs/intent-engine"
ROOT="${IE_MARKET_ROOT:-$REPO/data}"
TEMPLATES="$REPO/ops/launchd"
STAGE="$(mktemp -d)"

LABEL_PREFIX="com.intentengine.market"

# --- interpreter ------------------------------------------------------------
# An explicit interpreter from the project's own environment. launchd runs with
# a minimal environment and no shell profile, so "python3" would resolve to
# whatever /usr/bin/python3 is -- a different interpreter with none of this
# project's dependencies.
PYTHON="${IE_PYTHON:-$REPO/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "FAIL: no usable Python interpreter. Set IE_PYTHON=/path/to/python." >&2
  exit 1
fi

echo "repository   $REPO"
echo "interpreter  $PYTHON"
echo "runtime root $ROOT"
echo "logs         $LOGDIR"
echo "agents       $AGENTS"
echo

# --- preflight: the code must actually be importable ------------------------
# Installing a schedule that points at code the interpreter cannot import
# produces a job that fails silently every night. Checked BEFORE anything is
# written.
if ! PYTHONPATH="$REPO/src" "$PYTHON" -c "import intent_engine.market.cycle" 2>/dev/null; then
  echo "FAIL: '$PYTHON' cannot import intent_engine.market from $REPO/src." >&2
  echo "      Install the project's dependencies, or point IE_PYTHON at the" >&2
  echo "      interpreter that has them, then re-run." >&2
  exit 1
fi
echo "preflight    import OK"

render() {
  local template="$1" out="$2" label="$3" cycle="$4" hour="$5" minute="$6"
  sed -e "s|{{LABEL}}|$label|g" \
      -e "s|{{PYTHON}}|$PYTHON|g" \
      -e "s|{{REPO}}|$REPO|g" \
      -e "s|{{ROOT}}|$ROOT|g" \
      -e "s|{{LOGDIR}}|$LOGDIR|g" \
      -e "s|{{CYCLE}}|$cycle|g" \
      -e "s|{{HOUR}}|$hour|g" \
      -e "s|{{MINUTE}}|$minute|g" \
      "$template" > "$out"
}

render "$TEMPLATES/cycle.plist.template"  "$STAGE/$LABEL_PREFIX.day.plist" \
       "$LABEL_PREFIX.day"   day   6 30
render "$TEMPLATES/cycle.plist.template"  "$STAGE/$LABEL_PREFIX.night.plist" \
       "$LABEL_PREFIX.night" night 20 30
render "$TEMPLATES/health.plist.template" "$STAGE/$LABEL_PREFIX.health.plist" \
       "$LABEL_PREFIX.health" health 0 0

# --- validate ---------------------------------------------------------------
fail=0
for f in "$STAGE"/*.plist; do
  if ! plutil -lint "$f" >/dev/null 2>&1; then
    echo "FAIL: $f is not a valid plist" >&2; fail=1
  fi
  # Secret scan over the PARSED plist, not the raw file. The templates discuss
  # credentials in their own comments ("SECRETS: none"), and a scanner that
  # reads comments flags every one of them -- a check that always fires teaches
  # the operator to ignore it. plutil drops comments, so this scans what
  # launchd will actually load.
  if plutil -convert json -o - "$f" 2>/dev/null | \
     grep -Eiq '(api[_-]?key|secret|token|passwd|password|bearer|sk-[A-Za-z0-9]{10})'; then
    echo "FAIL: $(basename "$f") appears to contain a credential — refusing" >&2
    fail=1
  fi
  # An unrendered placeholder means the template and the script disagree.
  if grep -q '{{' "$f"; then
    echo "FAIL: $(basename "$f") has unrendered placeholders" >&2; fail=1
  fi
done
[[ $fail -eq 0 ]] || exit 1
echo "validate     plutil OK, no secrets, no placeholders"

if [[ $DRY_RUN -eq 1 ]]; then
  echo
  echo "DRY RUN — nothing installed. Rendered files:"
  for f in "$STAGE"/*.plist; do echo "  $f"; done
  echo
  echo "Install for real with:  ops/install_autonomous.sh"
  exit 0
fi

# --- install ----------------------------------------------------------------
mkdir -p "$AGENTS" "$LOGDIR" "$ROOT"
uid="$(id -u)"
for f in "$STAGE"/*.plist; do
  label="$(basename "$f" .plist)"
  target="$AGENTS/$label.plist"
  # Unload first so a re-run cannot leave two registrations of the same job.
  launchctl bootout "gui/$uid/$label" >/dev/null 2>&1 || true
  cp "$f" "$target"
  chmod 644 "$target"
  if launchctl bootstrap "gui/$uid" "$target" 2>/dev/null; then
    echo "loaded       $label"
  else
    echo "WARN: could not bootstrap $label (already loaded, or launchd" >&2
    echo "      refused). Check: launchctl print gui/$uid/$label" >&2
  fi
done

echo
echo "installed. verify with:"
echo "  launchctl list | grep $LABEL_PREFIX"
echo "  PYTHONPATH=$REPO/src $PYTHON -m intent_engine.market status --root $ROOT"
