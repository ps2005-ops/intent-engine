#!/usr/bin/env bash
# Installs scripts/precommit_guard.sh as the repo's pre-commit hook.
set -eu
cd "$(git rev-parse --show-toplevel)"
mkdir -p .git/hooks
cp scripts/precommit_guard.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit scripts/precommit_guard.sh
echo "pre-commit hook installed -> .git/hooks/pre-commit"
