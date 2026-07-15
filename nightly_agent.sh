#!/bin/bash
# Overnight autonomous task runner. Picks the top RUNNABLE task from
# ROADMAP.md, works it on an isolated branch via `claude -p` under a scoped
# permission set, and regenerates MORNING_REPORT.md with real results.
#
# Safety model, stated plainly (see PROGRESS.md's "Overnight autonomous
# operation" section for the full writeup):
# - Runs under --permission-mode auto (Anthropic's real safety-classifier
#   mode, verified directly this session via a live `claude -p ... --permission-mode
#   auto` call -- not the earlier, incorrect secondhand read that it needed
#   an unavailable model tier), not --dangerously-skip-permissions -- per
#   Anthropic's own guidance, full bypass is for disposable sandboxes, not
#   a real dev machine. Auto mode itself can only be selected as the
#   SESSION DEFAULT from ~/.claude/settings.json (user-level) -- Claude
#   Code deliberately ignores defaultMode:"auto" set at the project level
#   (.claude/settings.json / .claude/settings.local.json) so a checked-out
#   repo can never grant itself elevated trust. This script's own
#   --permission-mode auto is a plain CLI flag (an explicit per-invocation
#   choice by whoever runs the script), not a project-settings escalation,
#   and is unaffected by that restriction.
# - On top of the classifier, explicit --allowedTools/--disallowedTools plus
#   .claude/nightly-agent-settings.json's own deny list are a SECOND,
#   structural layer evaluated regardless of mode -- not relying on the
#   classifier's judgment alone for the things that must never happen
#   (force-push, rm -rf, main-branch pushes, credential paths).
# - --max-budget-usd is a REAL hard cap (verified flag). There is no
#   --max-turns flag in this CLI version -- checked directly via `claude
#   --help`, not assumed. "Stop when budget/turns run out" is therefore only
#   partially structural: budget is a hard stop, but the agent's own
#   judgment about when to stop iterating and commit WIP is prompted, not
#   mechanically enforced. Stated honestly, not oversold.
# - Never operates on main: always creates and works on agent/<task-id>.
# - Never pushes to main/master (denied in the settings file and the
#   allowedTools scoping both).
#
# Usage: ./nightly_agent.sh  (invoked by launchd; safe to run manually too)

set -uo pipefail  # NOT -e: a failed claude invocation or failed test run must
                   # still let the script reach the report-generation step.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H%M%SZ")"
LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"
RESULT_JSON_PATH="$LOG_DIR/nightly_${TIMESTAMP}.json"
STDERR_LOG="$LOG_DIR/nightly_${TIMESTAMP}.stderr.log"

NIGHTLY_BUDGET_USD="${NIGHTLY_BUDGET_USD:-5.00}"  # conservative default -- override via env var; a real dollar preference, not guessed permanently
SETTINGS_FILE="$REPO_ROOT/.claude/nightly-agent-settings.json"

ALLOWED_TOOLS="Read,Edit,Bash(git status*),Bash(git diff*),Bash(git log*),Bash(git add*),Bash(git commit*),Bash(git branch*),Bash(git checkout -b agent/*),Bash(git checkout agent/*),Bash(git push origin agent/*),Bash(gh pr create*),Bash(gh pr view*),Bash($PYTHON -m pytest*),Bash($PYTHON -m pyflakes*),Bash($PYTHON -c*),Bash($PYTHON -m pip install*)"
DISALLOWED_TOOLS="Bash(git push --force*),Bash(git push -f*),Bash(git push origin main*),Bash(git push origin master*),Bash(git checkout main*),Bash(git checkout master*),Bash(git reset --hard*),Bash(git clean -f*),Bash(rm -rf*),Bash(sudo*),Bash(curl*),Bash(wget*),Bash(nc *),Bash(ssh*),WebFetch,WebSearch"

echo "=== nightly_agent.sh starting $TIMESTAMP ===" | tee -a "$STDERR_LOG"

# Guard: never run with uncommitted changes already on main -- a failed or
# interrupted prior run leaving dirty state must be surfaced, not built on.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ABORT: working tree is dirty before this run started -- investigate before the next nightly run." | tee -a "$STDERR_LOG"
  "$PYTHON" "$REPO_ROOT/scripts/generate_morning_report.py" --no-task
  exit 1
fi

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "ABORT: not currently on main (on '$CURRENT_BRANCH') -- refusing to start a new task from a non-main base." | tee -a "$STDERR_LOG"
  "$PYTHON" "$REPO_ROOT/scripts/generate_morning_report.py" --no-task
  exit 1
fi

# 1. Pick the top RUNNABLE task.
TASK_ID="$("$PYTHON" "$REPO_ROOT/scripts/pick_next_task.py" "$REPO_ROOT/ROADMAP.md")"
if [ -z "$TASK_ID" ]; then
  echo "No RUNNABLE task found in ROADMAP.md. Nothing to do tonight." | tee -a "$STDERR_LOG"
  "$PYTHON" "$REPO_ROOT/scripts/generate_morning_report.py" --no-task
  exit 0
fi
echo "Picked task: $TASK_ID" | tee -a "$STDERR_LOG"

# 2. Baseline test run (real evidence of before-state, not assumed green).
BASELINE_TEST_OUTPUT="$("$PYTHON" -m pytest -q 2>&1 | tail -8)"

# 3. Branch, never main.
BRANCH="agent/${TASK_ID}"
git checkout -b "$BRANCH" 2>&1 | tee -a "$STDERR_LOG"

# 4. Self-contained prompt: the real ROADMAP.md task text, verbatim, plus
# fixed operating instructions -- no paraphrase between spec and prompt.
TASK_BLOCK="$("$PYTHON" "$REPO_ROOT/scripts/extract_task_prompt.py" "$REPO_ROOT/ROADMAP.md" "$TASK_ID")"

FULL_PROMPT="$TASK_BLOCK

INSTRUCTIONS:
- Work only within the files-in-scope listed above.
- Implement the task, then run the full test suite ($PYTHON -m pytest -q) and confirm the definition-of-done check passes.
- If tests fail, diagnose and fix -- never skip, weaken, or delete a test to make it pass.
- Commit your work with a clear commit message once the definition-of-done is met, then stop.
- If you cannot reach the definition-of-done within budget: commit whatever real, WORKING progress exists (never commit a known-broken state) with a commit message starting 'WIP:' and a clear status note on exactly what's done, what's not, and why. An honest partial commit and stop is correct behavior, not a failure to avoid.
- Never touch files outside this task's stated scope.
- Never modify ROADMAP.md, MORNING_REPORT.md, or anything under .claude/ -- those are managed by the orchestrating script, not you."

# 5. Invoke claude -p, scoped and budgeted. Auto mode (the real safety
# classifier), not full bypass -- backstopped by the explicit
# allow/disallow lists and settings file regardless of what the classifier
# would otherwise permit.
RESULT_JSON="$(claude -p "$FULL_PROMPT" \
  --settings "$SETTINGS_FILE" \
  --permission-mode auto \
  --allowedTools "$ALLOWED_TOOLS" \
  --disallowedTools "$DISALLOWED_TOOLS" \
  --max-budget-usd "$NIGHTLY_BUDGET_USD" \
  --output-format json \
  2>>"$STDERR_LOG")"
echo "$RESULT_JSON" > "$RESULT_JSON_PATH"

# 6. Post-run test run (real evidence of after-state).
FINAL_TEST_OUTPUT="$("$PYTHON" -m pytest -q 2>&1 | tail -8)"

# 7. Real diff stats against main.
DIFF_STATS="$(git diff main --stat 2>&1)"

# 8. Push + PR if a remote and gh exist; otherwise a real diff-summary file
# -- never silently skipped, never a fabricated PR link.
HAS_REMOTE=0
if git remote -v 2>/dev/null | grep -q .; then HAS_REMOTE=1; fi
HAS_GH=0
if command -v gh >/dev/null 2>&1; then HAS_GH=1; fi

if [ "$HAS_REMOTE" = "1" ] && [ "$HAS_GH" = "1" ]; then
  git push origin "$BRANCH" 2>&1 | tee -a "$STDERR_LOG"
  PR_URL="$(gh pr create --title "[agent] $TASK_ID" --body "Automated nightly run. See MORNING_REPORT.md for the real diff/test/cost summary." --head "$BRANCH" 2>&1)"
  PR_NOTE="PR opened: $PR_URL"
else
  DIFF_FILE="$LOG_DIR/diff_${TASK_ID}_${TIMESTAMP}.patch"
  git diff main > "$DIFF_FILE" 2>&1
  PR_NOTE="No git remote and/or gh CLI configured for this repo -- real diff written to logs/$(basename "$DIFF_FILE"). Branch $BRANCH is local only; review and merge manually."
fi

# 9. Return to main -- the branch/commits stay, the working tree does not
# stay on a task branch between nightly runs.
git checkout main 2>&1 | tee -a "$STDERR_LOG"

# 10. Regenerate MORNING_REPORT.md from real collected data.
"$PYTHON" "$REPO_ROOT/scripts/generate_morning_report.py" \
  --task-id "$TASK_ID" \
  --branch "$BRANCH" \
  --result-json "$RESULT_JSON_PATH" \
  --baseline-tests "$BASELINE_TEST_OUTPUT" \
  --final-tests "$FINAL_TEST_OUTPUT" \
  --diff-stats "$DIFF_STATS" \
  --pr-note "$PR_NOTE"

echo "=== nightly_agent.sh done $TIMESTAMP ===" | tee -a "$STDERR_LOG"
