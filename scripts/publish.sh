#!/bin/bash
# publish.sh — thin wrapper around git_publish.py
# Usage: bash publish.sh "commit message"
# Delegates to the Python script which handles locks, stale processes,
# and the git commit/push reliably.
REPO="$HOME/Desktop/joaobonin.com"
MSG="${1:-auto-commit}"
python3 "$REPO/scripts/git_publish.py" "$MSG"
