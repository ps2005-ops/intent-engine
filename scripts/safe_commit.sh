#!/usr/bin/env bash
# Safe commit helper (2026-07-26, after the linked-worktree corruption incident).
#
# Stages ONLY the explicit paths you name, then refuses to commit if the staged
# set looks like an accident — too many files, too many deletions, a repo-wide
# deletion pattern, or paths outside the allowed area. It runs targeted tests and
# the corrected guard, then verifies the resulting commit matches what was staged.
# It NEVER runs `git add .`/`-A`.
#
# Usage:
#   scripts/safe_commit.sh -m "msg" [options] <path> [<path> ...]
# Options:
#   --allow REGEX        paths must match this (default: growth_os|GROWTH_OS|test_growth_os)
#   --max-files N        refuse if >N files staged (default 50)
#   --max-deletions N    refuse if >N lines deleted (default 200)
#   --test "CMD"         targeted test command (default: pytest -k growth_os)
#   --no-verify          pass through to git (discouraged; the guard is the point)
set -euo pipefail

MSG=""; ALLOW='growth_os|GROWTH_OS|test_growth_os'; MAX_FILES=50; MAX_DEL=200
TEST_CMD='python -m pytest tests/ -k growth_os -q -p no:cacheprovider'
NOVERIFY=""; PATHS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m) MSG="$2"; shift 2;;
    --allow) ALLOW="$2"; shift 2;;
    --max-files) MAX_FILES="$2"; shift 2;;
    --max-deletions) MAX_DEL="$2"; shift 2;;
    --test) TEST_CMD="$2"; shift 2;;
    --no-verify) NOVERIFY="--no-verify"; shift;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) PATHS+=("$1"); shift;;
  esac
done

[[ -n "$MSG" ]] || { echo "refuse: -m <message> required" >&2; exit 2; }
[[ ${#PATHS[@]} -gt 0 ]] || { echo "refuse: name explicit paths (never 'git add .')" >&2; exit 2; }

# 1. index must start clean — never fold in someone else's staged work
if [[ -n "$(git diff --cached --name-only)" ]]; then
  echo "refuse: index is not clean; unstage first (git restore --staged .)" >&2; exit 1
fi

# 2. stage ONLY the explicit paths
git add -- "${PATHS[@]}"

STAGED="$(git diff --cached --name-only)"
NFILES="$(printf '%s\n' "$STAGED" | grep -c . || true)"
NDEL="$(git diff --cached --numstat | awk '{d+=$2} END{print d+0}')"
NADD="$(git diff --cached --numstat | awk '{a+=$1} END{print a+0}')"

echo "=== staged ($NFILES files, +$NADD/-$NDEL) ==="; printf '%s\n' "$STAGED" | sed 's/^/  /'
git diff --cached --shortstat | sed 's/^/  /'

# 3. safety gates — any failure unstages and aborts (no commit)
abort() { echo "REFUSED: $1" >&2; git restore --staged -- "${PATHS[@]}" 2>/dev/null || true; exit 1; }
(( NFILES <= MAX_FILES )) || abort "$NFILES files > --max-files $MAX_FILES"
(( NDEL <= MAX_DEL ))    || abort "$NDEL deletions > --max-deletions $MAX_DEL"
# repo-wide deletion pattern: many D entries in the staged diff
NDROWS="$(git diff --cached --name-status | grep -c '^D' || true)"
(( NDROWS <= 5 )) || abort "$NDROWS staged file DELETIONS looks like a repo-wide wipe"
# every staged path must be inside the allowed area
BADP="$(printf '%s\n' "$STAGED" | grep -vE "$ALLOW" || true)"
[[ -z "$BADP" ]] || abort "paths outside --allow '$ALLOW': $(echo "$BADP" | tr '\n' ' ')"

# 4. targeted tests
echo "=== running targeted tests: $TEST_CMD ==="
eval "$TEST_CMD" || abort "targeted tests failed"

# 5. commit (the hook runs the corrected guard unless --no-verify)
git commit $NOVERIFY -m "$MSG"

# 6. verify the resulting commit matches what was staged
CFILES="$(git diff-tree --no-commit-id --name-only -r HEAD | grep -c . || true)"
if [[ "$CFILES" != "$NFILES" ]]; then
  echo "WARNING: commit has $CFILES files but $NFILES were staged — inspect immediately!" >&2; exit 1
fi
echo "=== committed OK: $CFILES files (matches staged) ==="; git log --oneline -1
