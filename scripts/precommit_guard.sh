#!/usr/bin/env bash
# Pre-commit guard (B2, PLAN_2026-07-21). Two checks, both hard-fail the commit:
#
#   1. TREE CHECK — the synthetic-worlds file set must be tracked and must not
#      be staged-deleted or sitting untracked (the exact loose end B1 fixed).
#   2. SUITE CHECK — the offline suite must pass with EXIT=0, explicitly
#      checked (repo convention). Live/networked tests are deselected; the
#      guard makes 0 model calls (ANTHROPIC_API_KEY is stripped).
#
# Install:  scripts/install_precommit_hook.sh   (copies this to .git/hooks/pre-commit)
# Escape hatch (emergencies only): git commit --no-verify
# Env: GUARD_PYTHON overrides the interpreter (default .venv/bin/python, then
#      python3). GUARD_SKIP_PYTEST=1 skips check 2 (used by the guard's own test).
set -u

cd "$(git rev-parse --show-toplevel)" || exit 1

SYNTH_PATHS=(
  "src/intent_engine/core/synthetic_worlds.py"
  "scripts/run_synthetic_world_eval.py"
  "tests/test_synthetic_worlds.py"
  "tests/test_premortem_ledger_wiring.py"
  "reports/synthetic_worlds_eval.json"
  "reports/synthetic_worlds_eval.md"
  "reports/synthetic_worlds_eval_live.json"
  "reports/synthetic_worlds_eval_live.md"
  "reports/synthetic_worlds_run_history.jsonl"
)

fail=0

# --- Check 1: synthetic-worlds tree state -----------------------------------
# (a) none of the core files may be staged for deletion
while IFS= read -r line; do
  code="${line:0:2}"
  path="${line:3}"
  case "$path" in
    reports/synthetic_worlds_*|src/intent_engine/core/synthetic_worlds.py|scripts/run_synthetic_world_eval.py|tests/test_synthetic_worlds.py|tests/test_premortem_ledger_wiring.py)
      if [[ "$code" == D* || "$code" == "??" ]]; then
        echo "GUARD FAIL (tree): '$path' is ${code/??/untracked} — synthetic-worlds files must stay tracked." >&2
        echo "  If this is a new run artifact, 'git add' it; if you meant to delete it, that breaks append-only history." >&2
        fail=1
      fi
      ;;
  esac
done < <(git status --porcelain=v1)

# (b) every core file must exist and be tracked
for p in "${SYNTH_PATHS[@]}"; do
  if ! git ls-files --error-unmatch "$p" >/dev/null 2>&1; then
    echo "GUARD FAIL (tree): '$p' is not tracked by git." >&2
    fail=1
  fi
done

if [[ $fail -ne 0 ]]; then
  echo "Commit blocked by synthetic-worlds tree check." >&2
  exit 1
fi

# --- Check 2: offline suite green, EXIT=0 explicitly checked ----------------
if [[ "${GUARD_SKIP_PYTEST:-0}" != "1" ]]; then
  PYTHON="${GUARD_PYTHON:-.venv/bin/python}"
  if ! "$PYTHON" -c "import sys" >/dev/null 2>&1; then
    PYTHON=python3
  fi
  # Strip the git hook environment (GIT_DIR/GIT_INDEX_FILE/... are ABSOLUTE in a
  # linked worktree) so NO test's git subprocess can be misdirected at this real
  # repo/index — defense-in-depth behind each test sanitizing its own env
  # (2026-07-26 worktree incident fix).
  env -u ANTHROPIC_API_KEY \
    -u GIT_DIR -u GIT_INDEX_FILE -u GIT_WORK_TREE -u GIT_COMMON_DIR \
    -u GIT_OBJECT_DIRECTORY -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
    -u GIT_NAMESPACE -u GIT_PREFIX \
    "$PYTHON" -m pytest -q -p no:cacheprovider \
    --deselect tests/test_simulator_e2e.py \
    --deselect tests/test_calendar_live.py \
    --deselect tests/test_macro_data_live.py \
    --deselect tests/test_market_resolution_live.py \
    --deselect tests/test_scrap_estimate_live.py
  code=$?
  if [[ $code -ne 0 ]]; then
    echo "GUARD FAIL (suite): pytest EXIT=$code (need EXIT=0). Commit blocked." >&2
    exit 1
  fi
  echo "guard: suite EXIT=0 (explicitly checked)"
fi

exit 0
