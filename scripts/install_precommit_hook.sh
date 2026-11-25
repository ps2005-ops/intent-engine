#!/usr/bin/env bash
# Installs scripts/precommit_guard.sh as the repo's pre-commit hook.
set -eu
cd "$(git rev-parse --show-toplevel)"
# `.git` is a FILE in a linked worktree, so `mkdir -p .git/hooks` fails there
# with "Not a directory" and the hook silently stays stale. Ask git where the
# hooks actually live -- in a worktree that resolves to the SHARED hooks dir of
# the main checkout, which is correct: one guard for every worktree.
HOOK="$(git rev-parse --git-path hooks/pre-commit)"
mkdir -p "$(dirname "$HOOK")"
cp scripts/precommit_guard.sh "$HOOK"
chmod +x "$HOOK" scripts/precommit_guard.sh
echo "pre-commit hook installed -> $HOOK"
